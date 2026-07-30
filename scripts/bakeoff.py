"""Identity-transfer bakeoff, against a calibrated gate this time.

The morning's attempt was uninterpretable: faces came back 78-106px (under the
abstain floor) and there was no gallery to score against. Both fixed. So:

  - ONE face reference, the biggest we have (Kiara.png, 435px).
  - Close-up framing, so the face lands well above the floor. Framing is an
    identity setting: 660px scored 0.635 where 298px scored 0.450.
  - Every result scored against the same 5-angle gallery.
  - Read the YAW before the similarity. A model that ignores the brief and
    returns a frontal scores high for free.

Baselines to beat:
    nano-banana-pro/edit, same ref, close-up ..... 0.678
    her own frontals agree at ..................... 0.797  <- the ceiling
    stranger floor ................................ 0.552
"""
from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

import fal_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import gate                                   # noqa: E402
from backend.config import IMAGES, REFS                    # noqa: E402

FACE = REFS / "Kiara.png"

PROMPT = ("A candid iPhone photo of a woman, tight head and shoulders portrait, "
          "her face filling most of the frame, facing the camera, plain white "
          "studio background, soft even light, photorealistic, real skin texture "
          "with visible pores, natural skin imperfections, no retouching, "
          "no makeup gloss. Shot on a phone, not a professional camera.")

BIG = {"width": 1024, "height": 1408}

# (label, endpoint, argument builder). Params differ per model and I am not
# certain of every schema — each runs in its own try so one bad signature
# doesn't kill the batch.
def cands(url: str):
    return [
        ("flux-pulid", "fal-ai/flux-pulid", {
            "prompt": PROMPT, "reference_image_url": url,
            "image_size": BIG, "num_inference_steps": 28,
            "guidance_scale": 4.0, "id_weight": 1.0, "true_cfg": 1.0,
        }),
        ("ideogram-character", "fal-ai/ideogram/character", {
            "prompt": PROMPT, "reference_image_urls": [url],
            "image_size": BIG, "rendering_speed": "QUALITY",
        }),
        ("instant-character", "fal-ai/instant-character", {
            "prompt": PROMPT, "image_url": url,
            "image_size": BIG, "scale": 1.0,
            "num_inference_steps": 28,
        }),
    ]


def main() -> int:
    url = fal_client.upload_file(str(FACE))
    ref = gate.analyze(FACE)
    print(f"face ref: {FACE.name}  {ref.width}px  yaw {ref.yaw:+.1f}\n")

    rows = []
    for label, endpoint, args in cands(url):
        t0 = time.time()
        try:
            r = fal_client.subscribe(endpoint, arguments=args, with_logs=False)
            dest = IMAGES / f"bake_{label}.png"
            urllib.request.urlretrieve(r["images"][0]["url"], dest)
            if dest.stat().st_size < 10_000:
                raise RuntimeError("truncated download")
        except Exception as exc:                       # noqa: BLE001
            print(f"  {label:<20} FAILED  {str(exc)[:110]}")
            continue

        secs = time.time() - t0
        try:
            v = gate.check(dest).dict()
        except gate.NoFaceFound:
            print(f"  {label:<20} no face in output ({secs:.0f}s)")
            continue
        rows.append((label, v))
        note = f"  <- {v['reason'][:60]}" if v.get("reason") else ""
        print(f"  {label:<20} {v['similarity']:.3f} vs {v['matched']:<10} "
              f"yaw {v['yaw']:+6.1f} (delta {v['pose_delta']:>4.1f})  "
              f"{v['face_px']:>3}px  {v['status'].upper()}  {secs:.0f}s{note}")

    print(f"\n  {'nano-banana (baseline)':<22} 0.678")
    print(f"  {'her own frontals':<22} 0.797   <- ceiling")
    if rows:
        best = max(rows, key=lambda r: r[1]["similarity"])
        print(f"\n  best: {best[0]} at {best[1]['similarity']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
