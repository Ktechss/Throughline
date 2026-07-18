"""Generation via fal, and the bookkeeping that makes a run reviewable.

Every run records the EXACT prompt, the references, the pose, the seed and the
gate's verdict. A generation you can't reproduce is an anecdote.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import fal_client

from . import gate
from .config import (EDIT, GPT_IMAGE, GPT_IMAGE_SIZE, IMAGES, LOCAL_ENDPOINT,
                     LOCAL_PY, LOCAL_WORKER, RESOLUTION, RUNS_PATH, TEXT2IMG)


def _runs() -> list[dict]:
    return json.loads(RUNS_PATH.read_text()) if RUNS_PATH.exists() else []


def _save_runs(rows: list[dict]) -> None:
    RUNS_PATH.write_text(json.dumps(rows, indent=2) + "\n")


def upload(path: Path) -> str:
    """⚠ fal's CDN URLs are public and unauthenticated."""
    return fal_client.upload_file(str(path))


# Rotating the finished image levels the FACE by tilting the whole SCENE the
# other way — the floor, the horizon, her body all lean. That is a cheat, not a
# straight-head POSE, and on any shot with a visible horizon it reads as a
# mistake. So we do NOT do it as a real correction.
#
# The legitimate lever for an upright head is the LEVELED REFERENCE: the model
# copies the reference's head orientation, so a level reference yields a level
# head in a level scene. That is probabilistic (it lands ~3 deg, which is a
# natural head, not a tilt), and gpt-image-2 has no pose input to make it exact.
# True deterministic head-pose control needs the local ControlNet/OpenPose path.
#
# We keep ONE tiny use of rotation: cleaning up a sub-CLEANUP_MAX residual, where
# the scene tilt is genuinely imperceptible even against a horizon. Anything
# larger is LEFT ALONE and flagged `tilted` (see gate) — regenerate rather than
# tilt the world.
AUTOLEVEL_DEADBAND = 1.5     # below this, not worth touching
AUTOLEVEL_CLEANUP_MAX = 3.5  # above this, do NOT rotate — flag for regen instead


def auto_level(dest: Path) -> float:
    """DISABLED. Returns 0 — the image is never rotated or cropped.

    Rotating to level the face tilts the scene and crops the frame, which the
    owner (rightly) rejected. We do NOT touch the delivered image. Head tilt is
    handled where it belongs — at generation, via the upright reference — and
    reported by the gate's roll/`tilted` fields so a too-tilted shot can be
    regenerated. Left here as a no-op so the call sites and the recorded
    `auto_leveled: 0` stay stable; re-enable only behind an explicit opt-in.
    """
    return 0.0


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
             extra: dict | None = None, progress: dict | None = None) -> dict:
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

    if ep == LOCAL_ENDPOINT:
        return _generate_local(rid, dest, prompt=prompt, system=system,
                               refs=refs, seed=seed, session=session,
                               pose_file=pose_file, meta=meta, extra=extra)

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

    # gpt-image-2's moderation classifier is non-deterministic near its
    # boundary: an airport look (short shorts + heels + a body line + a close
    # crop) sits right on it and the SAME prompt flips accepted/refused call to
    # call. Measured: refused 3/3, then accepted 4/4, minutes apart. So a
    # content_policy refusal is retried rather than surfaced — it is a coin
    # flip, not a verdict on the prompt. A genuinely disallowed prompt refuses
    # every time and still raises after the retries are spent.
    t0 = time.time()
    last = None
    for attempt in range(4):
        try:
            r = fal_client.subscribe(ep, arguments=args, with_logs=False)
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
            if "content_policy" in str(exc) and attempt < 3:
                # Surface the moderation retry so it reads as "retrying", not a
                # silent hang — the confusion the user hit before.
                if progress is not None:
                    progress["retry"] = attempt + 1
                    progress["stage"] = "moderation retry"
                continue
            raise
    else:  # pragma: no cover - loop always breaks or raises
        raise last
    if progress is not None:
        progress["stage"] = "downloading"
    urllib.request.urlretrieve(r["images"][0]["url"], dest)

    # A truncated download gates as no_face, which looks identical to identity
    # drift — a dead connection recorded as a model failure.
    if dest.stat().st_size < 10_000:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"truncated download ({rid})")

    if progress is not None:
        progress["stage"] = "leveling & gating"
    leveled = auto_level(dest)   # deterministic tilt correction, before gating

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
        "auto_leveled": leveled,   # degrees rotated to straighten her head
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


