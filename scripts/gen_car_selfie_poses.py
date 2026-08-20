"""Add a Selfie (Car) category — 50 poses, written as CAMERA positions.

Same lesson the handheld selfies just taught, applied from the start: in a
selfie the camera IS the phone, so a third-person description ("she holds her
phone up in the driver's seat") tells the model to sit in the passenger seat and
photograph a woman holding a phone. Every entry here states where the LENS is.

Two clause variants, because a car gives you both kinds of selfie:

  * DIRECT — the phone's front camera. The phone cannot be in the picture,
    because the picture is what the phone sees.
  * MIRROR — shot into the rear-view or vanity mirror. Here the phone SHOULD be
    visible, in the reflection, and saying "the phone is not in frame" would be
    wrong. These get their own clause.

Getting that distinction wrong is how the handheld set ended up with a phone
floating in shot, so it is enforced below rather than left to care.

What makes a car selfie read as one is the geometry: a seatbelt across the
chest, a headrest behind her, a window or windscreen throwing light from one
side, the cabin close around her. Each entry carries at least one of those.

Run:  ./.venv/bin/python scripts/gen_car_selfie_poses.py
"""
import json
import re
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))
from backend import poses_data                                  # noqa: E402

CATEGORY = "Selfie (Car)"

DIRECT = (" The phone itself is not in the picture — this frame IS what its front camera "
          "sees. Framed close inside the cabin, head-and-shoulders to waist-up.")
MIRROR = (" Shot as a reflection, so the phone IS visible in her hand in the glass. "
          "The mirror frame and the cabin around it are part of the picture.")

