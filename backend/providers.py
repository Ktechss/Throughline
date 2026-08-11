"""Who renders the picture. The model is the same; the bill is not.

Measured 2026-08-11 on one prompt, three references, 4K, scored on Soni's own
gallery — the only variable was the provider:

    fal    sim 0.4304   $0.30           66s
    kie    sim 0.4267   $0.12 (24 cr)  220s
    poyo   sim 0.4426   $0.175 (35 cr) 265s

All three resell Google's nano-banana-pro, and the 0.016 spread is well inside
the seed-to-seed variance this project sees on identical prompts. So the choice
is price and latency, not quality — kie is 60% cheaper than fal at the same
picture, and poyo's advertised $0.070 turned out to be $0.175 when the task
record was actually read.

This module is deliberately thin. It replaces exactly one step of generate() —
"submit a prompt plus reference URLs, get an image URL back" — and returns fal's
own response shape so nothing downstream can tell the difference. The retry,
reclaim, download-parking and gate logic in generate.py is hard-won and stays
where it is.

Two things that cost an afternoon to find, kept here so they are not rediscovered:

  * kie's uploader 403s without a browser User-Agent. The endpoint is fine; the
    bot filter in front of it is not.
  * kie serves results from a CDN that resolves IPv6-ONLY. On a v4-only network
    the generation succeeds, is billed, and the download fails — which is the
    worst possible shape, so source_url parking in generate.py matters more here
    than it does on fal.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.request
from pathlib import Path

# Importing config runs load_dotenv(.env), and every key below is read from the
# environment. Without this the module imports fine, finds no keys, reports every
# provider unavailable and quietly renders everything on fal at full price — a
# failure with no error message anywhere. Caught in a bare `from backend import
# providers`, which is exactly how a script or a test would reach it.
from . import config  # noqa: F401

# A browser UA, because kie's upload endpoint refuses anything else.
_UA = "Mozilla/5.0"
_KIE_UPLOAD = "https://kieai.redpandaai.co/api/file-base64-upload"
_KIE_CREATE = "https://api.kie.ai/api/v1/jobs/createTask"
_KIE_POLL = "https://api.kie.ai/api/v1/jobs/recordInfo"
_KIE_CREDIT = "https://api.kie.ai/api/v1/chat/credit"

POLL_EVERY = 6          # seconds; kie reports 110-220s for a 4K edit
POLL_TIMEOUT = 1200     # a 4K three-reference edit has taken 274s at worst


class ProviderError(RuntimeError):
    """A provider refused or failed. Carries the provider's own message so a
    content refusal still reads as a content refusal to generate()'s retry."""


def _post(url: str, body: dict, key: str, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": _UA, "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _get(url: str, key: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}",
                                               "User-Agent": _UA})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def kie_key() -> str:
    k = os.environ.get("KIE_API_KEY", "").strip()
    if not k:
        raise ProviderError("KIE_API_KEY is not set — add it to .env")
    return k


_CREDIT_CACHE: tuple[float, float | None] = (0.0, None)
CREDIT_TTL = 60          # seconds


def kie_credits(force: bool = False) -> float | None:
    """Remaining balance, or None if it cannot be read. 24 credits per 4K edit,
    so this is roughly 'generations left, times 24'.

    Cached for a minute because the sidebar polls it: every call is a round trip
    to kie, and a balance that moves only when a shot is taken does not need
    asking about once per open tab per interval. A generation bypasses the cache
    (force) so the number visibly drops right after it is spent.
    """
    global _CREDIT_CACHE
    age, val = _CREDIT_CACHE
    if not force and val is not None and (time.time() - age) < CREDIT_TTL:
        return val
    try:
        val = float(_get(_KIE_CREDIT, kie_key())["data"])
    except Exception:                                     # noqa: BLE001
        return _CREDIT_CACHE[1]      # last known beats nothing
    _CREDIT_CACHE = (time.time(), val)
    return val


def kie_upload(path: Path) -> str:
    """Host one local reference and return its public URL.

    Uploads are base64 rather than multipart because the references are small —
    identity 1.1MB, a headless outfit crop 0.7MB — and base64's 33% overhead is
    cheaper than another code path. Files are deleted by kie after 3 days, which
    is irrelevant: they are re-uploaded per generation and the run keeps its own
    copy on disk.
    """
    mime = mimetypes.guess_type(path.name)[0] or "image/webp"
    b = base64.b64encode(path.read_bytes()).decode()
    d = _post(_KIE_UPLOAD,
              {"base64Data": f"data:{mime};base64,{b}",
               "uploadPath": "throughline", "fileName": path.name},
              kie_key(), timeout=600)
    url = ((d.get("data") or {}).get("downloadUrl"))
    if not url:
        raise ProviderError(f"kie upload failed: {json.dumps(d)[:200]}")
    return url