def _generate_local(rid, dest, *, prompt, system, refs, seed, session,
                    pose_file, meta, extra) -> dict:
    """Drive the local SDXL worker in its own venv as a subprocess.

    The identity reference is the FIRST ref — IP-Adapter takes one face image.
    A pose image, if present, is ignored here (SDXL IP-Adapter has no pose slot
    yet); that is a known gap, not a silent drop — recorded in the row.
    """
    if not refs:
        raise RuntimeError("local generation needs a face reference")
    face = refs[0]
    job = {"prompt": f"{system}\n\n{prompt}" if system else prompt,
           "face": str(face), "out": str(dest),
           "width": GPT_IMAGE_SIZE["width"], "height": GPT_IMAGE_SIZE["height"],
           "seed": seed}
    if extra:
        job |= {k: v for k, v in extra.items()
                if k in ("steps", "ip_scale", "cfg", "width", "height")}

    job_path = dest.with_suffix(".job.json")
    job_path.write_text(json.dumps(job))
    t0 = time.time()
    proc = subprocess.run([str(LOCAL_PY), str(LOCAL_WORKER), str(job_path)],
                          capture_output=True, text=True, cwd=str(LOCAL_WORKER.parent.parent))
    job_path.unlink(missing_ok=True)
    if proc.returncode != 0 or not dest.exists():
        tail = (proc.stderr or proc.stdout or "")[-400:]
        raise RuntimeError(f"local worker failed: {tail}")

    worker = {}
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            worker = json.loads(line[7:])

    leveled = auto_level(dest)

    row = {
        "id": rid, "session": session or new_session("local"),
        "auto_leveled": leveled,
        "file": dest.name, "endpoint": LOCAL_ENDPOINT, "prompt": prompt,
        "system": system, "refs": [p.name for p in refs],
        "pose": pose_file.name if pose_file else None, "seed": seed,
        "aspect": f"{job['width']}x{job['height']}",
        "resolution": f"{job['width']}x{job['height']}",
        "seconds": worker.get("seconds", round(time.time() - t0, 1)),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cost_usd": 0.0, "mark": None, "meta": meta or {},
    }
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


# --------------------------------------------------------------------------
# async jobs — so the UI knows a generation is alive and how long it's taken
# --------------------------------------------------------------------------
#
# fal is a single blocking ~70s call (local is ~5 min); a synchronous endpoint
# leaves the UI staring at a dead button with no idea if anything is happening.
# generate() runs in a thread and reports coarse stages into JOBS; the frontend
# polls and shows an elapsed timer + stage, so "is it working?" always has an
# answer. The stages are honest — we cannot see inside fal's call, so it is
# generating -> gating -> done, plus explicit retry visibility for the
# moderation coin-flip that used to look like a silent hang.

import threading  # noqa: E402

JOBS: dict[str, dict] = {}


def _now() -> float:
    return time.time()


def start_job(label: str, fn) -> str:
    """Run fn() (which returns a run row) in a thread, tracked in JOBS."""
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"id": jid, "label": label, "stage": "starting",
                 "started": _now(), "done": False, "error": None, "run": None}

    def worker():
        j = JOBS[jid]
        try:
            j["stage"] = "generating"
            row = fn(j)          # fn may update j["stage"] / j["retry"]
            j["run"] = row
            j["stage"] = "done"
        except Exception as exc:  # noqa: BLE001
            j["error"] = str(exc)[:300]
            j["stage"] = "failed"
        finally:
            j["done"] = True
            j["elapsed"] = round(_now() - j["started"], 1)

    threading.Thread(target=worker, daemon=True).start()
    return jid


def job_status(jid: str) -> dict | None:
    j = JOBS.get(jid)
    if not j:
        return None
    out = {k: j[k] for k in ("id", "label", "stage", "done", "error", "run")}
    out["retry"] = j.get("retry")
    out["elapsed"] = j.get("elapsed", round(_now() - j["started"], 1))
    return out
