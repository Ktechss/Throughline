"""How much of them is in the frame, and how big that leaves a face.

WHY THIS IS A LIBRARY AND NOT A SENTENCE IN THE BRIEF

On 2026-08-04 a three-person scene was briefed with "Tight head-and-shoulders
crop — all three cropped just below the collarbone, faces filling the frame.
Nothing below the chest is in shot." It came back waist-up with a ceiling in it.
The instruction was in the prompt, in plain English, at the end, and the model
ignored it in favour of its own idea of how to fit three people in a 3:4 frame.

Framing loses when it is prose competing with everything else in the brief. It
wins — or at least gets a fair hearing — when it is the FIRST thing after the
photographic register, which is where `_build_scene` now places it, and where the
shot path already places the camera holder for exactly the same stated reason:
it decides the distance everything after it is written against.

Whether that is enough is an open question with a cheap answer. Generate the same
cast twice, `head_shoulders` against `full_body`, and read back `face_px`. If the
number does not move, framing-by-prompt does not work and this library is a lie
that needs a real crop step behind it.

THE FACE-SIZE ESTIMATE

`face_frac` is the face box height as a fraction of the IMAGE height. It is
derived from how many head-heights the crop contains — a head is roughly 1/7.5 of
a standing body — and calibrated against the one measurement we have:

    waist-up, cast of 3, 4K, 3:4  ->  536 / 641 / 539 px, mean 572
    predicted: 0.17 * 0.70 * 4800 = 571

That is one point. Every other row is geometry hanging off it, which is why
`estimate_face_px` returns a band and the UI says "estimate". It exists to stop
someone spending a generation on a wide environmental shot of four people and
discovering afterwards that every face landed under the gate's 160px floor.
"""

# --------------------------------------------------------------------------
# FRAMING
# --------------------------------------------------------------------------
# `text` is written to be dropped into a prompt verbatim, directly after the
# shot-type opener. Each says what IS in frame and what is NOT — the negative
# half matters, because "head and shoulders" alone reads as a suggestion while
# "nothing below the collarbone is in shot" reads as a boundary.
#
# Nothing here describes a person. Same rule as every other library in this
# package: identity comes from the references, and describing her costs the
# measured 0.86 -> 0.53.
FRAMING: dict[str, dict] = {
    "": {"label": "Unspecified", "text": "", "face_frac": 0.17, "order": 0},

    "close_up": {
        "label": "Close-up (face)",
        "text": "Framed as a tight close-up: the face fills most of the frame, "
                "cropped at the top of the head and just under the chin. Nothing "
                "below the neck is in shot.",
        "face_frac": 0.55, "order": 1},

    "head_shoulders": {
        "label": "Head and shoulders",
        "text": "Framed head and shoulders: cropped just below the collarbone, "
                "faces filling the upper half of the frame. Nothing below the "
                "chest is in shot.",
        "face_frac": 0.35, "order": 2},

    "chest_up": {
        "label": "Chest up",
        "text": "Framed from the chest up, hands and arms mostly out of shot, "
                "the head comfortably clear of the top edge.",
        "face_frac": 0.25, "order": 3},

    "waist_up": {
        "label": "Waist up",
        "text": "Framed from roughly the waist up, so hands and what they are "
                "holding are visible.",
        "face_frac": 0.17, "order": 4},

    "knee_up": {
        "label": "Knee up (3/4 length)",
        "text": "A three-quarter length frame, cut at around the knee, with the "
                "full upper body and the stance visible.",
        "face_frac": 0.118, "order": 5},

    "full_body": {
        "label": "Full body",
        "text": "A full-length frame: the whole body from head to feet is in "
                "shot, with a little room above and below.",
        "face_frac": 0.09, "order": 6},

    "wide": {
        "label": "Wide / environmental",
        "text": "A wide environmental frame: the setting is as much the subject "
                "as the people in it, who occupy only part of the picture.",
        "face_frac": 0.045, "order": 7},

    "over_shoulder": {
        "label": "Over the shoulder",
        "text": "Shot over the shoulder of someone in the near foreground, who is "
                "soft and partly out of frame, looking past them at the subject.",
        "face_frac": 0.20, "order": 8},

    "from_behind": {
        "label": "From behind",
        "text": "Shot from behind, faces away from the camera or barely turned "
                "back — the picture is about posture and the view ahead.",
        # Faces are mostly absent. The gate will abstain and should: this is a
        # deliberate no-face frame, the same category as the POV shot.
        "face_frac": 0.06, "order": 9},
}


# --------------------------------------------------------------------------
# ASPECT
# --------------------------------------------------------------------------
# `nano-banana-pro/edit` takes `aspect_ratio` as a free-form string with no enum
# — checked against its schema — so a typo does not error, it silently returns a
# default-shaped image. That is why the verification step reads back PIXELS and
# not the request. This curated list is the set worth offering.
ASPECTS: list[dict] = [
    {"id": "1:1",  "label": "Square",           "w": 1, "h": 1},
    {"id": "4:5",  "label": "Portrait (feed)",  "w": 4, "h": 5},
    {"id": "3:4",  "label": "Portrait",         "w": 3, "h": 4},
    {"id": "2:3",  "label": "Portrait (tall)",  "w": 2, "h": 3},
    {"id": "9:16", "label": "Story / vertical", "w": 9, "h": 16},
    {"id": "4:3",  "label": "Landscape",        "w": 4, "h": 3},
    {"id": "3:2",  "label": "Landscape (wide)", "w": 3, "h": 2},
    {"id": "16:9", "label": "Widescreen",       "w": 16, "h": 9},
    {"id": "21:9", "label": "Cinematic",        "w": 21, "h": 9},
]

_ASPECT = {a["id"]: a for a in ASPECTS}

# Total pixels at each nano-banana resolution tier. Anchored on the one image we
# have measured: 4K at 3:4 came back 3584x4800, which is 17.2 MP. The tiers are
# 4x apart by name and behave that way.
_MEGAPIXELS = {"1K": 1.07e6, "2K": 4.3e6, "4K": 17.2e6}


def frame_height_px(aspect: str, resolution: str) -> int:
    """Pixel HEIGHT of the generated image, which is what a face is measured against.

    Height rather than width in both orientations: a standing person spans the
    short axis of a landscape frame just as she spans the long axis of a portrait
    one, so height is the dimension her face scales with either way.
    """
    a = _ASPECT.get(aspect) or _ASPECT["3:4"]
    mp = _MEGAPIXELS.get((resolution or "4K").upper(), _MEGAPIXELS["4K"])
    return int((mp * a["h"] / a["w"]) ** 0.5)


def cast_scale(cast: int) -> float:
    """How much a face shrinks when it has to share the frame.

    Calibrated on the one point available: a waist-up cast of three measured a
    mean 572px where a solo waist-up predicts 816, a ratio of 0.70. Linear in the
    cast size fits that better than 1/sqrt(n), which predicts 0.58 and would have
    under-called it.
    """
    return 1.0 / (1.0 + 0.22 * max(0, cast - 1))


def estimate_face_px(framing: str, cast: int, aspect: str, resolution: str) -> int:
    """Rough face-box height in pixels. An ESTIMATE, and labelled one everywhere.

    Compare against gate.FACE_PLATEAU_PX (400) and the gate's 160px abstain floor.
    Measured similarity by band, over 207 shots: <250px 0.472, 250-400 0.548,
    400-600 0.612, 600+ 0.608 — steep below the plateau, flat above it.
    """
    f = FRAMING.get(framing) or FRAMING[""]
    return int(f["face_frac"] * cast_scale(max(1, cast))
               * frame_height_px(aspect, resolution))
