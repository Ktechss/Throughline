"""Rewrite the handheld selfie poses as CAMERA positions, not body positions.

Every other category in poses_data describes a body seen from outside, which is
the right convention for `seated-lean-back` or `walking-arms-swinging`. Selfies
are the one case where it is wrong: in a selfie the camera IS the phone in her
hand, so a third-person description tells the model to stand a few feet away and
photograph a woman holding a phone. That is exactly what came back — a
photograph OF someone taking a selfie, with a proper camera's depth of field and
the phone visible as a prop.

Measured before the rewrite: all 25 handheld poses were third-person, and NONE
placed the camera in her hand.

The rewrite keeps every id and every pose's intent — the same gesture, the same
angle, the same mood — and moves the viewpoint into the phone. Three things each
entry now carries:

  * where the phone is, stated as where the CAMERA is
  * the arm entering frame, because a real selfie almost always shows it
  * the front-camera look: close subject, mild wide-angle stretch, background
    falling away

Ids are unchanged so historical runs and saved references still resolve.

Run:  ./.venv/bin/python scripts/gen_selfie_poses.py
"""
import json
import re
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))
from backend import poses_data                                  # noqa: E402

CATEGORY = "Selfie (Handheld)"

# Appended to EVERY entry, because the first rewrite proved that moving the
# camera is not enough on its own. It fixed the angle and left the phone sitting
# in her hand — and a phone visible in frame is proof the camera is not the
# phone. It also framed full-body, because the rest of the prompt describes an
# outfit head to toe and the pose never claimed a crop.
#
# So each pose now states two things the first version left implicit: the phone
# is NOT in the picture, and the crop is close.
THROUGH_THE_LENS = (" The phone itself is not in the picture — this frame IS what its front "
                    "camera sees. Framed close, head-and-shoulders to waist-up at most, "
                    "her face and upper body filling most of the frame.")