# --------------------------------------------------------- kie model registry
#
# kie's catalogue is NOT uniform, and every difference below fails SILENTLY
# rather than erroring. Send image_urls to a nano model, or image_input to a
# seedream one, and the task succeeds, bills in full, and renders with NO
# REFERENCES AT ALL — which looks like catastrophic identity drift rather than
# a wiring bug. That trap is why this is a table and not an if/else.
#
# Verified against the raw OpenAPI: appending .md to any docs.kie.ai model page
# returns the schema with exact enums, maxItems and defaults.
#
#   model                           refs key      res key     ceiling
#   nano-banana-pro                 image_input   resolution  4K
#   nano-banana-2                   image_input   resolution  4K   (14 refs)
#   seedream/4.5-edit               image_urls    quality     4K   (high)
#   seedream/5-pro-image-to-image   image_urls    quality     2K   (high)
#   seedream/5-lite-image-to-image  image_urls    quality     4K   (ultra)
#
# The seedream tiers do not share a quality vocabulary: "high" is 4K on 4.5,
# 2K on 5-pro and only 3K on 5-lite. Asking for 4K therefore has to be
# translated per model, and 5-pro cannot honour it at all — it is clamped and
# the caller is told, because silently returning half the pixels is how a shot
# comes back with a 169px face and no explanation.
_PASSTHROUGH = {"1K": "1K", "2K": "2K", "4K": "4K"}

KIE_MODELS: dict[str, dict] = {
    "nano-banana-pro": {
        "model": "nano-banana-pro", "label": "Nano Banana Pro", "refs_key": "image_input",
        "res_key": "resolution", "res_map": _PASSTHROUGH, "max_refs": 8,
        "extra": {"output_format": "png"}, "usd_4k": 0.12,
    },
    "nano-banana-2": {
        "model": "nano-banana-2", "label": "Nano Banana 2", "refs_key": "image_input",
        "res_key": "resolution", "res_map": _PASSTHROUGH, "max_refs": 14,
        "extra": {"output_format": "png"}, "usd_4k": 0.09,
    },
    "seedream-4.5": {
        "model": "seedream/4.5-edit", "label": "Seedream 4.5", "refs_key": "image_urls",
        "res_key": "quality", "res_map": {"1K": "basic", "2K": "basic", "4K": "high"},
        "max_refs": 14, "extra": {}, "usd_4k": 0.0325,
    },
    "seedream-5-pro": {
        "model": "seedream/5-pro-image-to-image", "label": "Seedream 5 Pro", "refs_key": "image_urls",
        # No 4K tier exists: basic=1K, high=2K. 4K maps to the ceiling, not to
        # an error, so a caller asking for 4K still renders — at 2K.
        "res_key": "quality", "res_map": {"1K": "basic", "2K": "high", "4K": "high"},
        "ceiling": "2K", "max_refs": 10, "extra": {}, "usd_4k": 0.075,
    },
    "seedream-5-lite": {
        "model": "seedream/5-lite-image-to-image", "label": "Seedream 5 Lite", "refs_key": "image_urls",
        # basic=2K, high=3K, ultra=4K — there is NO 1K tier, so a 1K request
        # renders at 2K. Measured: asked for 1K, got 1728x2304. The row's new
        # width/height is what makes that visible; `resolution` alone still says
        # "1K" because that is what was asked for, not what arrived.
        "res_key": "quality", "res_map": {"1K": "basic", "2K": "basic", "4K": "ultra"},
        "max_refs": 14, "extra": {}, "usd_4k": 0.0275,
    },
}

DEFAULT_KIE_MODEL = os.environ.get("THROUGHLINE_KIE_MODEL", "nano-banana-pro").strip()


def model_path():
    return config.ROOT / "data" / "model.json"


def load_model() -> str:
    """The project-wide default model key.

    Persisted rather than env-only for the same reason the provider order is:
    "render the wardrobe on seedream but the shot on nano" is a working decision
    made mid-session, and restarting the server to change it is not a workflow.
    A per-request `model` still overrides this for one generation.
    """
    import json as _json
    p = model_path()
    if p.exists():
        try:
            n = (_json.loads(p.read_text()) or {}).get("model")
            if n in KIE_MODELS:
                return n
        except Exception:                                   # noqa: BLE001
            pass
    return DEFAULT_KIE_MODEL if DEFAULT_KIE_MODEL in KIE_MODELS else "nano-banana-pro"


