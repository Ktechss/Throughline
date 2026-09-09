"""Her voice, anchored the same way her face is.

ONE VOICE PER CHARACTER, STORED ON HER. `voice_id` lives in bio.json beside
`reference` and `body_reference`, and every line she speaks is rendered with it.
That is not tidiness — it is the same rule the rest of the pipeline runs on. A
face picked per shot drifts; a wardrobe picked per scene drifts; a voice picked
per clip would drift too, and a listener notices a changed voice faster than a
changed hemline.

DESIGNED OR LIBRARY, NEVER CLONED FROM SOMEONE REAL. CLAUDE.md's hardest rule is
that she is entirely fictional, no real person's likeness anywhere. A voice is a
likeness. ElevenLabs' Voice Design generates one from a description, and the
shared Voice Library is voices their owners chose to publish — both are fine.
Uploading a recording of a real person to clone is not, and this module gives no
way to do it.

RENDERED LINES ARE CACHED ON DISK, keyed by (voice, model, settings, text). A
payg account bills per character, the same sentence gets re-rendered constantly
while an edit is being tuned, and paying twice for a byte-identical result is
the same waste `_UPLOAD_CACHE` exists to stop on the image side.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from . import config

_API = "https://api.elevenlabs.io/v1"

# Multilingual, because her voice is Indian English and the default English-only
# model flattens the accent it was chosen for.
MODEL = "eleven_multilingual_v2"

# Conversational, not announcer. Low-ish stability leaves the natural variation
# a vlog needs; high similarity keeps her recognisably one person across clips,
# which is the whole point of pinning a voice_id.
SETTINGS = {"stability": 0.45, "similarity_boost": 0.8,
            "style": 0.3, "use_speaker_boost": True}


class VoiceError(RuntimeError):
    """Anything that stops us returning audio."""


def _key() -> str:
    v = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not v or v.lower().startswith(("your-", "changeme", "xxx")):
        raise VoiceError("ELEVENLABS_API_KEY is not set in .env")
    return v


def voice_of(character: str | None = None) -> str:
    """Her voice id, from bio.json. Raises rather than substituting a default.

    A wrong-but-plausible voice is worse than none: it renders fine, sounds like
    somebody, and quietly makes her a different person for that clip.
    """
    cid = character or config.get_active()
    bio = config.char_base(cid) / "state" / "bio.json"
    try:
        vid = (json.loads(bio.read_text()).get("voice_id") or "").strip()
    except Exception as exc:                                    # noqa: BLE001
        raise VoiceError(f"cannot read {cid}'s bio: {exc}") from exc
    if not vid:
        raise VoiceError(
            f"{cid} has no voice yet — pick one and store it as `voice_id` in "
            f"her bio, the way `reference` holds her face")
    return vid


def _cache_path(cid: str, voice_id: str, text: str) -> Path:
    stamp = hashlib.sha256(
        json.dumps([voice_id, MODEL, SETTINGS, text], sort_keys=True).encode()
    ).hexdigest()[:16]
    d = config.char_base(cid) / "voice"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{stamp}.mp3"


def speak(text: str, *, character: str | None = None, voice_id: str | None = None,
          force: bool = False) -> Path:
    """Render one line in her voice. Cached, so a re-run of an edit is free."""
    text = (text or "").strip()
    if not text:
        raise VoiceError("nothing to say")
    cid = character or config.get_active()
    vid = voice_id or voice_of(cid)

    dest = _cache_path(cid, vid, text)
    if dest.is_file() and dest.stat().st_size > 0 and not force:
        return dest

    body = json.dumps({"text": text, "model_id": MODEL,
                       "voice_settings": SETTINGS}).encode()
    req = urllib.request.Request(
        f"{_API}/text-to-speech/{vid}", data=body, method="POST",
        headers={"xi-api-key": _key(), "Content-Type": "application/json",
                 "Accept": "audio/mpeg", "User-Agent": "curl/8.7.1"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            audio = r.read()
    except Exception as exc:                                    # noqa: BLE001
        detail = getattr(exc, "read", lambda: b"")() or b""
        raise VoiceError(
            f"ElevenLabs refused: {exc} {detail[:200].decode(errors='replace')}"
        ) from exc
    if not audio:
        raise VoiceError("ElevenLabs returned no audio")

    tmp = dest.with_suffix(".part")
    tmp.write_bytes(audio)
    tmp.replace(dest)
    return dest


def duration(media: Path) -> float:
    """Seconds, via ffprobe. 0.0 if it cannot be read."""
    exe = shutil.which("ffprobe")
    if not exe:
        return 0.0
    r = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(media)],
                       capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise VoiceError("ffmpeg is not on PATH")
    return exe


def narrate(cues: list[tuple[float, Path]], dest: Path, *,
            total: float | None = None) -> Path:
    """Lay rendered lines onto ONE track at their start times.

    A vlog is not a sequence of clips that each happen to contain a sentence —
    the voice runs ACROSS the cuts, which is most of what makes it feel like one
    person's day rather than eight fragments. So lines are placed on a single
    timeline by start time and mixed, and a line that overruns its own scene
    simply carries into the next shot, exactly as it does in a real one.

    `total` pads the track to the video's length so the mux cannot truncate the
    picture when the talking stops early.
    """
    cues = [(float(t), Path(p)) for t, p in cues if Path(p).is_file()]
    if not cues:
        raise VoiceError("no audio cues to lay down")

    parts, labels = [], []
    for i, (at, _p) in enumerate(cues):
        # adelay wants milliseconds, per channel.
        ms = max(0, int(round(at * 1000)))
        parts.append(f"[{i}:a]adelay={ms}|{ms},aresample=44100[a{i}];")
        labels.append(f"[a{i}]")
    graph = ("".join(parts) + "".join(labels) +
             f"amix=inputs={len(cues)}:dropout_transition=0:normalize=0[mix]")
    if total:
        graph += f";[mix]apad=whole_dur={total:.3f}[out]"
    out_label = "[out]" if total else "[mix]"

    cmd = [_ffmpeg(), "-y"]
    for _at, p in cues:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", graph, "-map", out_label,
            "-c:a", "aac", "-b:a", "192k", str(dest)]
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not dest.exists():
        tail = (r.stderr or "").strip().splitlines()[-5:]
        raise VoiceError("ffmpeg could not build the voice track: " + " | ".join(tail))
    return dest


def mux(video: Path, audio: Path, dest: Path) -> Path:
    """Put the voice track onto the picture without re-encoding the video.

    -c:v copy because the picture has already been encoded once by stitch(); a
    second pass would cost quality for nothing. -shortest is deliberately NOT
    used: narrate() pads to the video length, and letting the shorter stream end
    the file is how a vlog loses its last shot to a line that stopped early.
    """
    cmd = [_ffmpeg(), "-y", "-i", str(video), "-i", str(audio),
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
           "-map", "0:v:0", "-map", "1:a:0", str(dest)]
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not dest.exists():
        tail = (r.stderr or "").strip().splitlines()[-5:]
        raise VoiceError("ffmpeg could not mux the voice: " + " | ".join(tail))
    return dest