SELFIE = {
    "selfie-classic-arm-out": "Shot on her own phone's front camera held at arm's length just above eye level, angled slightly down at her. Her outstretched forearm runs into the lower corner of the frame and her near shoulder is closest to the lens. Mild wide-angle stretch, the room behind her falling away.",
    "selfie-high-angle": "Shot on her own front camera held high above her and tipped steeply down, so she is looking up into it with her chin raised. Her raised arm cuts across one side of the frame. Strong overhead foreshortening, the floor and background compressed far below her.",
    "selfie-two-hands": "Shot on her own front camera cradled in both hands close to her face, so the lens sits near and level. Both forearms rise into the bottom edge of the frame. Very tight crop, head tilted to one side, background thrown well out of focus.",
    "selfie-side-glance": "Shot on her own front camera held out to one side at arm's length, so she fills one half of the frame and glances sideways into it. Her extended arm enters from that edge. Cheek turned, chin dipped, background sliding away behind her.",
    "selfie-peace-sign": "Shot on her own front camera at arm's length while her other hand lifts a two-finger peace sign close to her cheek — that hand is large in the frame, nearer the lens than her face. Playful head tilt, mild wide-angle stretch.",
    "selfie-low-angle": "Shot on her own front camera held low near her chest and tilted up at her, so the angle looks up along her jaw. Her forearm rises into the bottom of the frame. Ceiling visible behind her, foreshortened upward perspective.",
    "selfie-blowing-kiss": "Shot on her own front camera at arm's length as she puckers toward it, her free hand raised beside her mouth and closer to the lens than her face. Tight crop, mild front-camera distortion.",
    "selfie-hair-toss": "Shot on her own front camera at arm's length while her other hand sweeps back through her hair, head tipping back toward the lens. Both arms frame the shot, hair loose across the top of the frame.",
    "selfie-over-shoulder": "Shot on her own front camera held out to one side while her back is partly turned, so she is glancing back over her shoulder into the lens. Her raised arm and shoulder dominate one edge of the frame.",
    "selfie-lying-overhead": "Shot on her own front camera held directly overhead in both hands as she lies on her back looking straight up into it. Her hair fans out around her head and the ceiling fills the background behind her.",
    "selfie-outstretched-laugh": "Shot on her own front camera flung out to full arm's length as she laughs into it, shoulders rising and her free hand drifting up near her collarbone. Looser wide crop, background visible around her.",
    "selfie-cheek-to-lens": "Shot on her own front camera brought in very close and turned to one cheek, eyes cutting sideways into it. Extremely tight crop — her face fills nearly the whole frame, skin texture prominent, background almost gone.",
    "selfie-both-arms-up": "Shot on her own front camera raised overhead in both hands as she arches slightly back and tilts her face up into it. Both arms run up the sides of the frame, sky or ceiling wide behind her.",
    "selfie-walking-vlog": "Shot on her own front camera held out ahead at eye level while she walks, talking toward it. The frame bobs with her steps, her free arm swings in and out of the bottom edge, the street or corridor slides past behind her.",
    "selfie-chin-in-hand": "Shot on her own front camera at arm's length while her other hand cups her chin, that hand large and near the lens. Head tilted thoughtfully, tight crop, soft background.",
    "selfie-wink": "Shot on her own front camera at arm's length as she throws a light wink into it, her free hand resting near her jaw. Close crop, playful expression, mild wide-angle stretch.",
    "selfie-pout": "Shot on her own front camera held slightly above and out, looking down at her as she pushes her lips into a soft pout with half-lidded eyes. Tight upper-body crop, background falling away.",
    "selfie-seated-relaxed": "Shot on her own front camera held out at chest height while she leans back seated, so the lens looks slightly up at her relaxed smile. Her forearm enters the lower frame, the seat and room behind her.",
    "selfie-sun-squint": "Shot on her own front camera outdoors in bright light at arm's length, she squints lightly into it with her other hand shading her brow — that hand nearest the lens. Blown-out sky behind her, harsh daylight on her face.",
    "selfie-hand-on-cheek": "Shot on her own front camera reached out to one side while her other palm presses softly to her cheek, head tilted into it. That hand is close to the lens, her face slightly further back.",
    "selfie-lying-front": "Shot on her own front camera propped on the surface just ahead of her as she lies on her stomach on her forearms, looking up into it. Low near-floor viewpoint, her arms framing the bottom corners.",
    "selfie-looking-away": "Shot on her own front camera held out at eye level, but her gaze drifts off past it rather than into it, chin lifted. Candid and unposed, her arm just visible at the frame edge.",
    "selfie-coffee-cup": "Shot on her own front camera in one hand while the other holds a takeaway cup near her chin, the cup large and close to the lens. She glances into the camera over its rim.",
    "selfie-face-frame": "Shot on her own front camera tucked in one of the two hands she has raised beside her face, both loosely framing her cheeks as she smiles into it. Hands nearest the lens, very tight crop.",
    "selfie-shoulder-shrug": "Shot on her own front camera held out to one side as she lifts both shoulders in a light shrug, head tilted toward one of them with a soft grin into the lens.",
}


def emit(groups: dict) -> str:
    out = ['"""Generated pose library — {cat: {id: text}}. Regenerate via '
           'scratchpad/gen_poses.py."""', "", "POSE_GROUPS = {"]
    for cat, items in groups.items():
        out.append(f"  {json.dumps(cat)}: {{")
        for k, v in items.items():
            out.append(f"    {json.dumps(k)}: {json.dumps(v)},")
        out[-1] = out[-1][:-1]
        out.append("  },")
    out[-1] = "  }"
    out.append("}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    groups = dict(poses_data.POSE_GROUPS)
    old = groups[CATEGORY]

    missing = set(old) - set(SELFIE)
    extra = set(SELFIE) - set(old)
    if missing or extra:
        raise SystemExit(f"id drift — missing {sorted(missing)}, extra {sorted(extra)}")

    # Every rewrite must actually MOVE the camera. A pose that still reads as a
    # third-person description of a woman holding a phone is the bug, not a fix.
    bad = [k for k, v in SELFIE.items()
           if not re.search(r"front camera|her own phone", v, re.I)]
    if bad:
        raise SystemExit(f"these do not place the camera in her hand: {bad}")
    if "not in the picture" not in THROUGH_THE_LENS:
        raise SystemExit("the shared clause must say the phone is absent")
    third = [k for k, v in SELFIE.items() if re.search(r"\bShe (holds|lifts|extends|cradles)\b", v)]
    if third:
        raise SystemExit(f"these still describe her from outside: {third}")

    groups[CATEGORY] = {k: SELFIE[k] + THROUGH_THE_LENS for k in old}  # order preserved
    (PROJ / "backend" / "poses_data.py").write_text(emit(groups))
    print(f"rewrote {len(SELFIE)} poses in {CATEGORY!r}; "
          f"{sum(len(g) for g in groups.values())} poses total, ids unchanged")
