"""Video generation via fal — animate a gate-approved still into a clip.

The still already IS her (it passed the gate), so identity is anchored from
frame one. The cinematic feel comes from CAMERA motion, not subject motion — a
locked subject with a moving camera reads far more "shot on a real rig" than a
twitching subject in a static frame. Each clip's frames are re-gated so identity
drift on big moves is a number, not a guess — same honesty rule as the stills.
"""

from __future__ import annotations

import json
import time
import urllib.request
import uuid
from pathlib import Path

import fal_client

from . import config, db, gate
from .config import VIDEOS

# fal image-to-video endpoints. Seedance 1.0 Pro is permissive + realistic (the
# default); Kling is gentler and the most identity-safe on big motion.
SEEDANCE = "fal-ai/bytedance/seedance/v1/pro/image-to-video"
KLING = "fal-ai/kling-video/v2.1/standard/image-to-video"
# Alibaba happy-horse: face-permissive (no ByteDance likeness block) AND does
# native audio + automatic multilingual lip-sync — put dialogue in the prompt and
# she speaks it. On fal, on our real Kiara. This is the closest to Seedance 2.0
# we can actually use.
HAPPY_HORSE = "alibaba/happy-horse/v1.1/image-to-video"
MODELS = {"seedance": SEEDANCE, "kling": KLING, "happy-horse": HAPPY_HORSE}

# camera move -> (prompt fragment, camera_fixed). Big moves (orbit, crash-zoom)
# turn her head off-axis and cost identity — that's the yaw law, and the frame
# gate reports it. Gentle moves (dolly, static) keep her frontal and on-model.
# Camera library — descriptions of the CAMERA only (the SUBJECT's motion comes
# from the scene/extra text), so a move never pins her still and fights an action
# clip. Each entry: (prompt fragment, camera_fixed). Curated from the standard
# cinematography vocabulary + Higgsfield's preset library, kept to the moves that
# translate reliably to text-prompt video models (Seedance / Kling / happy-horse).
CAMERA_MOVES = {
    # --- static / framing angles (camera holds; the shot's ANGLE is the choice) ---
    "static":        ("The camera is locked off and steady.", True),
    "low-angle":     ("Low-angle shot from below, looking up at her — she reads tall and powerful.", True),
    "high-angle":    ("High-angle shot from above, looking down at her.", True),
    "overhead":      ("Overhead top-down shot looking straight down at her.", True),
    "dutch-angle":   ("Dutch angle — the frame canted off-level for tension.", True),
    "over-shoulder": ("Over-the-shoulder framing, looking past her shoulder.", True),
    # --- push / pull (dolly & zoom on the lens axis) ---
    "dolly-in":      ("The camera pushes in smoothly toward her.", False),
    "dolly-out":     ("The camera pulls back smoothly away from her.", False),
    "super-dolly-in": ("A fast, aggressive super dolly straight in toward her.", False),
    "crash-zoom":    ("The camera crash-zooms in fast, a dramatic snap push.", False),
    "crash-zoom-out": ("The camera crash-zooms out fast, snapping wide.", False),
    "dolly-zoom":    ("A dolly-zoom (vertigo effect) — the camera pushes in while zooming out, the background warping around her.", False),
    "pull-back":     ("The camera slowly pulls back to reveal the full scene.", False),
    "aerial-pullback": ("The camera pulls back and rises into a wide aerial reveal.", False),
    # --- lateral / vertical ---
    "pan-left":      ("The camera pans smoothly to the left.", False),
    "pan-right":     ("The camera pans smoothly to the right.", False),
    "truck":         ("The camera tracks laterally alongside her.", False),
    "tilt-up":       ("The camera tilts upward.", False),
    "tilt-down":     ("The camera tilts downward.", False),
    "crane-up":      ("The camera cranes upward, rising above her.", False),
    "crane-down":    ("The camera cranes downward toward her.", False),
    # --- rotational ---
    "orbit":         ("The camera slowly orbits around her.", False),
    "arc":           ("The camera arcs around her in a smooth semicircle.", False),
    "360-orbit":     ("The camera makes a full 360-degree orbit around her.", False),
    "bullet-time":   ("Bullet-time — the camera whips around her in a frozen moment as she holds still.", False),
    # --- special / handheld ---
    "handheld":      ("Handheld camera with subtle natural shake, a candid documentary feel.", False),
    "whip-pan":      ("A fast whip pan with motion blur.", False),
    "fpv-drone":     ("A fast FPV drone shot flying in toward and around her, dynamic and immersive.", False),
    "snorricam":     ("Snorricam — the camera rig-mounted to her body, she stays fixed in frame while the world moves behind her.", False),
    "focus-pull":    ("A rack focus pulling from the foreground onto her.", False),
}