# id -> (text, "direct" | "mirror")
CAR = {
    # --- driver's seat
    "car-selfie-driver-parked": ("Shot on her own front camera held up in the driver's seat of a parked car, the steering wheel just below the frame and the seatbelt cutting across her chest.", "direct"),
    "car-selfie-driver-visor": ("Shot on her own front camera in the driver's seat with the sun visor down, hard daylight coming through the windscreen across one side of her face.", "direct"),
    "car-selfie-driver-headrest": ("Shot on her own front camera from the driver's seat with her head tipped back against the headrest, chin slightly up toward the lens.", "direct"),
    "car-selfie-driver-sunglasses": ("Shot on her own front camera in the driver's seat wearing sunglasses, one hand still resting on the top of the steering wheel below frame.", "direct"),
    "car-selfie-driver-window-down": ("Shot on her own front camera in the driver's seat with the window down beside her, an arm resting on the door and daylight flooding in from that side.", "direct"),
    "car-selfie-driver-side-glance": ("Shot on her own front camera propped near the windscreen in the driver's seat while she glances sideways out of the window rather than into the lens.", "direct"),
    "car-selfie-driver-seatbelt-hand": ("Shot on her own front camera in the driver's seat with one hand hooked around the seatbelt strap at her chest, that hand large and near the lens.", "direct"),
    "car-selfie-driver-keys": ("Shot on her own front camera in the driver's seat holding the car keys up beside her cheek, keys nearest the lens and slightly out of focus.", "direct"),
    "car-selfie-driver-laugh": ("Shot on her own front camera in the driver's seat mid-laugh with her head turned toward the door, seatbelt across her and the headrest behind.", "direct"),
    "car-selfie-driver-lean-wheel": ("Shot on her own front camera held above the steering wheel while she leans forward onto it, forearms crossed on the rim below the frame.", "direct"),
    "car-selfie-driver-coffee": ("Shot on her own front camera in the driver's seat holding a takeaway cup near her chin, the cup close and large in frame, windscreen light behind her.", "direct"),
    "car-selfie-driver-night-dash": ("Shot on her own front camera in the driver's seat at night, the dashboard glow lighting her face from below and the dark windscreen behind.", "direct"),

    # --- passenger seat
    "car-selfie-passenger-window": ("Shot on her own front camera in the passenger seat with the window behind her shoulder, landscape sliding past out of focus beyond the glass.", "direct"),
    "car-selfie-passenger-feet-up": ("Shot on her own front camera in the passenger seat leaning back with her knees drawn up toward the dashboard, seatbelt slack across her.", "direct"),
    "car-selfie-passenger-head-tilt": ("Shot on her own front camera in the passenger seat with her head tilted against the window glass, hair pressed flat where it touches.", "direct"),
    "car-selfie-passenger-arm-out": ("Shot on her own front camera in the passenger seat with her free arm out of the open window, wind pulling at her hair across the frame.", "direct"),
    "car-selfie-passenger-turn-back": ("Shot on her own front camera held out by the windscreen while she turns in the passenger seat toward the back, glancing over her shoulder.", "direct"),
    "car-selfie-passenger-sun-flare": ("Shot on her own front camera in the passenger seat with low sun coming through the side window straight into the lens, flare across one edge of the frame.", "direct"),
    "car-selfie-passenger-map": ("Shot on her own front camera in the passenger seat holding a phone or paper map up near her face, the cabin and dashboard soft behind her.", "direct"),
    "car-selfie-passenger-blanket": ("Shot on her own front camera in the passenger seat with a jacket or blanket pulled up to her chin, only her face and hands clear of it.", "direct"),
    "car-selfie-passenger-both-hands": ("Shot on her own front camera cradled in both hands close to her face in the passenger seat, elbows braced on her knees, cabin tight around her.", "direct"),
    "car-selfie-passenger-night-street": ("Shot on her own front camera in the passenger seat at night, streetlights sweeping across her face in bands through the side window.", "direct"),
    "car-selfie-passenger-eating": ("Shot on her own front camera in the passenger seat with fast food held up near the lens, laughing with her mouth half full.", "direct"),
    "car-selfie-passenger-sleepy": ("Shot on her own front camera in the passenger seat with heavy eyes and her cheek against the seatbelt, morning light flat through the windscreen.", "direct"),

    # --- back seat
    "car-selfie-backseat-centre": ("Shot on her own front camera from the middle of the back seat, both front headrests visible either side of the frame behind her.", "direct"),
    "car-selfie-backseat-window": ("Shot on her own front camera in the back seat leaning against the door with the rear window bright behind her head.", "direct"),
    "car-selfie-backseat-legs-up": ("Shot on her own front camera in the back seat with her legs stretched across the bench, the far door visible past her feet.", "direct"),
    "car-selfie-backseat-low": ("Shot on her own front camera held low in the back seat and angled up at her, the car roof and interior light above her in frame.", "direct"),
    "car-selfie-backseat-night": ("Shot on her own front camera in the dark back seat at night, her face lit only by the phone screen itself, everything behind her nearly black.", "direct"),
    "car-selfie-backseat-lean-forward": ("Shot on her own front camera in the back seat leaning forward between the front seats, headrests close on either side of her.", "direct"),
    "car-selfie-backseat-hair-window": ("Shot on her own front camera in the back seat with the window down and her hair blowing sideways across the frame.", "direct"),
    "car-selfie-backseat-seatbelt": ("Shot on her own front camera in the back seat with the belt diagonal across her chest and one hand resting on the buckle.", "direct"),

    # --- mirrors and reflections
    "car-selfie-rearview": ("Shot into the rear-view mirror, so only her eyes and the top of her face fill the small mirror frame with the cabin around it.", "mirror"),
    "car-selfie-vanity-mirror": ("Shot into the flipped-down vanity mirror on the sun visor, her face close in the small lit rectangle, the roof lining above.", "mirror"),
    "car-selfie-side-mirror": ("Shot into the wing mirror from the driver's window, her face in the glass with the road and car body wrapped around the reflection.", "mirror"),
    "car-selfie-rearview-lipstick": ("Shot into the rear-view mirror while she checks her lipstick, mouth slightly open, only the upper half of her face in the mirror.", "mirror"),
    "car-selfie-window-reflection": ("Shot into her own reflection in the closed side window at night, the street lights showing faintly through the glass behind the reflection.", "mirror"),
    "car-selfie-rearview-backseat": ("Shot into the rear-view mirror from the back seat, her face small in the mirror with the empty driver's seat below it.", "mirror"),

    # --- light and weather
    "car-selfie-rain-window": ("Shot on her own front camera in the passenger seat with rain running down the window beside her, the light outside grey and diffuse.", "direct"),
    "car-selfie-golden-hour": ("Shot on her own front camera in the driver's seat with low golden sun raking through the side window straight across her face.", "direct"),
    "car-selfie-tunnel-lights": ("Shot on her own front camera in the passenger seat as tunnel lights strobe past, bands of orange sweeping over her face and the seat.", "direct"),
    "car-selfie-car-wash": ("Shot on her own front camera inside the car during a car wash, foam and water sheeting down the glass all around the cabin behind her.", "direct"),
    "car-selfie-snow-window": ("Shot on her own front camera in the passenger seat with the windows fogged and snow visible beyond, her breath faintly clouding the air.", "direct"),
    "car-selfie-sunroof-up": ("Shot on her own front camera held above her with the sunroof open, bright sky filling the frame behind her head.", "direct"),

    # --- at the car rather than in it
    "car-selfie-leaning-door": ("Shot on her own front camera at arm's length while she leans back against the closed driver's door, the car body filling the frame behind her.", "direct"),
    "car-selfie-open-door-sit": ("Shot on her own front camera while she sits sideways in the open driver's doorway with her feet on the ground, door frame around one edge.", "direct"),
    "car-selfie-bonnet-lean": ("Shot on her own front camera while she leans back against the bonnet, the windscreen and roofline behind her out of focus.", "direct"),
    "car-selfie-roof-arm": ("Shot on her own front camera with her free arm resting along the roof of the car, standing at the open door, sky above the roofline.", "direct"),
    "car-selfie-boot-sit": ("Shot on her own front camera while she sits in the open boot with her legs hanging out, the tailgate above her in frame.", "direct"),
    "car-selfie-fuel-stop": ("Shot on her own front camera at the fuel pump beside the car, the forecourt canopy and pump behind her, flat overhead light.", "direct"),
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
    groups = {c: g for c, g in poses_data.POSE_GROUPS.items() if c != CATEGORY}
    seen = {k for g in groups.values() for k in g}

    dupes = seen & set(CAR)
    if dupes:
        raise SystemExit(f"id collision: {sorted(dupes)}")
    if len(CAR) != 50:
        raise SystemExit(f"{len(CAR)} poses, want 50")

    # A direct selfie must place the lens; a mirror one must not claim the phone
    # is absent, because in a reflection it is visibly there.
    for k, (text, kind) in CAR.items():
        if kind == "direct" and not re.search(r"her own front camera", text):
            raise SystemExit(f"{k}: direct selfie never places the camera in her hand")
        if kind == "mirror" and "front camera" in text:
            raise SystemExit(f"{k}: mirror selfie must not claim a front-camera view")
        if not re.search(r"seatbelt|steering wheel|headrest|window|windscreen|"
                         r"dashboard|cabin|door|mirror|sunroof|boot|bonnet|roof|"
                         r"seat|pump", text, re.I):
            raise SystemExit(f"{k}: nothing in it says 'car'")

    built = {k: text + (MIRROR if kind == "mirror" else DIRECT)
             for k, (text, kind) in CAR.items()}
    groups[CATEGORY] = built
    (PROJ / "backend" / "poses_data.py").write_text(emit(groups))

    mirrors = sum(1 for _, kind in CAR.values() if kind == "mirror")
    total = sum(len(g) for g in groups.values())
    print(f"{CATEGORY}: {len(built)} poses — {total} in the library, "
          f"{len(groups)} categories")
    print(f"  direct front-camera (phone absent) : {len(CAR) - mirrors}")
    print(f"  mirror shots (phone visible)       : {mirrors}")