def save_model(name: str) -> str:
    import json as _json
    if name not in KIE_MODELS:
        raise ProviderError(f"unknown kie model {name!r} — known: {sorted(KIE_MODELS)}")
    p = model_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps({"model": name}, indent=2) + "\n")
    return name


def model_rows() -> list[dict]:
    """The catalogue as the UI needs it — label, price, and the real ceiling.

    `ceiling` is the honest maximum, not the requested one: seedream-5-pro has no
    4K tier, so a 4K request renders at 2K. Surfacing that in the picker is the
    difference between choosing it and being surprised by a 169px face.
    """
    cur = load_model()
    return [{"id": k, "model": s["model"], "label": s.get("label", k),
             "usd_4k": s["usd_4k"], "max_refs": s["max_refs"],
             "ceiling": s.get("ceiling", "4K"), "active": k == cur}
            for k, s in KIE_MODELS.items()]


def kie_model(name: str | None) -> dict:
    """Resolve a model key, accepting either our key or kie's own model string."""
    n = (name or load_model()).strip()
    if n in KIE_MODELS:
        return KIE_MODELS[n]
    for spec in KIE_MODELS.values():
        if spec["model"] == n:
            return spec
    raise ProviderError(f"unknown kie model {n!r} — known: {sorted(KIE_MODELS)}")


def kie_generate(*, prompt: str, refs: list[Path], aspect: str, resolution: str,
                 progress: dict | None = None, model: str | None = None) -> dict:
    """Render on kie and return fal's response shape: {"images": [{"url": ...}]}.

    generate() unpacks r["images"][0]["url"] and knows nothing else about who
    made it, so matching that shape is the whole of the integration.
    """
    key = kie_key()
    spec = kie_model(model)

    # Over-budget references are dropped HERE rather than silently truncated by
    # the API, so the run record and the caller agree on what was actually sent.
    if len(refs) > spec["max_refs"]:
        refs = refs[: spec["max_refs"]]

    if progress is not None:
        progress["stage"] = "uploading references"
    urls = [kie_upload(p) for p in refs]

    if progress is not None:
        progress["stage"] = "generating"
    inp = {"prompt": prompt, spec["refs_key"]: urls, "aspect_ratio": aspect,
           spec["res_key"]: spec["res_map"].get(resolution, resolution),
           **spec["extra"]}
    d = _post(_KIE_CREATE, {"model": spec["model"], "input": inp}, key)
    if d.get("code") != 200:
        raise ProviderError(f"kie createTask: {d.get('msg')}")
    task = d["data"]["taskId"]

    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT:
        time.sleep(POLL_EVERY)
        st = (_get(f"{_KIE_POLL}?taskId={task}", key).get("data") or {})
        state = st.get("state")
        if state == "fail":
            # Keep the provider's wording. generate() greps for "content_policy"
            # to decide whether to retry or fall back, and a reworded message
            # would break that.
            raise ProviderError(f"kie: {st.get('failMsg') or 'failed'} "
                                f"({st.get('failCode')})")
        if state == "success":
            url = json.loads(st["resultJson"])["resultUrls"][0]
            return {"images": [{"url": url}],
                    "credits": st.get("creditsConsumed"),
                    # Which model actually rendered, recorded on the run. Without
                    # it a shot from a non-default model is indistinguishable
                    # from a nano one later, and every comparison built on the
                    # runs table quietly mixes renderers.
                    "model": spec["model"],
                    "seconds": round((st.get("costTime") or 0) / 1000, 1)}
        if progress is not None and state:
            progress["stage"] = f"generating ({state})"
    raise ProviderError(f"kie: task {task} did not finish in {POLL_TIMEOUT}s")



# ------------------------------------------------------------------- upscale
#
# DELIVERY ONLY. This never runs before the gate and its output is never the
# file a verdict is computed from.
#
# Measured 2026-08-12 on the 5-pro rooftop shot, topaz x2:
#
#     face_px      169 -> 338      (x2.00)
#     similarity   0.6417 -> 0.6363  (-0.0055)
#
# The pixels double; the identity signal does not move. That is expected and it
# is the whole reason this is quarantined: insightface detects at a fixed
# det_size=(640,640) and ArcFace embeds a 112x112 aligned crop, so a 169px face
# is already downsampled twice on its way in. Upscaling feeds the embedder an
# interpolated crop while face_px — a raw bbox width in on-disk pixel space —
# doubles.
#
# So an upscaled file scored by the gate would clear MIN_FACE_PX (160) and the
# FACE_PLATEAU_PX (400) band on manufactured confidence, and would silently join
# a corpus of 207 shots calibrated at native resolution. gate.py's own framing:
# "Face pixels are a gradient, not a cliff." The gradient is about how much
# detail the GENERATOR rendered; interpolation adds none of it.
#
# What it does buy is real: fabric weave and surface grain are visibly crisper,
# which is worth having on a deliverable.
_TOPAZ_MAX_MB = 10          # topaz refuses larger inputs outright


