"""Generation via fal, and the bookkeeping that makes a run reviewable.

Every run records the EXACT prompt, the references, the pose, the seed and the
gate's verdict. A generation you can't reproduce is an anecdote.
"""

from __future__ import annotations

import json
import time
import urllib.request
import uuid
from pathlib import Path

import fal_client

from . import gate
from .config import (EDIT, GPT_IMAGE, GPT_IMAGE_SIZE, IMAGES, RESOLUTION,
                     RUNS_PATH, TEXT2IMG)


def _runs() -> list[dict]:
    return json.loads(RUNS_PATH.read_text()) if RUNS_PATH.exists() else []


def _save_runs(rows: list[dict]) -> None:
    RUNS_PATH.write_text(json.dumps(rows, indent=2) + "\n")


def upload(path: Path) -> str:
    """⚠ fal's CDN URLs are public and unauthenticated."""
    return fal_client.upload_file(str(path))


def new_session(label: str = "") -> dict:
    """One trigger = one session.

    A session groups the images produced by a single decision, so the review
    grid shows "these four came from the same config" instead of a wall of
    undifferentiated output. Comparing two images from different sessions
    without knowing it is how you conclude a model is better when you actually
    changed the reference.
    """
    return {"id": uuid.uuid4().hex[:8], "label": label,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S")}


def generate(*, prompt: str, system: str = "", refs: list[Path] | None = None,
             aspect: str = "4:5", seed: int | None = None,
             pose_file: Path | None = None, meta: dict | None = None,
             session: dict | None = None, endpoint: str | None = None,
             extra: dict | None = None) -> dict:
    """One generation, gated and recorded.

    refs order matters and is the caller's responsibility. Measured on the
    previous build: an identity reference plus ONE face crop scored 0.860, where
    three face crops scored 0.547. More references don't add identity, they add
    things to blend. A pose image spends one of those slots.
    """
    refs = refs or []
    rid = uuid.uuid4().hex[:10]
    dest = IMAGES / f"{rid}.png"
    ep = endpoint or (EDIT if refs else TEXT2IMG)

    # Arguments are per-endpoint. fal ignores foreign fields rather than
    # rejecting them, which is worse than an error: send nano-banana's
    # aspect_ratio/resolution to gpt-image-2 and you get a default-sized image
    # while believing you asked for 4K, and the face-pixel count silently drops
    # below the gate's floor.
    if ep in GPT_IMAGE:
        # gpt-image takes prompt + image_urls. It has no system_prompt: the
        # realism rules have to ride inside the prompt itself.
        args = {"prompt": f"{system}\n\n{prompt}" if system else prompt,
                "image_size": GPT_IMAGE_SIZE}
        if refs:
            args["image_urls"] = [upload(p) for p in refs]
    else:
        args = {
            "prompt": prompt,
            "aspect_ratio": aspect,
            "resolution": RESOLUTION,
            "num_images": 1,
            "output_format": "png",
        }
        if system:
            args["system_prompt"] = system
        if refs:
            args["image_urls"] = [upload(p) for p in refs]
    if seed is not None:
        args["seed"] = seed
    if extra:
        args |= extra

    t0 = time.time()
    r = fal_client.subscribe(ep, arguments=args, with_logs=False)
    urllib.request.urlretrieve(r["images"][0]["url"], dest)

    # A truncated download gates as no_face, which looks identical to identity
    # drift — a dead connection recorded as a model failure.
    if dest.stat().st_size < 10_000:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"truncated download ({rid})")

    row = {
        "id": rid,
        # Every image belongs to exactly one session. Defaulting to a fresh one
        # means a caller that forgets still gets grouping, never a merge with
        # someone else's run.
        "session": session or new_session("ad-hoc"),
        "file": dest.name,
        "endpoint": ep,
        "prompt": prompt,
        "system": system,
        "refs": [p.name for p in refs],
        "pose": pose_file.name if pose_file else None,
        "seed": seed,
        "aspect": aspect,
        "resolution": RESOLUTION,
        "seconds": round(time.time() - t0, 1),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mark": None,          # human decision: approve / reject / None
        "meta": meta or {},
    }

    # Gate it if a gallery exists. No gallery yet is the normal state during a
    # seed hunt — that is not an error, it is the phase before there is a her.
    try:
        row["verdict"] = gate.check(dest).dict()
    except FileNotFoundError:
        row["verdict"] = {"status": "ungated", "reason": "gallery is empty"}
    except gate.NoFaceFound as exc:
        row["verdict"] = {"status": "no_face", "reason": str(exc)[:120]}
    except ValueError as exc:
        row["verdict"] = {"status": "error", "reason": str(exc)[:120]}

    rows = _runs()
    rows.append(row)
    _save_runs(rows)
    return row


def mark(run_id: str, decision: str | None) -> dict:
    """Human verdict. Distinct from the gate's — the gate measures her face; a
    human is the only thing that can judge her BODY, since person re-ID keys on
    clothing and clothing varies by design."""
    rows = _runs()
    for r in rows:
        if r["id"] == run_id:
            r["mark"] = decision
            _save_runs(rows)
            return r
    raise KeyError(run_id)


def all_runs() -> list[dict]:
    return list(reversed(_runs()))
