"""Generation via fal, and the bookkeeping that makes a run reviewable.

Every run records the EXACT prompt, the references, the pose, the seed and the
gate's verdict. A generation you can't reproduce is an anecdote.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import fal_client

from . import config, db, gate
from .config import (ARCHIVE_FORMAT, ARCHIVE_QUALITY, GPT_IMAGE, GPT_IMAGE_SIZE,
                     IMAGES, LOCAL_ENDPOINT, LOCAL_PY, LOCAL_WORKER, RESOLUTION,
                     SCENE_EDIT, SCENE_TEXT2IMG)

# The pipeline was rebuilt around nano-banana-pro as the PRIMARY generator: it
# renders the full figure range gpt-image-2's moderation refuses, and the
# identity/gallery is recalibrated natively on nano so its self-agreement is high
# (a model matches its own renderings far better than a foreign one's). gpt-image-2
# stays available as an explicit endpoint but is no longer the default.
PRIMARY_EDIT = SCENE_EDIT
PRIMARY_T2I = SCENE_TEXT2IMG


def _runs() -> list[dict]:
    return db.runs_all()


def upload(path: Path) -> str:
    """Upload a reference to fal, downscaling oversized ones first.

    ⚠ fal's CDN URLs are public and unauthenticated.

    Our generated references are full-res nano outputs (~20 MB each). Sending two
    of them as input (face @image1 + body @image2, ~40 MB) stalls fal's
    upload/generate call — the wardrobe-generation hang. A reference is read at
    modest resolution, so capping the longest side to 2048px preserves identity
    and proportions while cutting each payload to well under 1 MB. Small files go
    up untouched; any failure falls back to the raw upload so this can never
    break a generation.
    """
    p = Path(path)
    try:
        if p.stat().st_size < 4_000_000:
            return fal_client.upload_file(str(p))
        from PIL import Image
        im = Image.open(p).convert("RGB")
        im.thumbnail((2048, 2048))
        tmp = IMAGES / f"_up_{uuid.uuid4().hex[:8]}.jpg"
        im.save(tmp, quality=92)
        try:
            return fal_client.upload_file(str(tmp))
        finally:
            tmp.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 — downscaling must never fail a generation
        return fal_client.upload_file(str(p))


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


def archive(dest: Path) -> Path:
    """Re-encode a finished download to the archive format. Returns the kept file.

    Runs AFTER the gate, deliberately. The recorded verdict is then computed on
    the pristine 4K download, so the number in the db is never a number about a
    re-encode — even though it was measured not to matter (see config).

    Best-effort by design: if anything goes wrong the original PNG stays and the
    row keeps pointing at it. A shot that generated fine must never be lost to a
    space optimisation.
    """
    if not ARCHIVE_QUALITY or dest.suffix.lower() == f".{ARCHIVE_FORMAT}":
        return dest
    out = dest.with_suffix(f".{ARCHIVE_FORMAT}")
    try:
        from PIL import Image
        with Image.open(dest) as im:
            im.convert("RGB").save(out, ARCHIVE_FORMAT.upper(),
                                   quality=ARCHIVE_QUALITY, method=4)
        # Only drop the original once the replacement is on disk and plausible.
        if out.stat().st_size < 10_000:
            out.unlink(missing_ok=True)
            return dest
        dest.unlink(missing_ok=True)
        return out
    except Exception:  # noqa: BLE001 — keep the PNG, keep the shot
        out.unlink(missing_ok=True)
        return dest


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


# gpt-image-2's moderation classifier is non-deterministic NEAR its boundary
# (the airport look: refused 3/3 then accepted 4/4 on a byte-identical prompt),
# so a content_policy refusal is retried — it may be a coin flip. But an input
# image that is genuinely OVER the line (e.g. a short, tight, cutout outfit
# turnaround) refuses every single time, and four ~2-minute attempts turned a
# refusal into a 9-minute dead spin. Two retries keep the coin-flip rescue while
# failing a hard refusal in roughly a third of the time.
CONTENT_RETRIES = 2

# Hard ceilings so a stalled fal call (a hung queue, an oversized ref the model
# chokes on) fails the job with a reason instead of spinning forever. START is
# how long we wait to even leave fal's queue; CLIENT is the total wall-clock for
# one attempt.
#
# CLIENT_TIMEOUT was 300, chosen when "a 4-panel wardrobe turnaround is the
# slowest real request at ~2 min, so 5 min never trips a legitimate generation".
# That stopped being true. Measured over one afternoon's fal requests:
#
#     median 312s    p90 659s    max 659s
#     4 of 8 requests exceeded the 300s ceiling
#
# The ceiling had drifted BELOW the median, so half of all generations were
# being abandoned after fal had already made and billed them. Three calibration
# faces and a wardrobe turnaround were lost that way in a single session, each
# recoverable only by hand out of fal's request history.
#
# So: 15 minutes, comfortably past p90. And a timeout is no longer fatal —
# _reclaim() below asks fal for the result the client stopped waiting for.
START_TIMEOUT = 180      # seconds to leave the queue before giving up
CLIENT_TIMEOUT = 900     # seconds total for one subscribe() attempt

# How long to keep asking fal for a result our client timed out on. The image is
# already paid for at that point, so patience here is free and giving up is not.
RECLAIM_TIMEOUT = 900
RECLAIM_POLL = 10
# How many times to try pulling the finished image before giving up and parking
# it for refetch. The generation is already paid for by then, so a transient
# stall is worth another connection: three attempts cost minutes, one lost image
# costs a generation and, if it is a calibration face, a whole calibration run.
DOWNLOAD_ATTEMPTS = 3


_REQ_ID = re.compile(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b")


def _reclaim(exc: Exception, endpoint: str, progress: dict | None):
    """A client timeout is not a lost generation — ask fal for it.

    fal_client.subscribe() gives up after CLIENT_TIMEOUT and raises, throwing
    away a request that is still running and will still be billed. But the
    exception names the request id, and fal keeps the result: fal_client.result()
    fetches it once it lands.

    So a timeout becomes "wait longer" instead of "pay again". Returns the result
    payload, or None if there is no request id to chase or fal genuinely failed.

    This exists because 50% of one afternoon's requests exceeded the old ceiling
    and every one of them had to be recovered by hand from fal's request history.
    """
    m = _REQ_ID.search(str(exc))
    if not m:
        return None
    req_id = m.group(1)
    deadline = time.monotonic() + RECLAIM_TIMEOUT
    while time.monotonic() < deadline:
        if progress is not None:
            progress["stage"] = "still running on fal — waiting"
        try:
            return fal_client.result(endpoint, req_id)
        except Exception:  # noqa: BLE001 — not ready yet, or a real failure
            pass
        time.sleep(RECLAIM_POLL)
    return None


def _download(url: str, dest, rid: str) -> None:
    """Pull one finished image, with a TOTAL wall-clock budget on the read loop.

    urlopen's timeout is PER socket read, not total — a connection that trickles
    a few bytes inside each window never trips it and hangs the worker for
    minutes (observed: stuck 'downloading' at 250s+ with a 120s timeout). So the
    deadline is enforced here rather than left to the socket.

    Raises RuntimeError on a stall or a truncated file, and leaves nothing
    behind: a truncated image gates as no_face, which looks identical to identity
    drift — a dead connection recorded as a model failure.
    """
    import urllib.request as _u
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    with _u.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as resp, open(dest, "wb") as fh:
        while True:
            if time.monotonic() > deadline:
                fh.close()
                dest.unlink(missing_ok=True)
                raise RuntimeError(f"download timed out after {DOWNLOAD_TIMEOUT}s "
                                   f"(stalled/slow connection to fal) ({rid})")
            chunk = resp.read(262144)   # 256 KB
            if not chunk:
                break
            fh.write(chunk)
    if dest.stat().st_size < 10_000:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"truncated download ({rid})")

DOWNLOAD_TIMEOUT = 240   # total seconds for the result image download. 4K results
                         # are ~18-20 MB; on a slow link to fal's CDN, 120s wasn't
                         # enough and shots failed on download. Total wall-clock
                         # bound (see the read loop), so a real stall still fails.


def generate(*, prompt: str, system: str = "", refs: list[Path] | None = None,
             aspect: str = "4:5", seed: int | None = None,
             pose_file: Path | None = None, meta: dict | None = None,
             session: dict | None = None, endpoint: str | None = None,
             extra: dict | None = None, progress: dict | None = None,
             fallback_endpoint: str | None = None,
             resolution: str | None = None, gated: bool = True,
             character: str | None = None,
             safety_tolerance: str | int | None = None) -> dict:
    """One generation, gated and recorded.

    gated=False for output that is not a photo OF her — a wardrobe turnaround is
    a garment swatch, and only its clothing is ever used downstream. Scoring one
    is not a measurement: the sheet holds four faces, `analyze` embeds whichever
    panel renders the largest, and in a full-body panel that face lands near
    200px — under every floor that makes a number mean anything. Measured over
    118 turnarounds: 116 rejected, every one of them for face size, mean 0.483.
    A gate that cannot pass a thing by construction should not be judging it.

    refs order matters and is the caller's responsibility. Measured on the
    previous build: an identity reference plus ONE face crop scored 0.860, where
    three face crops scored 0.547. More references don't add identity, they add
    things to blend. A pose image spends one of those slots.

    fallback_endpoint: if the primary endpoint refuses on content_policy for
    every retry, run ONCE on this endpoint instead. gpt-image-2 and nano-banana
    have different moderation, so a revealing outfit that gpt-image-2 rejects
    outright still renders on nano — at weaker identity (~0.68 vs 0.81), which is
    why the served endpoint is recorded on the row (`moderation_fallback`).
    """
    refs = refs or []
    rid = uuid.uuid4().hex[:10]
    # Pin the character NOW — a mid-render switch must not misfile this. An
    # explicit `character` pins it harder still: IMAGES is a live proxy onto
    # whoever is active, so a long job (character creation makes a dozen images
    # over ~15 minutes) would otherwise write its later images into whichever
    # character the user clicked on meanwhile. Callers that own a character for
    # the length of a job pass it; everything else keeps the active one.
    owner = character or config.get_active()
    dest = config.char_base(owner) / "images" / f"{rid}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    primary = endpoint or (PRIMARY_EDIT if refs else PRIMARY_T2I)

    if primary == LOCAL_ENDPOINT:
        return _generate_local(rid, dest, prompt=prompt, system=system,
                               refs=refs, seed=seed, session=session,
                               pose_file=pose_file, meta=meta, extra=extra,
                               gated=gated)

    # Upload refs ONCE and reuse the URLs across both endpoints — re-uploading
    # for the fallback would double the cost and latency for nothing.
    image_urls = [upload(p) for p in refs] if refs else []

    def build_args(ep: str) -> dict:
        # Arguments are per-endpoint. fal ignores foreign fields rather than
        # rejecting them, which is worse than an error: send nano-banana's
        # aspect_ratio/resolution to gpt-image-2 and you get a default-sized
        # image while believing you asked for 4K, and the face-pixel count
        # silently drops below the gate's floor.
        if ep in GPT_IMAGE:
            # gpt-image takes prompt + image_urls. No system_prompt: the realism
            # rules ride inside the prompt itself.
            a = {"prompt": f"{system}\n\n{prompt}" if system else prompt,
                 "image_size": GPT_IMAGE_SIZE}
        else:
            a = {"prompt": prompt, "aspect_ratio": aspect,
                 "resolution": resolution or RESOLUTION,
                 "num_images": 1, "output_format": "png"}
            if system:
                a["system_prompt"] = system
            # fal exposes a documented moderation dial on every one of its major
            # image endpoints — 1 strictest, 6 least strict, default 4 on nano.
            # We had never set it, so every request went out on the default and a
            # legitimate commercial category (intimates) was refused without the
            # provider's own control ever being tried.
            #
            # Explicitly opt-in per request, NOT a raised global default: the
            # right level depends on what is being shot, the default is right for
            # nearly everything, and a quiet platform-wide loosening is not a
            # decision that should live in a config constant. Recorded on the run
            # so it is always visible what a given image was made under.
            #
            # This is the provider's setting, offered for the caller to choose.
            # It does not widen what fal's terms permit, and the content still has
            # to be within them.
            if safety_tolerance:
                a["safety_tolerance"] = str(safety_tolerance)
        if image_urls:
            a["image_urls"] = image_urls
        if seed is not None:
            a["seed"] = seed
        if extra:
            a |= extra
        return a

    # Try the primary endpoint (with coin-flip retries); on a persistent
    # content_policy refusal, drop to the fallback endpoint once.
    plan = [(primary, CONTENT_RETRIES)]
    if fallback_endpoint and fallback_endpoint != primary:
        plan.append((fallback_endpoint, 1))

    t0 = time.time()
    r = None
    used_ep = primary
    last = None
    for ep, tries in plan:
        falling_back = ep != primary
        for attempt in range(tries):
            try:
                if progress is not None:
                    progress["stage"] = ("scene-model fallback" if falling_back
                                         else "generating")
                r = fal_client.subscribe(ep, arguments=build_args(ep),
                                         with_logs=False,
                                         start_timeout=START_TIMEOUT,
                                         client_timeout=CLIENT_TIMEOUT)
                used_ep = ep
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
                if "content_policy" in str(exc):
                    # Surface the retry so it reads as "retrying", not a silent
                    # hang — the confusion the user hit before.
                    if progress is not None:
                        progress["retry"] = attempt + 1
                        progress["stage"] = ("scene-model moderation retry"
                                             if falling_back
                                             else "moderation retry")
                    continue
                # A TIMEOUT is not a failure, it is impatience. The request is
                # still running on fal and will still be billed, so go and get
                # it rather than raising and losing a paid generation.
                if "timed out" in str(exc).lower():
                    reclaimed = _reclaim(exc, ep, progress)
                    if reclaimed is not None:
                        r, used_ep = reclaimed, ep
                        break
                raise
        if r is not None:
            break
    if r is None:
        raise last

    moderation_fallback = used_ep != primary
    if progress is not None:
        progress["stage"] = "downloading"
    # A bounded download. urlopen's timeout is PER socket read, not total — a
    # connection that trickles a few bytes inside each window never trips it and
    # hangs the worker for minutes (observed: stuck 'downloading' at 250s+ with a
    # 120s timeout). Enforce a TOTAL wall-clock budget on the read loop so a slow
    # or stalled transfer fails cleanly and the shot can be retried.
    source_url = r["images"][0]["url"]

    # RETRY, then RECORD. The image is already made and already paid for by the
    # time this line runs; everything after it is a local plumbing problem, and a
    # plumbing problem must never destroy a generation.
    #
    # It did, once: twelve calibration faces for one character all failed here
    # with "stalled/slow connection to fal", and because the row is only written
    # AFTER a successful download, the URL died with the exception. The
    # source_url field exists precisely so a missing file can be re-fetched for
    # free instead of regenerated for money — and the one case it was for was the
    # one case it was not saved. They were recovered by hand out of fal's request
    # history, which is not a recovery procedure anybody should need.
    err = None
    for attempt in range(DOWNLOAD_ATTEMPTS):
        if attempt and progress is not None:
            progress["stage"] = f"downloading (retry {attempt})"
        try:
            _download(source_url, dest, rid)
            err = None
            break
        # OSError covers urllib's URLError and HTTPError; RuntimeError is our own
        # stall/truncation. Catching only the latter would have let a plain
        # network error skip the parking below — the exact hole this whole change
        # exists to close, reopened one line lower.
        except (RuntimeError, OSError) as exc:
            err = exc
            dest.unlink(missing_ok=True)
    if err is not None:
        # Park a row carrying the URL so /api/runs/refetch can finish the job.
        # `file` names a path that is deliberately NOT on disk, which is exactly
        # the shape /api/runs/missing already looks for.
        db.runs_insert({
            "id": rid, "session": session or new_session("ad-hoc"),
            "file": dest.name, "source_url": source_url, "endpoint": used_ep,
            "moderation_fallback": moderation_fallback, "prompt": prompt,
            "system": system, "refs": [p.name for p in refs],
            "pose": pose_file.name if pose_file else None, "seed": seed,
            "aspect": aspect, "resolution": resolution or RESOLUTION,
            "seconds": round(time.time() - t0, 1),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "auto_leveled": 0.0, "mark": None, "meta": meta or {},
            "verdict": {"status": "error",
                        "reason": f"{err} — image is on fal, refetch to recover"},
        }, character_id=owner)
        raise RuntimeError(f"{err}; the image was generated and its URL is saved "
                           f"— recover it from Review > missing images ({rid})")

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
        # Where the bytes came from. Kept so a file that goes missing — an
        # interrupted download, a disk tidy, a half-finished sync — can be
        # RE-FETCHED for free instead of regenerated for money. fal serves these
        # from public v3b.fal.media URLs; if one has expired the refetch fails
        # honestly rather than silently costing a generation.
        "source_url": source_url,
        "endpoint": used_ep,
        # True = the primary endpoint refused on content_policy and this image
        # came from the fallback (scene) model instead. Identity is weaker there
        # (~0.68 vs 0.81); the flag makes that visible rather than a silent swap.
        "moderation_fallback": moderation_fallback,
        "safety_tolerance": str(safety_tolerance) if safety_tolerance else None,
        "prompt": prompt,
        "system": system,
        "refs": [p.name for p in refs],
        "pose": pose_file.name if pose_file else None,
        "seed": seed,
        "aspect": aspect,
        "resolution": resolution or RESOLUTION,
        "seconds": round(time.time() - t0, 1),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "auto_leveled": leveled,   # degrees rotated to straighten her head
        "mark": None,          # human decision: approve / reject / None
        "meta": meta or {},
    }

    # Gate it if a gallery exists. No gallery yet is the normal state during a
    # seed hunt — that is not an error, it is the phase before there is a her.
    if not gated:
        row["verdict"] = {"status": "ungated",
                          "reason": "not a photo of her — only its clothing is used"}
    else:
        try:
            # A collaboration is judged as a CAST: every named character scored
            # against her own gallery, plus how alike the faces are to each
            # other. One branch, so a solo shot takes exactly the path it always
            # did.
            cast = (meta or {}).get("cast")
            row["verdict"] = (gate.check_cast(dest, cast) if cast
                              else gate.check(dest)).dict()
        except FileNotFoundError:
            row["verdict"] = {"status": "ungated", "reason": "gallery is empty"}
        except gate.NoFaceFound as exc:
            row["verdict"] = {"status": "no_face", "reason": str(exc)[:120]}
        except ValueError as exc:
            row["verdict"] = {"status": "error", "reason": str(exc)[:120]}

    # A shot asked to be imperfect is expected to score low: blur and a half-caught
    # expression degrade the geometry the embedding is built on. Marking the verdict
    # keeps that number out of any later read on drift — the same separation the
    # gate draws between a framing confound and a real identity miss.
    if (meta or {}).get("expected_low"):
        row["verdict"]["expected_low"] = True

    # Shrink last: the verdict above was scored on the pristine download, and the
    # row must name whatever file actually survives.
    row["file"] = archive(dest).name

    db.runs_insert(row, character_id=owner)   # atomic + pinned to the owning character
    return row


def _generate_local(rid, dest, *, prompt, system, refs, seed, session,
                    pose_file, meta, extra, gated: bool = True) -> dict:
    """Drive the local SDXL worker in its own venv as a subprocess.

    The identity reference is the FIRST ref — IP-Adapter takes one face image.
    A pose image, if present, is ignored here (SDXL IP-Adapter has no pose slot
    yet); that is a known gap, not a silent drop — recorded in the row.
    """
    if not refs:
        raise RuntimeError("local generation needs a face reference")
    owner = config.get_active()   # pin the character for this record
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
    if not gated:
        row["verdict"] = {"status": "ungated",
                          "reason": "not a photo of her — only its clothing is used"}
    else:
        try:
            # A collaboration is judged as a CAST: every named character scored
            # against her own gallery, plus how alike the faces are to each
            # other. One branch, so a solo shot takes exactly the path it always
            # did.
            cast = (meta or {}).get("cast")
            row["verdict"] = (gate.check_cast(dest, cast) if cast
                              else gate.check(dest)).dict()
        except FileNotFoundError:
            row["verdict"] = {"status": "ungated", "reason": "gallery is empty"}
        except gate.NoFaceFound as exc:
            row["verdict"] = {"status": "no_face", "reason": str(exc)[:120]}
        except ValueError as exc:
            row["verdict"] = {"status": "error", "reason": str(exc)[:120]}

    # A shot asked to be imperfect is expected to score low: blur and a half-caught
    # expression degrade the geometry the embedding is built on. Marking the verdict
    # keeps that number out of any later read on drift — the same separation the
    # gate draws between a framing confound and a real identity miss.
    if (meta or {}).get("expected_low"):
        row["verdict"]["expected_low"] = True

    # Shrink last: the verdict above was scored on the pristine download, and the
    # row must name whatever file actually survives.
    row["file"] = archive(dest).name

    db.runs_insert(row, character_id=owner)   # atomic + pinned to the owning character
    return row


def mark(run_id: str, decision: str | None) -> dict:
    """Human verdict. Distinct from the gate's — the gate measures her face; a
    human is the only thing that can judge her BODY, since person re-ID keys on
    clothing and clothing varies by design."""
    for r in _runs():
        if r["id"] == run_id:
            r["mark"] = decision
            return db.runs_update(run_id, r)
    raise KeyError(run_id)


def all_runs() -> list[dict]:
    return list(reversed(_runs()))


def delete_runs(ids: set[str]) -> list[dict]:
    """Remove runs by id from the ledger; return the removed rows so the caller
    can delete their image files. The ledger and disk are cleaned together."""
    return db.runs_delete(set(ids))


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
    # `stage` is owned by generate() and gets overwritten on every call
    # ("downloading", "leveling & gating"). A job that makes SEVERAL generations —
    # guided creation building ten home corners — needs somewhere to say which one
    # it is on that the next generate() will not clobber. That is `step`: set by
    # the job function, never by generate().
    out["step"] = j.get("step")
    out["retry"] = j.get("retry")
    out["elapsed"] = j.get("elapsed", round(_now() - j["started"], 1))
    return out


def all_jobs() -> list[dict]:
    """Every job still in memory, newest first — so a stuck generation is
    inspectable (id, stage, how long it has been running) instead of an
    invisible spinner. Omits the heavy `run` row; poll /api/jobs/{id} for that."""
    out = []
    for j in JOBS.values():
        out.append({
            "id": j["id"], "label": j["label"], "stage": j["stage"],
            "done": j["done"], "error": j.get("error"), "retry": j.get("retry"),
            "elapsed": j.get("elapsed", round(_now() - j["started"], 1)),
        })
    out.sort(key=lambda x: x["elapsed"])   # shortest-running first; oldest last
    return out
