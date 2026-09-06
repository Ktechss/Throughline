"""Generation via fal, and the bookkeeping that makes a run reviewable.

Every run records the EXACT prompt, the references, the pose, the seed and the
gate's verdict. A generation you can't reproduce is an anecdote.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

import fal_client

from . import config, db, gate
from .config import (ARCHIVE_FORMAT, ARCHIVE_QUALITY, GPT_IMAGE, GPT_IMAGE_SIZE,
                     IMAGES, PROVIDER, RESOLUTION,
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
    # A BROWSER USER-AGENT, because kie's result CDN 403s urllib's default.
    #
    # fal's CDN does not care, so this went unnoticed until the first real kie
    # shot: the image generated, 24 credits were spent, and the download died
    # with "HTTP Error 403: Forbidden". Same bot filter that sits in front of
    # kie's uploader, which providers.py already works around — the download
    # path is fal-era code and never got the same treatment.
    #
    # Recoverable only because source_url is parked on the row before the
    # download is attempted. That design note now has a second real case.
    req = _u.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _u.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, open(dest, "wb") as fh:
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
             meta: dict | None = None,
             session: dict | None = None, endpoint: str | None = None,
             extra: dict | None = None, progress: dict | None = None,
             fallback_endpoint: str | None = None,
             resolution: str | None = None, gated: bool = True,
             character: str | None = None,
             safety_tolerance: str | int | None = None,
             provider: str | None = None,
             model: str | None = None,
             run_id: str | None = None,
             client_token: str | None = None) -> dict:
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
    # The caller may hand us the id it already told the client about, so the job
    # id, the run id, the image filename and the idempotency record are all ONE
    # identifier. uuid4().hex[:10] is 40 bits; a collision used to surface as an
    # IntegrityError out of runs_insert AFTER the image was paid for and
    # downloaded. Full hex costs nothing and removes that entirely.
    rid = run_id or uuid.uuid4().hex
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

    # RESERVE THE ROW BEFORE THE MONEY. Everything from here to the insert at
    # the bottom used to be a hole: the provider renders and bills, and a crash
    # anywhere in between left no row, no task id and no file. See
    # db.runs_reserve. Written with the request's inputs, which are the part
    # worth keeping if the rest never arrives.
    db.runs_reserve(rid, owner, {
        "id": rid, "status": "pending", "client_token": client_token,
        "session": session or new_session("ad-hoc"),
        "file": dest.name, "prompt": prompt, "system": system,
        "refs": [p.name for p in refs],
        # `seed_requested` is what the caller asked for; `seed` stays None until
        # a provider confirms it actually used one. A pending row must not claim
        # a seed that may never be honoured.
        "seed_requested": seed, "seed": None, "aspect": aspect,
        "resolution": resolution or RESOLUTION,
        "endpoint": primary, "model": model, "provider": provider,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mark": None, "meta": meta or {},
        "verdict": {"status": "pending", "reason": "generation in flight"},
    })

    # WHO RENDERS THIS. Same model, same picture, different bill — measured on
    # one prompt with three references at 4K, scored on her own gallery:
    #
    #     fal   0.4304  $0.30            66s
    #     kie   0.4267  $0.12 (24 cr)   220s
    #     poyo  0.4426  $0.175 (35 cr)  265s
    #
    # A 0.016 spread is inside the seed-to-seed variance this project sees on
    # identical prompts, so kie is the same picture for 40% of the money. fal
    # stays reachable per-call and stays the fallback, because it is 3x faster
    # and because a second provider is only an asset while the first still works.
    #
    # kie replaces exactly one step: submit a prompt plus reference URLs, get an
    # image URL. Everything below — the download retry, the source_url parking,
    # auto-level, the gate, the row — is provider-agnostic and untouched.
    # The CHAIN, in the owner's chosen order (Settings), skipping anything
    # disabled or missing its key. Each is tried in turn and a failure costs
    # latency, not the shot; fal is the end of every chain because it is the
    # dearest and the one that works when the cheap ones queue or refuse.
    from . import providers
    if provider:
        chain = [provider.lower()]
    else:
        chain = providers.chain()

    # Resolve the model to a CONCRETE name before walking the chain.
    #
    # It used to be resolved inside kie_generate, which meant a project DEFAULT
    # (providers.load_model) never reached the other providers: generate() passed
    # a bare None, poyo's "do I carry this?" guard is `if model and ...`, so None
    # sailed straight past it and poyo rendered nano-banana-pro. With poyo first
    # in the chain the owner set the default to seedream, watched 35 credits a
    # shot leave the account, and got nano — the dearest route, and not the model
    # they picked. Resolving here means every provider is asked about the model
    # that was actually requested, and the ones that do not carry it decline and
    # fall through instead of silently substituting.
    model = model or providers.load_model()

    r, use, _prov_error = None, "fal", None
    # EVERY provider's complaint, not just the last one. The chain kept only the
    # final error, so on 2026-08-25 a kie "aspect_ratio is not within the range
    # of allowed options" and a poyo failure were both discarded and the caller
    # was shown fal's content_policy_violation — sending the diagnosis into a
    # moderation problem that did not exist, twice, across two models.
    _prov_errors: list[str] = []
    # Tasks we stopped waiting on. They are still running, still billing, and
    # recoverable via providers.reclaim() — see /api/runs/reclaim.
    _pending: list[dict] = []
    if refs:
        for name in chain:
            run_it = providers.RUNNERS.get(name)
            if run_it is None:          # "fal" — handled by the block below
                use = "fal"
                break
            try:
                if progress is not None:
                    progress["stage"] = f"generating on {name}"
                r = run_it(prompt=prompt, refs=refs, aspect=aspect,
                           resolution=resolution or RESOLUTION, progress=progress,
                           model=model, seed=seed)
                use = name
                # Refresh the cached balance now that credits have actually been
                # spent, so the sidebar drops immediately instead of showing a
                # stale figure for up to a minute after the shot it paid for.
                if name == "kie":
                    try:
                        providers.kie_credits(force=True)
                    except Exception:                       # noqa: BLE001
                        pass
                break
            except providers.ProviderTimeout as exc:
                # NOT a failure — the task is still running and will finish and
                # bill. Falling through now pays a second provider for the same
                # picture and abandons the first, which is the expensive half of
                # this. Park the id so it can be reclaimed, then carry on so the
                # owner still gets a shot.
                _pending.append({"provider": exc.provider, "task_id": exc.task_id,
                                 "model": model})
                _prov_error = f"{name}: {exc}"
                _prov_errors.append(_prov_error)
                if progress is not None:
                    progress["stage"] = f"{name} slow — parked, trying next"
                continue
            except providers.ProviderError as exc:
                _prov_error = f"{name}: {exc}"
                _prov_errors.append(_prov_error)
                if progress is not None:
                    progress["stage"] = f"{name} unavailable — trying next"
                continue

    # Upload refs ONCE and reuse the URLs across both endpoints — re-uploading
    # for the fallback would double the cost and latency for nothing.
    image_urls = [upload(p) for p in refs] if (refs and r is None) else []

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
    # What ACTUALLY rendered this, not a constant. This was hardcoded to
    # "kie/nano-banana-pro" for every reseller run, so a row could say
    # endpoint='kie/nano-banana-pro' while model='seedream/5-pro-image-to-image'
    # — the two fields on the same row contradicting each other. Verified on a
    # live run before this change.
    used_ep = primary if r is None else f"{use}/{(r or {}).get('model') or model or 'nano-banana-pro'}"
    last = None
    for ep, tries in (plan if r is None else []):
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
                # Was `"content_policy" in str(exc)` — fal's wording and nobody
                # else's. Shared with the clip path now, so a provider that says
                # "sensitive" or "flagged" still earns its retries.
                if providers.is_content_refusal(exc):
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
        # `last` is None only if the loop never ran, which now happens when kie
        # failed AND the fal plan was skipped — surface kie's message rather
        # than a bare TypeError.
        # Say what EVERY provider said. The last one to be tried is rarely the
        # one that explains the failure.
        if _prov_errors:
            trail = " | ".join(_prov_errors)
            if last is not None:
                raise RuntimeError(f"{trail} | fal: {last}") from last
            raise RuntimeError(trail)
        raise last or RuntimeError("no provider produced an image")

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
        # PATCH, not insert: the row was reserved before the provider call.
        # It also carries pending_tasks now, which the old parking row omitted —
        # so /api/runs/reclaim said "no parked provider task on this run" for
        # exactly the rows that had one, and the sweeper's reclaim branch never
        # fired for them.
        db.runs_patch(
            rid, status="parked", source_url=source_url, endpoint=used_ep,
            provider=use, credits=(r or {}).get("credits"),
            model=(r or {}).get("model") or model,
            moderation_fallback=moderation_fallback,
            pending_tasks=_pending or None,
            seconds=round(time.time() - t0, 1), auto_leveled=0.0,
            verdict={"status": "error",
                     "reason": f"{err} — image is on fal, refetch to recover"})
        raise RuntimeError(f"{err}; the image was generated and its URL is saved "
                           f"— recover it from Review > missing images ({rid})")

    if progress is not None:
        progress["stage"] = "leveling & gating"
    leveled = auto_level(dest)   # deterministic tilt correction, before gating

    # The MEASURED size of what actually arrived, not the size that was asked
    # for. The row already carries `aspect` and `resolution`, but those are the
    # REQUEST — and the request is not the picture. config.py records the
    # incident: nano returned a 1024x768 landscape master face with a 306px
    # subject and "the run row recorded aspect 3:4 / 4K, so nothing looked
    # wrong". A silent default-shaped image currently leaves no trace anywhere.
    #
    # It is also what makes a native row distinguishable from an upscaled file
    # later: face_px is a raw bbox width in the pixel space of whatever was
    # scored, so it is only comparable against the corpus alongside the
    # dimensions it was measured in.
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(dest) as _im:
            img_w, img_h = _im.size
    except Exception:                                     # noqa: BLE001
        img_w = img_h = None      # never lose a generated shot to bookkeeping

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
        # THE SEED THAT WAS ACTUALLY USED, which is not always the one asked
        # for. The resellers take no seed parameter, so a seeded request used to
        # render unseeded while the row recorded the seed anyway — every one of
        # the 365 rows on this machine claims `seed: None`, and a user who set
        # one would have been told it was honoured. A provider now reports back
        # what it used; anything else records None.
        "seed_requested": seed,
        # WHO rendered it and what they charged. Without this the provider
        # comparison is unrepeatable: a run's endpoint alone cannot tell you
        # whether 0.61 came from fal at $0.30 or kie at $0.12.
        "provider": use,
        "credits": (r or {}).get("credits"),
        # Providers we abandoned mid-flight; each is a paid-for image still
        # reachable by task id until its result expires.
        "pending_tasks": _pending or None,
        # Measured, not requested — see the comment at the Image.open above.
        "width": img_w, "height": img_h,
        # Which model rendered it — None means fal/nano. Without this every
        # cross-renderer comparison built on the runs table silently mixes them.
        "model": (r or {}).get("model"),
        # True = the primary endpoint refused on content_policy and this image
        # came from the fallback (scene) model instead. Identity is weaker there
        # (~0.68 vs 0.81); the flag makes that visible rather than a silent swap.
        "moderation_fallback": moderation_fallback,
        "safety_tolerance": str(safety_tolerance) if safety_tolerance else None,
        "prompt": prompt,
        "system": system,
        "refs": [p.name for p in refs],
        "seed": (r or {}).get("seed") if use != "fal" else seed,
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
            # `character=owner`, not the active character: this runs in a
            # background thread minutes after the request that started it, and
            # the gallery + threshold are CharPath proxies. check_cast already
            # scores each member against her own gallery; the solo path was the
            # one place still asking "whoever is active right now".
            row["verdict"] = (gate.check_cast(dest, cast) if cast
                              else gate.check(dest, character=owner)).dict()
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

    # IS IT A PHOTOGRAPH — measured separately, and stored separately.
    #
    # ⚠ This is not part of the identity number and must never be added to it. A
    # good capture score does not make a picture her; a good similarity does not
    # make it a photograph. It lives under its own key so that a later read on
    # one axis cannot accidentally sweep in the other, the same quarantine the
    # upscale rows and the video frames get.
    #
    # Failure here is never allowed to lose a generation that already cost money:
    # the image is downloaded and gated by this point, and a metric is not worth
    # a run record.
    try:
        from . import capture as _capture
        _cap = _capture.measure(dest)            # once — it runs the detector
        row["verdict"]["capture"] = {**_cap.dict(), "framing": _cap.framing}
        _d = _capture.distance(_cap, owner)
        if _d:
            row["verdict"]["capture"]["distance"] = _d
    except Exception as exc:                     # noqa: BLE001 — see above
        row["verdict"]["capture"] = {"error": str(exc)[:120]}

    # Shrink last: the verdict above was scored on the pristine download, and the
    # row must name whatever file actually survives.
    row["file"] = archive(dest).name

    # PATCH the reserved row rather than inserting a second one. `status` moving
    # to complete is what tells the sweeper this one needs nothing.
    row["status"] = "complete"
    db.runs_patch(rid, **row)
    return row


def mark(run_id: str, decision: str | None) -> dict:
    """Human verdict. Distinct from the gate's — the gate measures her face; a
    human is the only thing that can judge her BODY, since person re-ID keys on
    clothing and clothing varies by design."""
    # A single-field patch under the write lock. The old form loaded every run,
    # edited one dict and wrote the WHOLE document back, so a mark could both
    # lose to and be lost by the sweeper. Writing only `mark` means the two can
    # no longer overwrite each other's work.
    if not any(r["id"] == run_id for r in _runs()):
        raise KeyError(run_id)
    return db.runs_patch(run_id, mark=decision)


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

# ------------------------------------------------------------------ job events
#
# Polling worked but was lossy and loud: eight hand-rolled loops in the frontend
# at 1-3s each, every completion firing an 11-endpoint refresh, and — because
# the poll loops swallowed errors and rescheduled unconditionally — a backend
# restart left tabs hammering /api/jobs/{gone} at 1.5s forever.
#
# SSE rather than WebSocket: this is strictly one-way status text, and SSE keeps
# the things that matter here for free — the browser reconnects on its own, it
# is plain HTTP through the Vite proxy, and it is curl-able. The polling
# endpoint stays as the fallback and as the reattach primitive.
_LOOP = None                                    # set in main's lifespan
_LISTENERS: dict[str, set] = {}
_LISTENER_LOCK = threading.Lock()


def bind_loop(loop) -> None:
    """Hand the worker threads a way back onto the event loop."""
    global _LOOP
    _LOOP = loop


def subscribe(jid: str):
    import asyncio
    q = asyncio.Queue(maxsize=64)
    with _LISTENER_LOCK:
        _LISTENERS.setdefault(jid, set()).add(q)
    return q


def unsubscribe(jid: str, q) -> None:
    with _LISTENER_LOCK:
        qs = _LISTENERS.get(jid)
        if qs:
            qs.discard(q)
            if not qs:
                _LISTENERS.pop(jid, None)


def _publish(jid: str) -> None:
    """Called from the WORKER thread on every mutation of a job."""
    if _LOOP is None:
        return
    with _LISTENER_LOCK:
        qs = list(_LISTENERS.get(jid, ()))
    if not qs:
        return
    snap = job_status(jid)
    for q in qs:
        try:
            _LOOP.call_soon_threadsafe(q.put_nowait, snap)
        except Exception:       # noqa: BLE001 — a dead listener must not kill a job
            pass


class _Job(dict):
    """A job dict that announces its own changes.

    Subclassing the dict rather than adding publish() calls at each of the ~10
    `job["stage"] = ...` sites in this module and main.py: those are written by
    whoever adds a new job type, and one forgotten call is a stream that goes
    silent halfway with no error.
    """

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        jid = self.get("id")
        if jid:
            _publish(jid)


def _now() -> float:
    return time.time()


def start_job(label: str, fn, jid: str | None = None) -> str:
    """Run fn() (which returns a run row) in a thread, tracked in JOBS.

    `jid` lets the caller supply the id it will also use as the run id, so the
    job and the row it produces share one identifier. Without that there was no
    way to go from a finished row back to the job that made it, or from a job
    id to its row — they were independent uuids that never met.
    """
    jid = jid or uuid.uuid4().hex[:8]
    JOBS[jid] = _Job({"id": jid, "label": label, "stage": "starting",
                      "started": _now(), "done": False, "error": None,
                      "run": None})

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
            # elapsed BEFORE done: a listener woken by done=True must not read a
            # job whose elapsed is still being computed.
            j["elapsed"] = round(_now() - j["started"], 1)
            j["done"] = True
            _reap()

    threading.Thread(target=worker, daemon=True).start()
    return jid


# Keep finished jobs around long enough for a client that was mid-poll (or
# mid-reconnect) to still read the terminal state, then let them go. JOBS was
# never pruned at all: every job ever started stayed resident holding its full
# run row (a shot's prompt alone is ~4.5 KB), and all_jobs() plus
# backup._guard_jobs walked the whole history on every call.
JOB_TTL_S = 3600
JOB_KEEP = 200


def _reap() -> None:
    now = _now()
    done = [(j.get("started", now), jid) for jid, j in list(JOBS.items())
            if j.get("done")]
    stale = [jid for started, jid in done if now - started > JOB_TTL_S]
    # Age first, then a hard cap so a burst cannot outrun the TTL.
    if len(done) - len(stale) > JOB_KEEP:
        for _, jid in sorted(done)[:len(done) - len(stale) - JOB_KEEP]:
            stale.append(jid)
    for jid in stale:
        with _LISTENER_LOCK:
            if jid in _LISTENERS:        # someone is still watching; leave it
                continue
        JOBS.pop(jid, None)


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


# ------------------------------------------------------------------- video
#
# Deliberately NOT routed through generate(). That function has "one still" wired
# in at six points — the .png destination, the num_images/output_format request
# args, the r["images"][0]["url"] unpack, the PIL archive, the PIL dimension
# probe and the gate call — and branching all six to carry a clip would put the
# still path, which works, at risk for the sake of the one that does not exist
# yet.
#
# What IS shared is everything that turned out to be format-agnostic: the
# download loop, source_url parking, the runs row, session grouping and the job
# threading. Those are reused as-is.
DOWNLOAD_TIMEOUT_VIDEO = 900   # a 10s 1080p clip is far larger than a 4K still


def generate_video(*, still: Path, prompt: str, model: str | None = None,
                   duration: int = 5, resolution: str = "1080p",
                   provider: str = "poyo", end_still: Path | None = None,
                   character: str | None = None, session: dict | None = None,
                   progress: dict | None = None, meta: dict | None = None,
                   source_run: str | None = None) -> dict:
    """Animate an already-approved still. Returns the run row.

    `still` must be a shot that already carries a verdict — see /api/video, which
    refuses an ungated one. That refusal is the whole design: the approved image
    becomes frame one, so identity is inherited rather than re-argued.
    """
    from . import providers

    owner = character or config.get_active()
    rid = uuid.uuid4().hex[:10]
    dest = config.char_base(owner) / "images" / f"{rid}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    session = session or new_session("video")

    if providers.VIDEO_RUNNERS.get(provider) is None:
        raise RuntimeError(f"no video runner for {provider!r} — "
                           f"have {sorted(providers.VIDEO_RUNNERS)}")

    # The motion prompt gets the SAME sanitiser as a shot prompt. It did not
    # before, which left a hole exactly where one was least expected: the still
    # path neutralises "sensual/seductive/cleavage" inside compose_tagged,
    # while a clip's prompt is typed (or now AI-written) and went to the provider
    # untouched. Reported on the row, so a rewrite is never silent.
    from . import prompt as promptlib
    prompt, sanitised = promptlib.sanitise(prompt)

    # A content refusal is worth retrying: the classifiers sit near a stochastic
    # boundary (measured on stills — 3/3 refused then 4/4 accepted on byte-
    # identical text), and kie and poyo run DIFFERENT ones in front of the same
    # Kling weights. So try again here, then try whoever else carries this model.
    # An outage still falls through immediately; only refusals earn the retries.
    plan = [(provider, model, CONTENT_RETRIES)]
    plan += [(p, m, 1) for p, m in providers.video_alternates(
        provider, model, need_end_frame=end_still is not None)]

    r, refusals, tried = None, [], []
    for prov, mod, tries in plan:
        run_it = providers.VIDEO_RUNNERS[prov]
        for attempt in range(tries):
            try:
                if progress is not None and (prov != provider or attempt):
                    progress["stage"] = (f"{prov} declined the content — "
                                         f"{'retrying' if prov == provider else f'trying {prov}'}")
                r = run_it(prompt=prompt, image=still, model=mod,
                           duration=duration, resolution=resolution,
                           end_image=end_still, progress=progress)
                provider, model = prov, mod      # whoever actually rendered it
                break
            except providers.ProviderError as exc:
                if prov not in tried:
                    tried.append(prov)
                if not providers.is_content_refusal(exc):
                    raise            # an outage, a bad key, a rejected duration
                refusals.append(f"{prov}: {exc}")
        if r is not None:
            break

    if r is None:
        # Say what was actually tried. "Blocked" reads as a bug the owner can
        # fix in the prompt; naming the providers that all declined the same
        # frame is what points at the STILL instead — every one of these runs a
        # classifier on the uploaded first frame too, not only on the words.
        raise RuntimeError(
            f"every provider refused this clip on content ({', '.join(tried)}). "
            f"The wording was already sanitised, so the first frame itself is the "
            f"likely trigger — try a different still, or a different model. "
            f"Last: {refusals[-1] if refusals else 'no detail'}")

    source_url = (r.get("video") or {}).get("url")
    if not source_url:
        raise RuntimeError("provider returned no video URL")

    row = {
        "id": rid, "session": session, "file": dest.name,
        "source_url": source_url, "endpoint": "", "provider": provider,
        "model": r.get("model"), "credits": r.get("credits"),
        # `kind` is what every consumer branches on — the runs table is an opaque
        # JSON blob so this needs no migration, and without it the review grid
        # would hand an mp4 to PIL and 500.
        "kind": "video", "duration": r.get("duration", duration),
        "resolution": resolution, "aspect": "",
        "width": None, "height": None,
        # Both anchors are references — the clip is derived from each of them,
        # and a start+end row that recorded only its opening frame would lose
        # half of what produced it.
        "prompt": prompt, "system": "",
        "refs": [still.name] + ([end_still.name] if end_still else []),
        "pose": None, "seed": None, "auto_leveled": 0.0, "mark": None,
        "seconds": r.get("seconds"),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        # `sanitised` is the same contract the shot detail already renders, so a
        # rewritten motion prompt shows up in the UI with no frontend change.
        "meta": {**(meta or {}), "video": True, "from_run": source_run,
                 "still": still.name, "sanitised": sanitised,
                 "end_still": end_still.name if end_still else None,
                 "refused_by": tried if r is not None and tried else None},
        # Frame scoring is Phase 2. Until then a clip is honestly unmeasured
        # rather than falsely clean — and its verdict must never be confused with
        # a still's, which is why the reason says so.
        "verdict": {"status": "ungated",
                    "reason": "video — frame scoring not yet applied"},
    }

    if progress is not None:
        progress["stage"] = "downloading the clip"
    try:
        _download(source_url, dest, rid)
    except Exception as exc:                                # noqa: BLE001
        # Same parking contract as a still: the clip exists and is paid for, so
        # the row keeps its URL and /api/runs/refetch can finish the job.
        row["verdict"] = {"status": "error",
                          "reason": f"{exc} — clip is on {provider}, refetch to recover"}
        db.runs_insert(row, character_id=owner)
        raise RuntimeError(f"{exc}; the clip was generated and its URL is saved "
                           f"— recover it from Review > missing ({rid})")

    row["seconds"] = round(time.time() - t0, 1)
    db.runs_insert(row, character_id=owner)
    return row
