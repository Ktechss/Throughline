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


def kie_credits() -> float | None:
    """Remaining balance, or None if it cannot be read. 24 credits per 4K edit,
    so this is roughly 'generations left times 24'."""
    try:
        return float(_get(_KIE_CREDIT, kie_key())["data"])
    except Exception:                                     # noqa: BLE001
        return None


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


def kie_generate(*, prompt: str, refs: list[Path], aspect: str, resolution: str,
                 progress: dict | None = None) -> dict:
    """Render on kie and return fal's response shape: {"images": [{"url": ...}]}.

    generate() unpacks r["images"][0]["url"] and knows nothing else about who
    made it, so matching that shape is the whole of the integration.
    """
    key = kie_key()
    if progress is not None:
        progress["stage"] = "uploading references"
    urls = [kie_upload(p) for p in refs]

    if progress is not None:
        progress["stage"] = "generating"
    d = _post(_KIE_CREATE,
              {"model": "nano-banana-pro",
               # NOT image_urls — that is poyo's name for it. kie calls the
               # reference array image_input, and silently generates without
               # references if you send the wrong key.
               "input": {"prompt": prompt, "image_input": urls,
                         "aspect_ratio": aspect, "resolution": resolution,
                         "output_format": "png"}},
              key)
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
                    "seconds": round((st.get("costTime") or 0) / 1000, 1)}
        if progress is not None and state:
            progress["stage"] = f"generating ({state})"
    raise ProviderError(f"kie: task {task} did not finish in {POLL_TIMEOUT}s")
