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

# poyo is measurably the slowest of the three and gets a longer leash. Giving up
# on a task that is still running is not free: the image finishes, is BILLED, and
# is then abandoned while generate() falls through and pays a second provider for
# the same shot.
POLL_TIMEOUT_BY_PROVIDER = {"poyo": 2400}


class ProviderError(RuntimeError):
    """A provider refused or failed. Carries the provider's own message so a
    content refusal still reads as a content refusal to generate()'s retry."""


class ProviderTimeout(ProviderError):
    """Polling gave up while the task was still RUNNING — not a failure.

    Carries the provider and task id, because the image is very probably
    finishing right now and that id is the only handle left on it. The
    source_url parking in generate.py cannot help here: there is no URL yet, so
    without this the paid-for task becomes unreachable the moment we stop
    waiting, and the chain pays a second provider for the same picture.
    """

    def __init__(self, message: str, *, provider: str, task_id: str):
        super().__init__(message)
        self.provider = provider
        self.task_id = task_id


def poll_budget(name: str) -> int:
    return POLL_TIMEOUT_BY_PROVIDER.get(name, POLL_TIMEOUT)


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

# WHICH ASPECT RATIOS A MODEL WILL ACTUALLY ACCEPT.
#
# kie refuses an unlisted one at createTask with
#   {"code": 500, "msg": "This aspect_ratio is not within the range of allowed options"}
# and because the chain then walks to poyo and fal, the caller is shown whatever
# the LAST provider said. On 2026-08-25 that was a fal content_policy_violation,
# and two models were blamed for a moderation problem that did not exist. The
# request had simply asked seedream for 4:5.
#
# Measured from 200 runs rather than from documentation: nano generated at 16:9,
# 3:4 and 4:5; seedream/5-pro generated at 16:9, 3:4 and 4:3 across 91 runs and
# never once at 4:5. `_NEAREST` maps a refused ratio to the closest supported
# one so a shot still renders — reported, never silent, because the frame the
# caller asked for is not the frame they got.
_SEEDREAM_ASPECTS = ("1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2")
_NANO_ASPECTS = ("1:1", "3:4", "4:3", "4:5", "5:4", "16:9", "9:16", "2:3", "3:2", "21:9")

_NEAREST = {"4:5": "3:4", "5:4": "4:3"}

