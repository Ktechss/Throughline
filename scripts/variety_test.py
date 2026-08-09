"""Does gpt-image-2 hold her off-frontal, full-body, and in real light?

    .venv-win\\Scripts\\python.exe scripts\\variety_test.py

Every generator number this project has is a frontal studio close-up. That is
the easiest shot there is, and the two places every previous approach collapsed
are exactly the ones untested:

    nano-banana  close-up 0.678 -> full body 0.562
    FLUX LoRA    close-up 0.742 -> full body 0.522 (abstain, 108px, 43.9 off)

So: five shots across pose, framing and light, scored on the same 5-angle
gallery. Because the gallery spans -81 to +69, a profile is scored against a
PROFILE entry — the comparison is fair rather than abstaining, which is what
the multi-angle references bought us.

## Read the yaw before the similarity

A model that ignores a pose request returns a frontal image, and frontal images
score high against a frontal reference for free. So each shot prints the yaw it
asked for next to the yaw it got. A high score at the wrong yaw is not a pass;
it is the pose control silently failing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, gate, generate                  # noqa: E402

FACE = config.bio_face()
EDIT = "openai/gpt-image-2/edit"

HOLD = ("A candid iPhone photo of the woman in the reference image. She must "
        "remain exactly this person — do not regenerate, reinterpret or "
        "beautify her face.")
REAL = ("Photorealistic, real skin texture with visible pores, natural skin "
        "imperfections, no retouching. Shot on a phone, not a professional "
        "camera. No other people in frame.")

# (label, expected yaw, prompt). Expected yaw is what we ASKED for; the gate
# reports what we got. The gap between them is the pose control's honesty.
SHOTS = [
    ("3q-left", -42, f"{HOLD} Head and shoulders, her head turned three-quarters "
                     f"to her left, plain white studio background, soft even "
                     f"light. {REAL}"),
    ("profile-left", -81, f"{HOLD} Head and shoulders, her head in full left "
                          f"profile, looking away from the camera, plain white "
                          f"studio background, soft even light. {REAL}"),
    ("fullbody", 0, f"{HOLD} Full body, head to toe, standing facing the camera, "
                    f"arms relaxed at her sides, plain white studio background, "
                    f"soft even light. {REAL}"),
    ("street-noon", 0, f"{HOLD} Head and shoulders, facing the camera, standing "
                       f"on a pavement in a city, harsh vertical noon sunlight, "
                       f"hard shadows under her nose and chin, blown highlights "
                       f"on her shoulders. Unflattering and true. {REAL}"),
    ("cafe-window", -25, f"{HOLD} Head and shoulders, seated at a cafe table, her "
                         f"head turned slightly to her left, looking down at a "
                         f"notebook, flat grey diffuse light through a window, "
                         f"low contrast. {REAL}"),
]


def main() -> int:
    ref = gate.analyze(FACE)
    print(f"ref {FACE.name} {ref.width}px  |  bar: her own sheets 0.797  "
          f"|  frontal close-up was 0.813\n")
    session = generate.new_session("gpt-image-2 variety — pose, framing, light")
    url = generate.upload(FACE)

    rows = []
    for name, want_yaw, prompt in SHOTS:
        try:
            row = generate.generate(
                prompt=prompt, refs=[FACE], aspect="3:4", session=session,
                endpoint=EDIT, extra={"image_urls": [url]},
                meta={"note": f"variety: {name}", "expected_yaw": want_yaw},
            )
        except Exception as exc:                            # noqa: BLE001
            print(f"  {name:<14} FAILED {str(exc)[:110]}")
            continue
        v = row["verdict"]
        rows.append((name, want_yaw, v))
        got = v.get("yaw")
        obeyed = "" if got is None else ("pose OK" if abs(got - want_yaw) <= 20
                                         else f"IGNORED POSE (asked {want_yaw:+d})")
        s = v.get("similarity")
        print(f"  {name:<14} {s if s is None else f'{s:.3f}'} vs "
              f"{v.get('matched','-'):<20} yaw {got:+6.1f} "
              f"(delta {v.get('pose_delta',0):>4.1f})  {v.get('face_px',0):>3}px  "
              f"{v['status'].upper():<8} {obeyed}")
        if v.get("reason"):
            print(f"                 {v['reason'][:95]}")

    scored = [(n, v) for n, _, v in rows if v.get("similarity") and v["status"] != "abstain"]
    if scored:
        lo = min(scored, key=lambda r: r[1]["similarity"])
        print(f"\n  worst fair comparison: {lo[0]} at {lo[1]['similarity']:.3f}")
    print(f"  frontal close-up 0.813  |  her own sheets 0.797  |  floor 0.552")
    return 0


if __name__ == "__main__":
    sys.exit(main())
