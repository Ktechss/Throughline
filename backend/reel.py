"""One script in, one reel out — with every stage named, priced and resumable.

WHY THIS EXISTS. The first vlog was built by hand: eight stills, eight clips, a
stitch, then a voice track laid over the top. It worked, and it was wrong in a
way that only shows when you try to add lipsync — because lipsync needs the
AUDIO BEFORE THE CLIP, and a pipeline that renders voice last cannot ever grow
that stage. The order below is the dependency order, not the order they happened
to get built in.

    1  voice    every line rendered first, because stage 4 consumes it
    2  still    the 9:16 frame; front beats carry the wardrobe and face the gate
    3  clip     the still animated
    4  lipsync  front beats that speak — NO PROVIDER TODAY, see LIPSYNC below
    5  stitch   the clips joined, in script order
    6  mux      the remaining voice laid across the cut

RESUMABLE, BECAUSE EVERY STAGE COSTS MONEY. Each scene records what it has
already produced. Re-running skips anything already on disk, so a failure in
scene 7 does not re-buy scenes 1-6. A pipeline that spends real money and cannot
resume is a pipeline you are afraid to run.

LIPSYNC IS DECLARED AND UNAVAILABLE, ON PURPOSE. Probed against kie on
2026-09-08: omnihuman, latentsync, wav2lip, musetalk, sync/lipsync, kling
lipsync, hedra, sonic, infinitetalk, wan-s2v, sadtalker, echomimic and ten more
all return 422 "model name not supported". Not one lipsync model is reachable on
this account. The stage still exists here and reports `blocked` rather than
being quietly dropped, because a silently skipped stage is how you ship a
talking-head reel where the mouth does not move and only notice on playback.

THE ONE RULE THAT DECIDES THE SHAPE. A front beat has her in it and must clear
the gate; a back beat is a photograph of a street with no face to score. Half a
reel is back-camera, and that half is cheap, ungated and cannot fail on
identity. See vlog_data for the argument in full.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import config, vlog

# What each stage needs before it can run. Read as: to lipsync a scene you need
# its clip AND its audio, which is why voice is stage 1 and not stage 6.
STAGES = ("voice", "still", "clip", "lipsync", "stitch", "mux")

DEPENDS: dict[str, tuple[str, ...]] = {
    "voice":   (),
    "still":   (),
    "clip":    ("still",),
    "lipsync": ("clip", "voice"),
    "stitch":  ("clip",),
    "mux":     ("stitch", "voice"),
}


class ReelError(RuntimeError):
    """Anything that stops a reel being buildable."""


@dataclass
class Scene:
    n: int
    slug: str
    camera: str                 # front | back
    seconds: int
    still: str                  # what the 9:16 frame shows
    motion: str                 # what moves in the clip
    line: str = ""              # what she says over it ("" = let it breathe)
    at: float = 0.0             # where it starts in the finished cut

    # Artifacts, filled in as stages complete. Their presence IS the resume
    # state — no separate bookkeeping to drift out of sync with the disk.
    voice_file: str | None = None
    still_run: str | None = None
    clip_run: str | None = None
    lipsync_run: str | None = None

    @property
    def gated(self) -> bool:
        """She is in it, so the gate has something to say. See vlog_data."""
        return self.camera == "front"

    @property
    def speaks(self) -> bool:
        return bool(self.line.strip())

    @property
    def needs_lipsync(self) -> bool:
        """Only a talking head needs its mouth to match. A line over b-roll is
        voice-over and wants no lipsync at all — running it would be spending
        money to animate a street's lips."""
        return self.camera == "front" and self.speaks


def load(path: str | Path) -> tuple[dict, list[Scene]]:
    """Read a script file into a header and its scenes."""
    p = Path(path)
    if not p.is_file():
        raise ReelError(f"no script at {p}")
    try:
        doc = json.loads(p.read_text())
    except Exception as exc:                                    # noqa: BLE001
        raise ReelError(f"{p.name} is not valid JSON: {exc}") from exc

    scenes, at = [], 0.0
    for i, s in enumerate(doc.get("scenes") or [], 1):
        missing = [k for k in ("slug", "camera", "still", "motion") if not s.get(k)]
        if missing:
            raise ReelError(f"scene {i} is missing {missing}")
        if s["camera"] not in ("front", "back"):
            raise ReelError(f"scene {i}: camera must be front or back")
        secs = int(s.get("seconds") or 5)
        scenes.append(Scene(
            n=i, slug=s["slug"], camera=s["camera"], seconds=secs,
            still=s["still"], motion=s["motion"], line=(s.get("line") or ""),
            at=float(s.get("at", at)),
        ))
        at += secs
    if not scenes:
        raise ReelError("that script has no scenes")
    return doc, scenes