def kie_upscale(path: Path, factor: str = "2", *,
                progress: dict | None = None) -> dict:
    """Upscale one image on topaz. Same response shape as kie_generate.

    `factor` is topaz's own enum — "1", "2" or "4" — passed through as a string
    because that is what the schema declares; sending an int is rejected.
    """
    factor = str(factor)
    if factor not in ("1", "2", "4"):
        raise ProviderError(f"upscale factor must be 1, 2 or 4 — got {factor!r}")
    mb = path.stat().st_size / 1e6
    if mb >= _TOPAZ_MAX_MB:
        # Worth naming rather than letting topaz return an opaque failure: a 4K
        # PNG straight off the CDN is ~20MB, while the archived WebP this is
        # meant to read is under 1.5MB.
        raise ProviderError(f"{path.name} is {mb:.1f}MB, over topaz's "
                            f"{_TOPAZ_MAX_MB}MB input cap")

    key = kie_key()
    if progress is not None:
        progress["stage"] = "uploading"
    url = kie_upload(path)

    if progress is not None:
        progress["stage"] = f"upscaling x{factor}"
    d = _post(_KIE_CREATE,
              {"model": "topaz/image-upscale",
               "input": {"image_url": url, "upscale_factor": factor}}, key)
    if d.get("code") != 200:
        raise ProviderError(f"kie createTask: {d.get('msg')}")
    task = d["data"]["taskId"]

    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT:
        time.sleep(POLL_EVERY)
        st = (_get(f"{_KIE_POLL}?taskId={task}", key).get("data") or {})
        state = st.get("state")
        if state == "fail":
            raise ProviderError(f"kie upscale: {st.get('failMsg') or 'failed'} "
                                f"({st.get('failCode')})")
        if state == "success":
            return {"images": [{"url": json.loads(st["resultJson"])["resultUrls"][0]}],
                    "credits": st.get("creditsConsumed"),
                    "model": "topaz/image-upscale",
                    "seconds": round((st.get("costTime") or 0) / 1000, 1)}
        if progress is not None and state:
            progress["stage"] = f"upscaling ({state})"
    raise ProviderError(f"kie upscale: task {task} did not finish in {POLL_TIMEOUT}s")


# --------------------------------------------------------------------- poyo
_POYO_SUBMIT = "https://api.poyo.ai/api/generate/submit"
_POYO_STATUS = "https://api.poyo.ai/api/generate/status"

# poyo publishes $0.070 for a 4K nano-banana-pro edit. Its own task record says
# 35 credits, and its credits are $0.005, so the real number is $0.175 — still
# 42% under fal, but two and a half times what the page advertises and half again
# what kie charges. The advertised figure was the tier labelled "via Fal"; what
# the API actually routes to is dearer. Read the meter, not the pricing page.
POYO_CREDIT_USD = 0.005


def poyo_key() -> str:
    k = os.environ.get("POYO_API_KEY", "").strip()
    if not k:
        raise ProviderError("POYO_API_KEY is not set — add it to .env")
    return k