KIE_MODELS: dict[str, dict] = {
    "nano-banana-pro": {
        "model": "nano-banana-pro", "label": "Nano Banana Pro", "refs_key": "image_input",
        "res_key": "resolution", "res_map": _PASSTHROUGH, "aspects": _NANO_ASPECTS, "max_refs": 8,
        "extra": {"output_format": "png"}, "usd_4k": 0.12,
    },
    "nano-banana-2": {
        "model": "nano-banana-2", "label": "Nano Banana 2", "refs_key": "image_input",
        "res_key": "resolution", "res_map": _PASSTHROUGH, "aspects": _NANO_ASPECTS, "max_refs": 14,
        "extra": {"output_format": "png"}, "usd_4k": 0.09,
    },
    "seedream-4.5": {
        "model": "seedream/4.5-edit", "label": "Seedream 4.5", "refs_key": "image_urls",
        "res_key": "quality", "res_map": {"1K": "basic", "2K": "basic", "4K": "high"},
        "aspects": _SEEDREAM_ASPECTS, "max_refs": 14, "extra": {}, "usd_4k": 0.0325,
    },
    "seedream-5-pro": {
        "model": "seedream/5-pro-image-to-image", "label": "Seedream 5 Pro", "refs_key": "image_urls",
        # No 4K tier exists: basic=1K, high=2K. 4K maps to the ceiling, not to
        # an error, so a caller asking for 4K still renders — at 2K.
        "res_key": "quality", "res_map": {"1K": "basic", "2K": "high", "4K": "high"},
        "ceiling": "2K", "aspects": _SEEDREAM_ASPECTS, "max_refs": 10, "extra": {}, "usd_4k": 0.075,
    },
    "seedream-5-lite": {
        "model": "seedream/5-lite-image-to-image", "label": "Seedream 5 Lite", "refs_key": "image_urls",
        # basic=2K, high=3K, ultra=4K — there is NO 1K tier, so a 1K request
        # renders at 2K. Measured: asked for 1K, got 1728x2304. The row's new
        # width/height is what makes that visible; `resolution` alone still says
        # "1K" because that is what was asked for, not what arrived.
        "res_key": "quality", "res_map": {"1K": "basic", "2K": "basic", "4K": "ultra"},
        "aspects": _SEEDREAM_ASPECTS, "max_refs": 14, "extra": {}, "usd_4k": 0.0275,
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
    # An unsupported ratio is a 500 at createTask, not a soft failure, and the
    # chain then blames whoever it reaches last. Substitute the nearest supported
    # one instead — a 3:4 frame is a real answer to a 4:5 request; a
    # content_policy_violation from a third provider is not.
    allowed = spec.get("aspects")
    if allowed and aspect not in allowed:
        swapped = _NEAREST.get(aspect)
        if swapped in allowed:
            if progress is not None:
                progress["aspect_swapped"] = f"{aspect} -> {swapped}"
            aspect = swapped
        else:
            raise ProviderError(
                f"kie/{spec['model']} does not accept aspect {aspect} "
                f"(it takes {', '.join(allowed)})")

    inp = {"prompt": prompt, spec["refs_key"]: urls, "aspect_ratio": aspect,
           spec["res_key"]: spec["res_map"].get(resolution, resolution),
           **spec["extra"]}
    d = _post(_KIE_CREATE, {"model": spec["model"], "input": inp}, key)
    if d.get("code") != 200:
        raise ProviderError(f"kie createTask: {d.get('msg')}")
    task = d["data"]["taskId"]

    t0 = time.time()
    budget = poll_budget("kie")
    while time.time() - t0 < budget:
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
    raise ProviderTimeout(f"kie: task {task} still running after {budget}s",
                          provider="kie", task_id=task)



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



# poyo carries seedream too — its own catalogue, its own spelling. The adapter
# used to hard-refuse anything but nano, which made "provider poyo + model
# seedream-5-pro" impossible even though poyo sells exactly that.
#
#   our key          poyo model string          ceiling
#   nano-banana-pro  nano-banana-pro-edit       4K
#   seedream-4.5     seedream-4.5-edit          4K
#   seedream-5-pro   seedream-5.0-pro-edit      2K  (size AND resolution required)
#   seedream-5-lite  seedream-5.0-lite-edit     3K
#
# nano-banana-2 is absent from poyo's catalogue, so a request for it declines and
# falls through rather than quietly rendering something else.
POYO_MODELS: dict[str, dict] = {
    "nano-banana-pro": {"model": "nano-banana-pro-edit", "max_res": "4K"},
    "seedream-4.5":    {"model": "seedream-4.5-edit",    "max_res": "4K"},
    "seedream-5-pro":  {"model": "seedream-5.0-pro-edit", "max_res": "2K"},
    "seedream-5-lite": {"model": "seedream-5.0-lite-edit", "max_res": "3K"},
}
_RES_ORDER = ["1K", "2K", "3K", "4K"]


def poyo_model(name: str | None) -> dict:
    n = (name or load_model()).strip()
    spec = POYO_MODELS.get(n)
    if spec is None:
        for k, s in POYO_MODELS.items():
            if s["model"] == n:
                return s
        raise ProviderError(f"poyo does not carry {n!r}")
    return spec


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
    spec = poyo_model(model)          # raises -> chain falls through, never substitutes
    # Clamp rather than fail: 5.0-pro has no 4K tier, and a request for one is a
    # resolution the caller cannot have rather than a shot they cannot take.
    res = resolution
    if _RES_ORDER.index(res) > _RES_ORDER.index(spec["max_res"]):
        res = spec["max_res"]
    if progress is not None:
        progress["stage"] = "uploading references"
    urls = [kie_upload(p) for p in refs]

    if progress is not None:
        progress["stage"] = "generating"
    d = _post(_POYO_SUBMIT,
              {"model": spec["model"],
               # image_urls here, image_input on kie. Same model, same idea,
               # different spelling — send the wrong one and it generates with no
               # references at all rather than erroring. poyo needs BOTH size and
               # resolution on the seedream tiers; omitting either silently
               # defaults to 1:1 at 1K.
               "input": {"prompt": prompt, "image_urls": urls, "size": aspect,
                         "resolution": res, "n": 1, "output_format": "png"}},
              key)
    task = (d.get("data") or {}).get("task_id") or d.get("task_id")
    if not task:
        raise ProviderError(f"poyo submit: {json.dumps(d)[:200]}")

    t0 = time.time()
    budget = poll_budget("poyo")
    while time.time() - t0 < budget:
        time.sleep(POLL_EVERY)
        st = (_get(f"{_POYO_STATUS}/{task}", key).get("data") or {})
        state = st.get("status")
        if state == "failed":
            raise ProviderError(f"poyo: {st.get('error_message') or 'failed'}")
        if state == "finished":
            return {"images": [{"url": st["files"][0]["file_url"]}],
                    "model": spec["model"],
                    "credits": st.get("credits_amount")}
        if progress is not None and state:
            progress["stage"] = f"generating ({state})"
    raise ProviderTimeout(f"poyo: task {task} still running after {budget}s",
                          provider="poyo", task_id=task)


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


def reclaim(provider: str, task_id: str) -> dict | None:
    """Re-poll a task polling gave up on. Returns the same shape as the runners,
    or None if it is still running.

    This is the counterpart to source_url parking: that recovers a shot whose URL
    we had and whose DOWNLOAD failed; this recovers one we stopped waiting for
    before a URL existed. Both exist so a generation that was paid for is never
    silently lost.
    """
    provider = (provider or "").lower()
    if provider == "kie":
        st = (_get(f"{_KIE_POLL}?taskId={task_id}", kie_key()).get("data") or {})
        state = st.get("state")
        if state == "fail":
            raise ProviderError(f"kie: {st.get('failMsg') or 'failed'}")
        if state != "success":
            return None
        return {"images": [{"url": json.loads(st["resultJson"])["resultUrls"][0]}],
                "credits": st.get("creditsConsumed"),
                "seconds": round((st.get("costTime") or 0) / 1000, 1)}
    if provider == "poyo":
        st = (_get(f"{_POYO_STATUS}/{task_id}", poyo_key()).get("data") or {})
        state = st.get("status")
        if state == "failed":
            raise ProviderError(f"poyo: {st.get('error_message') or 'failed'}")
        if state != "finished":
            return None
        return {"images": [{"url": st["files"][0]["file_url"]}],
                "credits": st.get("credits_amount"),
                "seconds": None}
    raise ProviderError(f"cannot reclaim a {provider!r} task")


# --------------------------------------------------------------------- video
#
# Phase 1: animate a still that ALREADY PASSED THE GATE. The approved image
# becomes frame one, so identity is preserved by construction rather than
# re-argued per frame — which is the entire reason image-to-video leads and
# text-to-video is out of scope.
#
# The reference key differs per family and, as everywhere else in this module,
# sending the wrong one does not error — it generates an unanchored clip and
# bills for it:
#
#   kling-2.1/standard|pro     start_image_url   (a bare string)
#   wan2.5-image-to-video      image_urls        (an array)
#
# Prices are not published for video any more than for images. Read
# credits_amount off the status response; do not assume.
POYO_VIDEO: dict[str, dict] = {
    "kling-2.1": {
        "model": "kling-2.1/standard", "image_key": "start_image_url",
        "array": False, "durations": (5, 10), "resolutions": (),
        "label": "Kling 2.1 Standard",
    },
    "kling-2.1-pro": {
        "model": "kling-2.1/pro", "image_key": "start_image_url",
        "array": False, "durations": (5, 10), "resolutions": (),
        "label": "Kling 2.1 Pro",
    },
    # Fixed 2K output — the highest of any video model wired here, which matters
    # more than it sounds: face pixels are the binding constraint on whether a
    # clip can be scored at all.
    "hailuo-03": {
        "model": "hailuo-03", "image_key": "image_urls",
        "array": True, "durations": tuple(range(5, 16)), "resolutions": (),
        "label": "Hailuo 03 (2K)",
    },
    "runway-4.5": {
        "model": "runway-gen-4.5", "image_key": "image_urls",
        "array": True, "durations": (5, 10), "resolutions": (), "aspect": True,
        "label": "Runway Gen-4.5",
    },
    "seedance-2.5": {
        "model": "seedance-2.5", "image_key": "image_urls",
        "array": True, "durations": (5, 10), "resolutions": ("480p", "720p"),
        "label": "Seedance 2.5",
    },
    # 4/8/12/16/20s, one reference image, sized by aspect_ratio rather than a
    # resolution enum.
    "sora-2": {
        "model": "sora-2-official", "image_key": "image_urls",
        "array": True, "durations": (4, 8, 12, 16, 20),
        "resolutions": (), "aspect": True,
        "label": "Sora 2",
    },
}

# WAN IS REJECTED FOR THIS PROJECT — owner's decision, 2026-08-14, after seeing
# it beside Kling 2.1 on the same two stills. Not a cost or plumbing problem: the
# clips generated fine and were the cheapest of anything tested ($0.10 per 5s).
# It was rejected on how the footage LOOKS, which is the axis the gate cannot
# measure and therefore the one the owner decides. Left out of the catalogues so
# it cannot be selected by accident; the runners still understand the model
# strings if the decision is ever revisited.
DEFAULT_VIDEO_MODEL = "kling-2.1"

# Video renders in minutes, not seconds. The image budget would abandon a clip
# that is merely working, and abandoning a running task is the expensive
# failure — it finishes, it bills, and nobody fetches it.
POLL_TIMEOUT_BY_PROVIDER["poyo-video"] = 3600


# Every provider words a content refusal differently, and the difference is not
# cosmetic: generate() decides whether to RETRY (the classifier is stochastic
# near its boundary) or to give up, and it used to make that decision on the
# single substring "content_policy" — which is fal's wording and nobody else's.
#
#   fal   ... content_policy ...
#   kie   "Generation failed as the content includes sensitive information"
#
# So a kie refusal read as a hard failure: no retry, no fallback, dead job. One
# list, used by both the still and the clip path, so the next provider's phrasing
# joins it here instead of silently disabling recovery again.
_REFUSAL_MARKERS = (
    "content_policy", "sensitive", "moderation", "nsfw", "safety",
    "prohibited", "inappropriate", "flagged", "violat", "policy",
)


def is_content_refusal(exc: object) -> bool:
    """Did the provider refuse this on CONTENT, as opposed to being down?

    The distinction drives everything downstream — a refusal is worth sanitising
    and retrying, an outage is worth falling through fast — and it is also what
    the progress line tells the owner, who otherwise reads 'kie unavailable' for
    a shot that kie was perfectly available to decline.
    """
    s = str(exc).lower()
    return any(m in s for m in _REFUSAL_MARKERS)


def video_supports_end_frame(provider: str, model: str | None) -> bool:
    """Can this (provider, model) take a last frame at all?

    Asked by the endpoint so a start+end request against a start-only model is
    refused before a job is started, rather than failing minutes later inside
    the worker where the owner has already walked away from the screen.
    """
    table = KIE_VIDEO if provider == "kie" else POYO_VIDEO
    spec = table.get((model or DEFAULT_VIDEO_MODEL).strip())
    return bool(spec and spec.get("end_frame"))


def video_alternates(provider: str, model: str | None,
                     need_end_frame: bool = False) -> list[tuple[str, str]]:
    """Other (provider, model) pairs that render the SAME video model.

    kie and poyo both resell Kling and Seedance, and they run different content
    classifiers in front of them — so a clip one refuses is often one the other
    renders unchanged. Returns [] when the model is single-sourced, which is the
    honest answer for Sora, Runway and the Hailuo tiers.

    `need_end_frame` drops any alternate that cannot take a last frame. Without
    it a refused start+end clip would "recover" onto a model that ignores the end
    frame entirely, and hand back a clip that goes somewhere else — a worse
    outcome than the refusal, because it looks like success.
    """
    key = (model or DEFAULT_VIDEO_MODEL).strip()
    out: list[tuple[str, str]] = []
    for name, table in (("kie", KIE_VIDEO), ("poyo", POYO_VIDEO)):
        if name == provider or key not in table:
            continue
        if need_end_frame and not table[key].get("end_frame"):
            continue
        out.append((name, key))
    return out


def video_model(name: str | None) -> dict:
    n = (name or DEFAULT_VIDEO_MODEL).strip()
    if n in POYO_VIDEO:
        return POYO_VIDEO[n]
    for spec in POYO_VIDEO.values():
        if spec["model"] == n:
            return spec
    raise ProviderError(f"unknown video model {n!r} — known: {sorted(POYO_VIDEO)}")


def video_rows() -> list[dict]:
    return [{"id": k, "model": s["model"], "label": s["label"],
             "durations": list(s["durations"]),
             "resolutions": list(s["resolutions"]),
             # The UI shows the end-frame slot only where it is real, so the
             # capability has to travel with the catalogue rather than being a
             # hardcoded model name in the frontend.
             "end_frame": bool(s.get("end_frame"))}
            for k, s in POYO_VIDEO.items()]


def poyo_video(*, prompt: str, image: Path, model: str | None = None,
               duration: int = 5, resolution: str = "1080p",
               aspect: str = "9:16", end_image: Path | None = None,
               progress: dict | None = None) -> dict:
    """Animate one still on poyo. Returns a VIDEO envelope, not an image one.

    generate() has always unpacked r["images"][0]["url"]; a clip is deliberately
    not squeezed into that shape, because pretending a video is an image is how
    the .png destination and the PIL archive step would silently corrupt it.
    """
    key = poyo_key()
    spec = video_model(model)
    if duration not in spec["durations"]:
        raise ProviderError(f"{spec['label']} supports {spec['durations']}s, not {duration}")
    # None of poyo's catalogue takes an end frame. Refused rather than dropped —
    # see kie_video for why a silently ignored end frame is the expensive shape.
    if end_image is not None:
        raise ProviderError(f"poyo's {spec['label']} takes a start frame only; "
                            f"kie's kling-3.0 is the end-frame model")

    if progress is not None:
        progress["stage"] = "uploading the still"
    # Reference hosting is kie's uploader, exactly as the image path does —
    # poyo takes URLs only.
    url = kie_upload(_video_safe_still(image))

    inp = {"prompt": prompt, "duration": duration}
    inp[spec["image_key"]] = [url] if spec["array"] else url
    if spec["resolutions"]:
        if resolution not in spec["resolutions"]:
            raise ProviderError(f"{spec['label']} supports {spec['resolutions']}")
        inp["resolution"] = resolution
    if spec.get("aspect"):
        # Sora sizes by ratio, not by a resolution enum.
        inp["aspect_ratio"] = aspect

    if progress is not None:
        progress["stage"] = f"rendering {duration}s on {spec['label']}"
    d = _post(_POYO_SUBMIT, {"model": spec["model"], "input": inp}, key)
    task = (d.get("data") or {}).get("task_id") or d.get("task_id")
    if not task:
        raise ProviderError(f"poyo video submit: {json.dumps(d)[:200]}")

    t0 = time.time()
    budget = poll_budget("poyo-video")
    while time.time() - t0 < budget:
        time.sleep(POLL_EVERY)
        try:
            st = (_get(f"{_POYO_STATUS}/{task}", key).get("data") or {})
        except Exception:                                   # noqa: BLE001
            # A blip must not kill a paid-for render — the budget still bounds
            # the wait, and a real outage ends as a ProviderTimeout carrying the
            # task id rather than a bare URLError that loses it.
            continue
        state = st.get("status")
        if state == "failed":
            raise ProviderError(f"poyo video: {st.get('error_message') or 'failed'}")
        if state == "finished":
            f = (st.get("files") or [{}])[0]
            return {"video": {"url": f.get("file_url")},
                    "credits": st.get("credits_amount"),
                    "model": spec["model"], "duration": duration,
                    "seconds": round(time.time() - t0, 1)}
        if progress is not None and state:
            progress["stage"] = f"rendering ({state})"
    raise ProviderTimeout(f"poyo video: task {task} still running after {budget}s",
                          provider="poyo", task_id=task)


# ------------------------------------------------------------- video on kie
#
# kie carries video too, with its own spellings and its own trap: `duration` is
# a STRING here ('5'|'10'|'15'), not the integer poyo takes. Sending an int is
# rejected, and sending image_url instead of image_urls generates an unanchored
# clip — the same silent-failure shape as the still models.
KIE_VIDEO: dict[str, dict] = {
    # A THIRD spelling for the reference: not image_urls, not image_url, but
    # first_frame_url — and a string, not an array. Same silent failure if it is
    # wrong. duration is a free integer here (2-30s), unusually generous.
    "seedance-2.5": {
        "model": "bytedance/seedance-2-5", "image_key": "first_frame_url",
        "array": False, "durations": tuple(range(2, 31)),
        "resolutions": ("480p", "720p"), "duration_str": False,
        "label": "Seedance 2.5 (kie)",
    },
    # Kling on kie — the owner's preferred look, moved off poyo because poyo is
    # nearly out of credits and kie carries more Kling variants anyway.
    # image_url is a STRING here, and duration is a STRING too.
    "kling-2.1": {
        "model": "kling/v2-1-standard", "image_key": "image_url",
        "array": False, "durations": (5, 10), "resolutions": (),
        "duration_str": True, "label": "Kling 2.1 Standard (kie)",
    },
    "kling-2.1-pro": {
        "model": "kling/v2-1-pro", "image_key": "image_url",
        "array": False, "durations": (5, 10), "resolutions": (),
        "duration_str": True, "label": "Kling 2.1 Pro (kie)",
    },
    # Hailuo on kie. Its resolution enum is UPPERCASE — 768P / 1080P — while
    # every other model here takes lowercase. res_map exists for exactly this:
    # sending "1080p" is rejected, and there is no hint in the error which field
    # was wrong.
    "hailuo-2.3": {
        "model": "hailuo/2-3-image-to-video-standard", "image_key": "image_url",
        "array": False, "durations": (6, 10),
        "resolutions": ("768p", "1080p"),
        "res_map": {"768p": "768P", "1080p": "1080P",
                    "720p": "768P", "480p": "768P"},
        "duration_str": True, "label": "Hailuo 2.3 (kie)",
    },
    "hailuo-2.3-pro": {
        "model": "hailuo/2-3-image-to-video-pro", "image_key": "image_url",
        "array": False, "durations": (6, 10),
        "resolutions": ("768p", "1080p"),
        "res_map": {"768p": "768P", "1080p": "1080P",
                    "720p": "768P", "480p": "768P"},
        "duration_str": True, "label": "Hailuo 2.3 Pro (kie)",
    },
    "kling-2.5-turbo-pro": {
        "model": "kling/v2-5-turbo-image-to-video-pro", "image_key": "image_url",
        "array": False, "durations": (5, 10), "resolutions": (),
        "duration_str": True, "label": "Kling 2.5 Turbo Pro",
    },
    # The only model wired here that takes an END frame as well as a start one.
    # `image_urls` is positional: index 0 is the first frame, index 1 the last,
    # and the model interpolates between them. Two anchors instead of one is
    # strictly better for identity — the clip cannot drift away and stay away,
    # because it has to arrive somewhere specific.
    #
    # aspect_ratio is deliberately NOT sent. The schema makes it optional once
    # image_urls is present and adapts to the uploaded frames, and its enum
    # (16:9 / 9:16 / 1:1) has no 3:4 — which is every still this project shoots.
    # Sending the nearest one would letterbox or crop her.
    #
    # sound/mode/multi_shots/multi_prompt are required at the input level even in
    # plain single-shot mode, so they are pinned here rather than left out.
    "kling-3.0": {
        "model": "kling-3.0/video", "image_key": "image_urls",
        "array": True, "durations": tuple(range(3, 16)), "resolutions": (),
        "duration_str": True, "end_frame": True,
        "extra": {"sound": False, "mode": "std",
                  "multi_shots": False, "multi_prompt": []},
        "label": "Kling 3.0 (start + end frame)",
    },
}


def _video_safe_still(path: Path) -> Path:
    """A copy of the still in a format every video model accepts.

    Stills are archived as WebP, and kie's Kling rejects that outright with
    "File type not supported" — no mention of which file or which field. Image
    models take WebP happily, so this only bites on the video path.

    JPEG rather than PNG, and not merely for tidiness: a 3584x4800 still is 1.0MB
    as WebP, 10.6MB as PNG and 1.9MB as JPEG. kie_upload sends base64, adding
    33%, so the PNG would arrive as 14.1MB against JPEG's 2.6MB — and poyo
    enforces a 10MB input ceiling. PNG would have silently started failing on
    the larger stills.

    The original archive is never touched.
    """
    if path.suffix.lower() in (".jpg", ".jpeg", ".png"):
        return path
    import tempfile
    from PIL import Image
    out = Path(tempfile.gettempdir()) / f"vidsrc-{path.stem}.jpg"
    if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
        with Image.open(path) as im:
            im.convert("RGB").save(out, "JPEG", quality=92)
    return out

def kie_video_model(name: str | None) -> dict:
    n = (name or "seedance-2.5").strip()
    if n in KIE_VIDEO:
        return KIE_VIDEO[n]
    for spec in KIE_VIDEO.values():
        if spec["model"] == n:
            return spec
    raise ProviderError(f"kie has no video model {n!r} — known: {sorted(KIE_VIDEO)}")


def kie_video(*, prompt: str, image: Path, model: str | None = None,
              duration: int = 5, resolution: str = "1080p",
              end_image: Path | None = None,
              progress: dict | None = None) -> dict:
    """Animate one still on kie. Same video envelope as poyo_video.

    `end_image` is the LAST frame, on the models that take one. Passing it to a
    model that does not is refused rather than dropped: a silently ignored end
    frame renders a perfectly ordinary clip that simply does not arrive where it
    was told to, and bills in full for it — the same silent-substitution shape
    this module keeps designing around.
    """
    key = kie_key()
    spec = kie_video_model(model)
    if duration not in spec["durations"]:
        raise ProviderError(f"{spec['label']} supports {spec['durations']}s, not {duration}")
    if end_image is not None and not spec.get("end_frame"):
        raise ProviderError(
            f"{spec['label']} takes a start frame only — "
            f"{sorted(k for k, s in KIE_VIDEO.items() if s.get('end_frame'))} take an end frame")

    if progress is not None:
        progress["stage"] = "uploading the end frame" if end_image else "uploading the still"
    urls = [kie_upload(_video_safe_still(image))]
    if end_image is not None:
        # Order is the contract: index 0 is where the clip starts, index 1 is
        # where it has to end up. Reversing them runs the motion backwards.
        urls.append(kie_upload(_video_safe_still(end_image)))

    inp = {"prompt": prompt,
           "duration": str(duration) if spec["duration_str"] else duration}
    inp[spec["image_key"]] = urls if spec["array"] else urls[0]
    if spec["resolutions"]:
        if resolution not in spec["resolutions"]:
            raise ProviderError(f"{spec['label']} supports {spec['resolutions']}")
        # Some models spell the tier differently (Hailuo wants 1080P, not 1080p).
        inp["resolution"] = (spec.get("res_map") or {}).get(resolution, resolution)
    inp.update(spec.get("extra") or {})     # fields kie marks required

    if progress is not None:
        progress["stage"] = f"rendering {duration}s on {spec['label']}"
    d = _post(_KIE_CREATE, {"model": spec["model"], "input": inp}, key)
    if d.get("code") != 200:
        raise ProviderError(f"kie video createTask: {d.get('msg')}")
    task = d["data"]["taskId"]

    t0 = time.time()
    budget = poll_budget("poyo-video")      # video budgets are about video, not vendor
    while time.time() - t0 < budget:
        time.sleep(POLL_EVERY)
        try:
            st = (_get(f"{_KIE_POLL}?taskId={task}", key).get("data") or {})
        except Exception:                                   # noqa: BLE001
            continue                        # a blip must not abandon a paid render
        state = st.get("state")
        if state == "fail":
            raise ProviderError(f"kie video: {st.get('failMsg') or 'failed'} "
                                f"({st.get('failCode')})")
        if state == "success":
            urls = json.loads(st["resultJson"])["resultUrls"]
            return {"video": {"url": urls[0]},
                    "credits": st.get("creditsConsumed"),
                    "model": spec["model"], "duration": duration,
                    "seconds": round((st.get("costTime") or 0) / 1000, 1)}
        if progress is not None and state:
            progress["stage"] = f"rendering ({state})"
    raise ProviderTimeout(f"kie video: task {task} still running after {budget}s",
                          provider="kie", task_id=task)


VIDEO_RUNNERS = {"poyo": poyo_video, "kie": kie_video}


def video_catalogue() -> dict:
    return {"poyo": video_rows(),
            "kie": [{"id": k, "model": s["model"], "label": s["label"],
                     "durations": list(s["durations"]),
                     "resolutions": list(s["resolutions"]),
                     "end_frame": bool(s.get("end_frame"))}
                    for k, s in KIE_VIDEO.items()]}


# ---------------------------------------------------- kie runway (legacy API)
#
# Runway is NOT a /market/ model on kie — it lives on its own older API with its
# own base path, camelCase fields and its own poll endpoint. Nothing about the
# createTask/recordInfo shape applies, which is why it gets its own runner
# rather than another row in KIE_VIDEO.
_KIE_RUNWAY_GEN = "https://api.kie.ai/api/v1/runway/generate"
_KIE_RUNWAY_POLL = "https://api.kie.ai/api/v1/runway/record-detail"


def kie_runway_video(*, prompt: str, image: Path, model: str | None = None,
                     duration: int = 5, resolution: str = "720p",
                     end_image: Path | None = None,
                     progress: dict | None = None) -> dict:
    """Runway on kie's legacy endpoint. Same video envelope as the others."""
    key = kie_key()
    if duration not in (5, 10):
        raise ProviderError(f"runway supports 5 or 10s, not {duration}")
    if end_image is not None:
        raise ProviderError("runway here takes a start frame only; "
                            "kie's kling-3.0 is the end-frame model")
    quality = resolution if resolution in ("720p", "1080p") else "720p"

    if progress is not None:
        progress["stage"] = "uploading the still"
    url = kie_upload(_video_safe_still(image))

    if progress is not None:
        progress["stage"] = f"rendering {duration}s on Runway"
    body = {"prompt": prompt, "imageUrl": url, "duration": duration,
            "quality": quality, "aspectRatio": "vertical", "waterMark": ""}
    d = _post(_KIE_RUNWAY_GEN, body, key)
    if d.get("code") != 200:
        raise ProviderError(f"kie runway: {d.get('msg')}")
    task = (d.get("data") or {}).get("taskId")
    if not task:
        raise ProviderError(f"kie runway: no taskId in {json.dumps(d)[:160]}")

    t0 = time.time()
    budget = poll_budget("poyo-video")
    while time.time() - t0 < budget:
        time.sleep(POLL_EVERY)
        try:
            st = (_get(f"{_KIE_RUNWAY_POLL}?taskId={task}", key).get("data") or {})
        except Exception:                                   # noqa: BLE001
            continue
        flag = st.get("successFlag")
        if flag in (2, 3, "2", "3"):
            raise ProviderError(f"kie runway: {st.get('errorMessage') or 'failed'}")
        if flag in (1, "1"):
            info = st.get("response") or st
            vurl = info.get("videoUrl") or (info.get("resultUrls") or [None])[0]
            if not vurl:
                raise ProviderError(f"kie runway: finished with no url {json.dumps(st)[:160]}")
            return {"video": {"url": vurl}, "credits": st.get("creditsConsumed"),
                    "model": "runway-gen-4.5 (kie)", "duration": duration,
                    "seconds": round(time.time() - t0, 1)}
        if progress is not None:
            progress["stage"] = f"rendering (runway {flag})"
    raise ProviderTimeout(f"kie runway: task {task} still running after {budget}s",
                          provider="kie", task_id=task)


VIDEO_RUNNERS["kie-runway"] = kie_runway_video
