"""openai/gpt-image-2/edit — same reference, same prompt, same gate.

gpt-image-1 through fal scored 0.466 (high) / 0.591 (medium), well under
nano-banana. If that was the model being old rather than the endpoint lacking
ChatGPT's conversation context, gpt-image-2 should be visibly better.

Comparable numbers, all one face reference, close-up, scored on the 5-angle
gallery:
    her own ChatGPT sheets .. 0.797   <- the bar
    ideogram-character ...... 0.750
    FLUX LoRA ............... 0.742
    flux-pulid .............. 0.713
    nano-banana ............. 0.678
    gpt-image-1 medium ...... 0.591
    gpt-image-1 high ........ 0.466
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import gate, generate                          # noqa: E402
from backend.config import REFS                             # noqa: E402

FACE = REFS / "Kiara.png"
EDIT = "openai/gpt-image-2/edit"

PROMPT = ("A candid iPhone photo of the woman in the reference image. She must "
          "remain exactly this person — do not regenerate, reinterpret or "
          "beautify her face. Tight head and shoulders portrait, her face "
          "filling most of the frame, facing the camera, plain white studio "
          "background, soft even light. Photorealistic, real skin texture with "
          "visible pores, natural skin imperfections, no retouching. Shot on a "
          "phone, not a professional camera.")


def main() -> int:
    ref = gate.analyze(FACE)
    print(f"ref: {FACE.name} {ref.width}px yaw {ref.yaw:+.1f}\n")
    session = generate.new_session("gpt-image-2 via fal — same ref, same close-up")
    url = generate.upload(FACE)

    # Params unknown beyond prompt+image_urls; try quality tiers and fall back
    # to a bare call rather than guessing a schema.
    attempts = [
        ("high", {"image_urls": [url], "image_size": "1024x1536", "quality": "high"}),
        ("medium", {"image_urls": [url], "image_size": "1024x1536", "quality": "medium"}),
        ("default", {"image_urls": [url]}),
    ]
    for label, extra in attempts:
        try:
            row = generate.generate(
                prompt=PROMPT, refs=[FACE], aspect="3:4", session=session,
                endpoint=EDIT, extra=extra,
                meta={"note": f"gpt-image-2 edit, {label}"},
            )
        except Exception as exc:                            # noqa: BLE001
            print(f"  {label:<8} FAILED {str(exc)[:150]}")
            continue
        v = row["verdict"]
        s = v.get("similarity")
        print(f"  {label:<8} {s if s is None else f'{s:.3f}'} vs {v.get('matched','-'):<8} "
              f"yaw {v.get('yaw',0):+6.1f} (delta {v.get('pose_delta',0):>4.1f})  "
              f"{v.get('face_px',0):>3}px  {v['status'].upper()}")
        print(f"           data/images/{row['file']}")

    print("\n  bar: her own sheets 0.797  |  best fal so far: ideogram 0.750")
    print("  gpt-image-1 was 0.591 medium / 0.466 high")
    return 0


if __name__ == "__main__":
    sys.exit(main())