def poyo_generate(*, prompt: str, refs: list[Path], aspect: str, resolution: str,
                  progress: dict | None = None, model: str | None = None) -> dict:
    """Render on poyo. Same contract as kie_generate.

    `model` is accepted so the chain can pass it uniformly, but poyo only carries
    nano-banana-pro here. A request for any other model is refused rather than
    quietly rendered on the wrong one — falling through to the next provider is
    the correct outcome, and a silent substitution would corrupt a comparison.

    poyo has NO upload endpoint of its own — it only accepts URLs — so the
    references are hosted on kie and handed over. That means poyo needs a working
    KIE_API_KEY even when kie itself is disabled, which is worth knowing before
    turning kie off and expecting poyo to carry on alone.

    It also enforces 10MB per image. Local references are 0.3-1.2MB so that is
    irrelevant in practice, but a 4K OUTPUT used as a reference is 12-21MB and
    would be refused — the failure that first surfaced the limit.
    """
    key = poyo_key()
    if model and model not in ("nano-banana-pro", "nano-banana-pro-edit"):
        raise ProviderError(f"poyo does not carry {model!r}")
    if progress is not None:
        progress["stage"] = "uploading references"
    urls = [kie_upload(p) for p in refs]

    if progress is not None:
        progress["stage"] = "generating"
    d = _post(_POYO_SUBMIT,
              {"model": "nano-banana-pro-edit",
               # image_urls here, image_input on kie. Same model, same idea,
               # different spelling — send the wrong one and it generates with no
               # references at all rather than erroring.
               "input": {"prompt": prompt, "image_urls": urls, "size": aspect,
                         "resolution": resolution, "n": 1, "output_format": "png"}},
              key)
    task = (d.get("data") or {}).get("task_id") or d.get("task_id")
    if not task:
        raise ProviderError(f"poyo submit: {json.dumps(d)[:200]}")

    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT:
        time.sleep(POLL_EVERY)
        st = (_get(f"{_POYO_STATUS}/{task}", key).get("data") or {})
        state = st.get("status")
        if state == "failed":
            raise ProviderError(f"poyo: {st.get('error_message') or 'failed'}")
        if state == "finished":
            return {"images": [{"url": st["files"][0]["file_url"]}],
                    "credits": st.get("credits_amount")}
        if progress is not None and state:
            progress["stage"] = f"generating ({state})"
    raise ProviderError(f"poyo: task {task} did not finish in {POLL_TIMEOUT}s")


# ------------------------------------------------------------------ registry
#
# What each provider costs and how fast it is, measured on one prompt with three
# references at 4K — never taken from a pricing page, because poyo's was wrong by
# 2.5x. `usd` is per 4K edit.
CATALOGUE = {
    "kie":  {"label": "kie.ai", "usd": 0.12, "seconds": 220, "key": "KIE_API_KEY",
             "note": "same picture as fal for 40% of the price; 24 credits per 4K edit"},
    "poyo": {"label": "poyo.ai", "usd": 0.175, "seconds": 265, "key": "POYO_API_KEY",
             "note": "35 credits per 4K edit — its advertised $0.070 was not what "
                     "the API charged; needs a kie key to host references"},
    "fal":  {"label": "fal.ai", "usd": 0.30, "seconds": 66, "key": "FAL_KEY",
             "note": "dearest and 3x faster; the fallback everything else falls to"},
}

RUNNERS = {"kie": kie_generate, "poyo": poyo_generate}


def available(name: str) -> bool:
    """Is this provider usable at all — i.e. is its key present?"""
    entry = CATALOGUE.get(name)
    return bool(entry and os.environ.get(entry["key"], "").strip())


# The ORDER providers are tried in, and which are switched off. Persisted rather
# than an env var because it is a running preference — "kie is queueing today,
# put fal first" — and restarting the server to change it is not a workflow.
#
# fal is deliberately last-and-permanent in the default: it is the dearest, and
# it is what everything else falls to, so it earns its place by working when the
# cheap ones do not.
_DEFAULT_ORDER = ["kie", "poyo", "fal"]
_SETTINGS = None            # set by config at import; kept out of this module's
                            # import graph so providers.py stays dependency-free


def settings_path():
    return config.ROOT / "data" / "providers.json"


def load_order() -> list[dict]:
    """[{name, enabled}] in priority order, healed against the catalogue.

    Anything unknown is dropped and anything missing is appended, so editing the
    file by hand — or adding a provider in a later version — cannot leave the
    pipeline with no way to render.
    """
    import json as _json
    p = settings_path()
    saved = []
    if p.exists():
        try:
            saved = _json.loads(p.read_text()).get("order") or []
        except Exception:                                   # noqa: BLE001
            saved = []
    out, seen = [], set()
    for row in saved:
        n = (row or {}).get("name")
        if n in CATALOGUE and n not in seen:
            out.append({"name": n, "enabled": bool(row.get("enabled", True))})
            seen.add(n)
    for n in _DEFAULT_ORDER:
        if n not in seen:
            out.append({"name": n, "enabled": True})
    return out


def save_order(order: list[dict]) -> list[dict]:
    import json as _json
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = [{"name": r["name"], "enabled": bool(r.get("enabled", True))}
             for r in order if r.get("name") in CATALOGUE]
    p.write_text(_json.dumps({"order": clean}, indent=2) + "\n")
    return load_order()


def chain() -> list[str]:
    """The providers to try, in order: enabled, key present, best first.

    Never returns empty. If everything is disabled or unkeyed, fal is used
    anyway — a settings mistake should degrade to the expensive provider, not to
    a pipeline that cannot render at all.
    """
    picked = [r["name"] for r in load_order()
              if r["enabled"] and available(r["name"])]
    return picked or ["fal"]
