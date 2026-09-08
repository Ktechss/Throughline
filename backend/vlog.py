"""A vlog: plan it for nothing, then spend on it deliberately.

Two spends per beat — a 9:16 still, then the clip made from that still — because
every kie video model is image-to-video and none of them takes an aspect ratio,
so the clip is the shape of its start frame. That doubles the cost of a mistake
and is the reason `plan()` and `estimate()` exist at all: the whole shot list is
priced and inspectable before a single credit moves.

WHAT THIS DELIBERATELY DOES NOT DO. It does not invent a price for a clip.
Video prices are unpublished — providers.py says plainly "Read credits_amount
off the status response; do not assume" — and poyo's own page was wrong by 2.5x.
So `estimate()` reports the still cost exactly (that is known per model) and the
clip cost as MEASURED, from clips this project has actually run, or as unknown.
An estimate that quietly invents the expensive half is worse than no estimate,
because it is the half that decides whether a plan is affordable.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import statistics
import subprocess
from pathlib import Path

from . import db, vlog_data

# kie bills in credits and one credit is $0.005 — confirmed against the ledger
# rather than a pricing page: seedream-5-lite charged 5.5 credits against a
# listed usd_4k of 0.0275, and nano-banana-pro charged 24.0 against 0.12. Both
# exact. See providers.CATALOGUE for the per-provider note.
KIE_CREDIT_USD = 0.005

# A vlog is vertical. Not a preference — the still decides the clip's shape, so
# this is the one setting that cannot be fixed later.
ASPECT = "9:16"


def _db() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db.DB_PATH}?mode=ro", uri=True)


def measured_clip_cost(model: str | None = None) -> dict:
    """What a clip has ACTUALLY cost, from the ledger. None until one has run.

    Returns {"usd": float|None, "n": int, "by_model": {...}}. The caller must be
    able to say "unknown" — see the module docstring for why inventing a number
    here would be the worst possible place to guess.
    """
    per: dict[str, list[float]] = {}
    try:
        with _db() as c:
            for (doc,) in c.execute("select doc from runs"):
                d = json.loads(doc)
                if (d.get("kind") or "") != "video":
                    continue
                cr = d.get("credits")
                if cr is None:
                    continue
                per.setdefault(str(d.get("model") or "?"), []).append(
                    float(cr) * KIE_CREDIT_USD)
    except sqlite3.Error:
        return {"usd": None, "n": 0, "by_model": {}}

    by_model = {m: {"usd": round(statistics.median(v), 4), "n": len(v)}
                for m, v in per.items()}
    if model and model in by_model:
        return {"usd": by_model[model]["usd"], "n": by_model[model]["n"],
                "by_model": by_model}
    flat = [x for v in per.values() for x in v]
    return {"usd": round(statistics.median(flat), 4) if flat else None,
            "n": len(flat), "by_model": by_model}


def still_cost(model_key: str) -> float | None:
    """What one still costs on a given image model, from the registry."""
    from .registry import REGISTRY
    from . import vendors  # noqa: F401 — registers the models

    spec = REGISTRY.model(model_key)
    return None if spec is None else float(spec.usd_4k)


def plan(shape: str | None = None, beat_ids: list[str] | None = None, *,
         place: str = "", idea: str = "") -> list[dict]:
    """Resolve a shape name or an explicit beat list into a shot list.

    Every entry says what it NEEDS, not what it is: `needs_still` is the 9:16
    frame to make, `gated` says whether that frame has to clear her threshold,
    and `motion` is what the video model is told afterwards. A caller can
    reorder, drop or duplicate entries freely — this returns data, not a
    commitment.
    """
    beats = (vlog_data.shape(shape) if shape
             else [b for b in (vlog_data.beat(i) for i in (beat_ids or [])) if b])

    out = []
    for i, b in enumerate(beats):
        # The place rides on the STILL, never on the motion: the video model is
        # animating a frame that already contains the street, and telling it
        # about a location it can see is how a clip acquires a second street.
        needs = b["still"]
        if place and not b["subject"]:
            needs = f"{needs} The location is {place}."
        elif place:
            needs = f"{needs} She is in {place}."
        if idea and b["subject"]:
            needs = f"{needs} {idea}"

        out.append({
            "n": i + 1,
            "id": b["id"], "label": b["label"], "group": b["group"],
            "camera": b["camera"],
            # `subject` and `gated` are the same fact said twice on purpose: one
            # is about the picture, the other about what the pipeline does with
            # it, and the second is the expensive one.
            "subject": b["subject"],
            "gated": b["subject"],
            "seconds": b["seconds"],
            "aspect": ASPECT,
            "needs_still": needs,
            "motion": b["motion"],
            # Filled in as the plan is executed.
            "still_run": None, "clip_run": None, "status": "planned",
        })
    return out


def estimate(shot_list: list[dict], *, still_model: str = "seedream-5-lite",
             clip_model: str | None = None) -> dict:
    """Price the whole plan before anything is spent.

    Honest about the half it cannot know. `clip_usd` is None until this project
    has actually run a clip, and `total_usd` is then a FLOOR — the stills only —
    with `complete: False` saying so. A caller that renders a floor as if it
    were a total is the failure this is shaped to prevent.
    """
    s_each = still_cost(still_model)
    measured = measured_clip_cost(clip_model)
    c_each = measured["usd"]

    n_stills = len(shot_list)
    n_clips = len(shot_list)
    n_gated = sum(1 for b in shot_list if b["gated"])
    seconds = sum(b["seconds"] for b in shot_list)

    stills_usd = None if s_each is None else round(s_each * n_stills, 4)
    clips_usd = None if c_each is None else round(c_each * n_clips, 4)

    total = None
    if stills_usd is not None:
        total = stills_usd + (clips_usd or 0.0)

    return {
        "beats": len(shot_list), "seconds": seconds,
        "stills": n_stills, "clips": n_clips,
        # The gated stills are the ones that can FAIL and be re-shot, so they
        # are the ones a budget actually has to carry twice.
        "gated_stills": n_gated, "ungated_stills": n_stills - n_gated,
        "still_model": still_model, "still_usd_each": s_each,
        "stills_usd": stills_usd,
        "clip_usd_each": c_each, "clips_usd": clips_usd,
        "clip_samples": measured["n"], "clip_by_model": measured["by_model"],
        "total_usd": None if total is None else round(total, 4),
        # False means total_usd is a FLOOR: the clips are not in it.
        "complete": clips_usd is not None,
        "note": ("clip prices are measured, not published — this total is the "
                 "stills only until a clip has run"
                 if clips_usd is None else
                 f"clip cost is the median of {measured['n']} measured run(s)"),
    }


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError(
            "ffmpeg is not on PATH — it is what joins the clips. "
            "Install it (brew install ffmpeg) and try again.")
    return exe


def probe_size(clip: Path) -> tuple[int, int] | None:
    """(width, height) of a clip, or None if ffprobe cannot say."""
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    r = subprocess.run(
        [exe, "-v", "error", "-select_streams", "v", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, timeout=60)
    try:
        w, h = r.stdout.strip().split("\n")[0].split(",")[:2]
        return int(w), int(h)
    except Exception:                                       # noqa: BLE001
        return None


def stitch(clips: list[Path], dest: Path, *, width: int | None = None,
           height: int | None = None, fps: int = 30) -> Path:
    """Join clips in order into one vertical file.

    Re-encodes rather than using the concat demuxer. The demuxer is faster and
    would be right if every clip were identical, but these come back from
    different models at whatever size and frame rate that model returns, and it
    fails or produces a broken file when they differ. Scaling every input to one
    canvas first is the version that cannot silently produce something unplayable.

    Video only. Nothing here generates sound, and a silent track is honest;
    inventing one is not.
    """
    clips = [Path(c) for c in clips]
    missing = [c.name for c in clips if not c.is_file()]
    if missing:
        raise RuntimeError(f"these clips are not on disk: {', '.join(missing)}")
    if not clips:
        raise RuntimeError("nothing to stitch")

    # THE CANVAS DEFAULTS TO THE FOOTAGE, not to a guess. A clip is the shape of
    # the still it was made from, so a set shot at 3:4 letterboxed into a 9:16
    # frame would be pillarboxed on both sides for no reason. Only an explicit
    # width/height overrides what the first clip actually is.
    if width is None or height is None:
        got = probe_size(clips[0])
        width, height = got or (1080, 1920)
    # h264 needs even dimensions.
    width, height = (width // 2) * 2, (height // 2) * 2

    # Pad rather than crop. A clip that came back the wrong shape is a mistake
    # worth SEEING as letterboxing, not one to hide by cutting her head off.
    per = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
           f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
           f"setsar=1,fps={fps}")
    parts = "".join(f"[{i}:v]{per}[v{i}];" for i in range(len(clips)))
    joins = "".join(f"[v{i}]" for i in range(len(clips)))
    graph = f"{parts}{joins}concat=n={len(clips)}:v=1:a=0[out]"

    cmd = [_ffmpeg(), "-y"]
    for c in clips:
        cmd += ["-i", str(c)]
    cmd += ["-filter_complex", graph, "-map", "[out]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(dest)]

    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not dest.exists():
        tail = (r.stderr or "").strip().splitlines()[-6:]
        raise RuntimeError("ffmpeg could not join the clips: " + " | ".join(tail))
    return dest