def _upload_seed(path: Path) -> str:
    """Downscale + upload the still (the 20 MB originals are needless here)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((1080, 1920))
    tmp = VIDEOS / f"_seed_{uuid.uuid4().hex[:8]}.jpg"
    im.save(tmp, quality=92)
    try:
        return fal_client.upload_file(str(tmp))
    finally:
        tmp.unlink(missing_ok=True)


def _strip_audio(path: Path) -> bool:
    """Remove the audio track in place (happy-horse forces audio; this is the only
    way to get a silent clip). Returns True if it stripped."""
    import subprocess
    import imageio_ffmpeg
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = path.with_suffix(".mute.mp4")
    subprocess.run([exe, "-y", "-i", str(path), "-c", "copy", "-an", str(tmp)],
                   capture_output=True)
    if tmp.exists() and tmp.stat().st_size > 10_000:
        tmp.replace(path)
        return True
    tmp.unlink(missing_ok=True)
    return False


def _score_frames(video_path: Path) -> list[dict]:
    """Gate the mid + last frame so identity drift over the clip is measured."""
    import cv2
    out = []
    cap = cv2.VideoCapture(str(video_path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    for label, idx in (("mid", n // 2), ("end", n - 2)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, idx))
        ok, fr = cap.read()
        if not ok:
            continue
        tmp = VIDEOS / f"_f_{uuid.uuid4().hex[:6]}.png"
        cv2.imwrite(str(tmp), fr)
        try:
            v = gate.check(tmp).dict()
            out.append({"frame": label, "status": v.get("status"),
                        "similarity": v.get("similarity"), "yaw": v.get("yaw")})
        except Exception:  # noqa: BLE001 — a frame we can't gate isn't fatal
            out.append({"frame": label, "status": "no_face"})
        finally:
            tmp.unlink(missing_ok=True)
    cap.release()
    return out


def animate(still: Path, *, camera_move: str = "dolly-in", model: str = "seedance",
            extra: str = "", prompt_override: str = "", dialogue: str = "",
            resolution: str = "1080p", duration: int = 5, seed: int | None = None,
            enable_safety_checker: bool = True, keep_audio: bool = True,
            progress: dict | None = None) -> dict:
    """Animate `still` into a clip on fal, gate its frames, and record it.

    prompt_override wins if given; else the prompt is built from the camera move +
    extra. `dialogue` (happy-horse only) is appended so the model lip-syncs speech.
    """
    owner = config.get_active()   # pin the character NOW — a mid-render switch must not misfile this clip
    frag, camera_fixed = CAMERA_MOVES.get(camera_move, CAMERA_MOVES["dolly-in"])
    if prompt_override.strip():
        prompt = prompt_override.strip()
    else:
        # scene/action FIRST (drives her movement), camera second, then realism tail
        parts = [extra.strip()] if extra.strip() else []
        parts.append(frag)
        prompt = " ".join(parts).strip().rstrip(".") + ". Photorealistic, cinematic."
    if dialogue.strip():
        prompt = f'{prompt} She looks at the camera and says: "{dialogue.strip()}"'
    ep = MODELS.get(model, SEEDANCE)

    if progress is not None:
        progress["stage"] = "uploading"
    url = _upload_seed(still)

    if progress is not None:
        progress["stage"] = "generating video"
    if ep == HAPPY_HORSE:
        args = {"prompt": prompt, "image_url": url,
                "resolution": resolution if resolution in ("720p", "1080p") else "1080p",
                "duration": int(duration), "enable_safety_checker": bool(enable_safety_checker)}
        if seed is not None:
            args["seed"] = int(seed)
    elif ep == KLING:
        args = {"prompt": prompt, "image_url": url,
                "duration": "10" if int(duration) >= 8 else "5",
                "negative_prompt": "distortion, morphing face, warping, identity change, extra fingers",
                "cfg_scale": 0.5}
    else:  # seedance — supports 5s or 10s
        args = {"prompt": prompt, "image_url": url, "resolution": "1080p",
                "duration": "10" if int(duration) >= 8 else "5", "camera_fixed": camera_fixed}
    r = fal_client.subscribe(ep, arguments=args, with_logs=False)
    vid_url = (r.get("video") or {}).get("url") or (r.get("videos") or [{}])[0].get("url")
    if not vid_url:
        raise RuntimeError("fal returned no video url")

    rid = uuid.uuid4().hex[:10]
    dest = VIDEOS / f"{rid}.mp4"
    if progress is not None:
        progress["stage"] = "downloading"
    urllib.request.urlretrieve(vid_url, dest)
    if dest.stat().st_size < 10_000:
        dest.unlink(missing_ok=True)
        raise RuntimeError("truncated video download")

    # happy-horse forces audio; strip it if the user asked for a silent clip
    muted = False
    if not keep_audio:
        if progress is not None:
            progress["stage"] = "muting"
        muted = _strip_audio(dest)

    if progress is not None:
        progress["stage"] = "gating frames"
    frames = _score_frames(dest)

    row = {"id": rid, "file": dest.name, "still": still.name,
           "camera_move": camera_move, "model": model, "endpoint": ep,
           "prompt": prompt, "dialogue": dialogue.strip() or None,
           "resolution": resolution, "duration": int(duration),
           "audio": not muted, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "frames": frames}
    db.videos_insert(row, character_id=owner)
    return row


def stitch(clip_paths: list[Path], out: Path | None = None,
           durations: list[int] | None = None) -> Path:
    """Concatenate clips (cover-cropped to 1080x1920, audio preserved) into one.

    `durations` (per clip) trims each to its intended length — models with a 5s
    minimum otherwise pad short storyboard beats and bloat the total."""
    import os
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", __import__("imageio_ffmpeg").get_ffmpeg_exe())
    from moviepy import VideoFileClip, concatenate_videoclips
    W, H = 1080, 1920

    def cover(c):
        c = c.resized(height=H)
        if c.w < W:
            c = c.resized(width=W)
        return c.cropped(x_center=c.w / 2, y_center=c.h / 2, width=W, height=H)

    clips = []
    for i, p in enumerate(clip_paths):
        if not (p and p.exists()):
            continue
        c = cover(VideoFileClip(str(p)))
        if durations and i < len(durations) and durations[i] and durations[i] < c.duration:
            c = c.subclipped(0, durations[i])
        clips.append(c)
    if not clips:
        raise RuntimeError("no clips to stitch")
    final = concatenate_videoclips(clips, method="compose")
    out = out or (VIDEOS / f"{uuid.uuid4().hex[:10]}.mp4")
    final.write_videofile(str(out), fps=24, codec="libx264", audio_codec="aac",
                          preset="veryfast", logger=None)
    return out


def record(row: dict) -> None:
    db.videos_insert(row)


def all_videos() -> list[dict]:
    return db.videos_all(newest_first=True)
