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

from . import gate
from .config import VIDEOS, VIDEOS_META

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
# Camera-ONLY descriptions — the SUBJECT's motion comes from the scene/extra text
# (or the director), so these must not pin her still or they fight an action clip.
CAMERA_MOVES = {
    "static":     ("The camera is locked off and steady.", True),
    "dolly-in":   ("The camera pushes in smoothly toward her.", False),
    "orbit":      ("The camera slowly orbits around her.", False),
    "crash-zoom": ("The camera crash-zooms in fast, a dramatic push.", False),
    "pull-back":  ("The camera slowly pulls back.", False),
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
            enable_safety_checker: bool = True, progress: dict | None = None) -> dict:
    """Animate `still` into a clip on fal, gate its frames, and record it.

    prompt_override wins if given; else the prompt is built from the camera move +
    extra. `dialogue` (happy-horse only) is appended so the model lip-syncs speech.
    """
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

    if progress is not None:
        progress["stage"] = "gating frames"
    frames = _score_frames(dest)

    row = {"id": rid, "file": dest.name, "still": still.name,
           "camera_move": camera_move, "model": model, "endpoint": ep,
           "prompt": prompt, "dialogue": dialogue.strip() or None,
           "resolution": resolution, "duration": int(duration),
           "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "frames": frames}
    rows = _ledger()
    rows.append(row)
    VIDEOS_META.write_text(json.dumps(rows, indent=2) + "\n")
    return row


def _ledger() -> list[dict]:
    return json.loads(VIDEOS_META.read_text()) if VIDEOS_META.exists() else []


def all_videos() -> list[dict]:
    return list(reversed(_ledger()))