def status(doc: dict, scenes: list[Scene], *, lipsync_available: bool = False) -> dict:
    """What is done, what is left, what it costs, and what is BLOCKED.

    `blocked` is not the same as `todo`. Todo is work waiting to be paid for;
    blocked is work that cannot be done at all right now, and conflating the two
    is how a reel gets shipped with silent mouths.
    """
    per_still = vlog.still_cost("seedream-5-lite") or 0.0
    clip = vlog.measured_clip_cost()
    per_clip = clip["usd"]

    todo = {s: 0 for s in STAGES}
    done = {s: 0 for s in STAGES}
    for sc in scenes:
        for stage, got in (("voice", sc.voice_file if sc.speaks else "-"),
                           ("still", sc.still_run),
                           ("clip", sc.clip_run)):
            if stage == "voice" and not sc.speaks:
                continue
            (done if got else todo)[stage] += 1
        if sc.needs_lipsync:
            (done if sc.lipsync_run else todo)["lipsync"] += 1

    blocked = []
    if todo["lipsync"] and not lipsync_available:
        blocked.append({
            "stage": "lipsync", "scenes": todo["lipsync"],
            "why": "no lipsync model is reachable on this account — probed "
                   "omnihuman, latentsync, wav2lip, musetalk, sync, kling, "
                   "hedra, sonic, infinitetalk, wan-s2v and more; all 422",
            "effect": "those scenes render with her mouth out of sync",
            "options": ["cut away from her face while she speaks",
                        "add a provider that carries a lipsync model",
                        "run a local lipsync pass over the finished clips"],
        })

    stills_usd = round(per_still * todo["still"], 4)
    clips_usd = None if per_clip is None else round(per_clip * todo["clip"], 4)
    chars = sum(len(sc.line) for sc in scenes if sc.speaks and not sc.voice_file)

    return {
        "title": doc.get("title") or "untitled",
        "character": doc.get("character"),
        "wardrobe": doc.get("wardrobe"),
        "scenes": len(scenes),
        "seconds": sum(sc.seconds for sc in scenes),
        "front": sum(1 for s in scenes if s.camera == "front"),
        "back": sum(1 for s in scenes if s.camera == "back"),
        "speaking": sum(1 for s in scenes if s.speaks),
        "needs_lipsync": sum(1 for s in scenes if s.needs_lipsync),
        "done": done, "todo": todo, "blocked": blocked,
        "cost": {
            "stills_usd": stills_usd,
            "clips_usd": clips_usd,
            "voice_characters": chars,      # billed by ElevenLabs, not kie
            "total_usd": None if clips_usd is None else round(stills_usd + clips_usd, 4),
            # False means the total is a FLOOR — the clips are not in it. Same
            # contract as vlog.estimate; see that docstring for why guessing the
            # expensive half is worse than admitting to not knowing it.
            "complete": clips_usd is not None,
        },
    }


def next_actions(scenes: list[Scene], *, lipsync_available: bool = False) -> list[dict]:
    """The work, in dependency order, one entry per thing to actually do.

    Returned rather than executed so a caller can price it, show it, and let the
    owner strike lines out before any of it is bought.
    """
    # THE WHOLE REMAINING PLAN, not just what happens to be runnable now.
    #
    # An earlier version only listed a clip once its still existed, so a fresh
    # script reported eight stills and NO clips — understating both the work and
    # the money by the entire expensive half. Readiness is a separate axis from
    # existence, so it gets its own field and the plan stays complete.
    out: list[dict] = []
    for sc in scenes:
        if sc.speaks and not sc.voice_file:
            out.append({"stage": "voice", "scene": sc.n, "slug": sc.slug,
                        "detail": sc.line[:70], "spends": "elevenlabs",
                        "ready": True, "blocked": False})
    for sc in scenes:
        if not sc.still_run:
            out.append({"stage": "still", "scene": sc.n, "slug": sc.slug,
                        "gated": sc.gated, "spends": "kie",
                        "ready": True, "blocked": False})
    for sc in scenes:
        if not sc.clip_run:
            out.append({"stage": "clip", "scene": sc.n, "slug": sc.slug,
                        "spends": "kie",
                        "ready": bool(sc.still_run), "blocked": False})
    for sc in scenes:
        if sc.needs_lipsync and not sc.lipsync_run:
            out.append({"stage": "lipsync", "scene": sc.n, "slug": sc.slug,
                        "spends": "no provider",
                        "ready": bool(sc.clip_run and sc.voice_file),
                        "blocked": not lipsync_available})
    out.append({"stage": "stitch", "scene": None, "spends": "free",
                "ready": all(sc.clip_run for sc in scenes), "blocked": False})
    if any(sc.speaks for sc in scenes):
        out.append({"stage": "mux", "scene": None, "spends": "free",
                    "ready": all(sc.clip_run for sc in scenes)
                             and all(sc.voice_file for sc in scenes if sc.speaks),
                    "blocked": False})
    return out


def script_path(name: str) -> Path:
    return config.DATA / "scripts" / f"{name}.json"


def scripts() -> list[str]:
    d = config.DATA / "scripts"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []
