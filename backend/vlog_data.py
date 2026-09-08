"""WHAT A PHONE VLOG IS ACTUALLY MADE OF.

A vlog is not a short film. It is a pile of short, badly-framed, self-shot
fragments cut together, and the two things that make it read as one are that the
camera keeps FLIPPING — her face, then what she is looking at, then her face —
and that nothing is held for long.

THE ONE STRUCTURAL FACT EVERYTHING HERE FOLLOWS FROM. Every video model on kie
is image-to-video and NONE of them takes an aspect ratio (verified against
providers.KIE_VIDEO: only poyo's runway-4.5 and sora-2 accept one, and poyo has
no key). So a clip is the shape of its start image, and a beat is therefore
always TWO spends: a 9:16 still, then the clip made from it. Vertical footage is
decided at the still, never at the video.

WHY THE FRONT/BACK SPLIT IS THE WHOLE DESIGN, and not just vocabulary:

    front   she is in frame. The clip inherits her identity from frame one, so
            the still MUST be one the gate kept. This is the expensive half —
            it can fail, and a failed still is a spend with nothing to show.

    back    the world is in frame and she is not. There is no face to verify,
            so scoring it is meaningless — the same reasoning that makes a
            wardrobe turnaround `gated=False`: a photograph of a street is not
            a photograph of her. This half cannot fail on identity at all.

Roughly half a real vlog is `back`, which means roughly half of it carries no
identity risk and needs no gate. That is not a compromise; it is what the form
already looks like.

AND THE CUTS ARE THE POINT. `continue_from` chains a clip off the previous
clip's last frame, which is the only way to run past Kling's 10s cap — but
every link then starts from a GENERATED frame, so drift compounds, and the
frame scoring that would make that visible does not exist yet (generate.py's
verdict for a clip still reads "frame scoring not yet applied"). A vlog cuts
every few seconds by nature, so each beat can re-anchor on its own approved
still and the drift never accumulates. The aesthetic and the engineering want
the same thing here, which is rare enough to be worth writing down.

`still` is what the 9:16 frame has to SHOW. `motion` is what the video model is
told to do with it. They are separate because they are two different spends and
two different failure modes: a still that is wrong costs a still, a motion that
is wrong costs a clip.
"""
from __future__ import annotations


# Nothing here describes her face. On the front beats the still is generated
# from her reference the same way every other shot is, and prompt.compose drops
# identity parts when a reference exists (measured: reference + terse 0.860,
# description alone 0.531). These strings only ever say what the CAMERA does.
BEATS: dict[str, dict[str, dict]] = {
    # ------------------------------------------------------------------ front
    "Front camera — her": {
        "walk-and-talk": {
            "label": "Walking and talking",
            "camera": "front", "subject": True, "seconds": 5,
            "still": "Held at arm's length on the front camera while she walks, "
                     "the phone slightly above eye level and angled down, her "
                     "face filling much of a tall vertical frame, the street "
                     "falling away behind her and out of focus at the edges.",
            "motion": "She is mid-sentence to the camera as she walks — her head "
                      "bobs very slightly with each step, the frame sways with "
                      "her arm, the background slides past behind her. Her mouth "
                      "moves naturally; her eyes stay on the lens.",
        },
        "reaction-face": {
            "label": "Pulling a face",
            "camera": "front", "subject": True, "seconds": 4,
            "still": "Front camera held close, her face filling most of a tall "
                     "vertical frame, caught mid-expression rather than posed.",
            "motion": "One quick expression and a settle: her eyebrows go up, "
                      "her eyes widen at the lens, and she breaks into a small "
                      "laugh. The phone shifts a little in her hand. Nothing "
                      "else in the frame changes.",
        },
        "whisper-close": {
            "label": "Close to the lens",
            "camera": "front", "subject": True, "seconds": 4,
            "still": "The phone very close on the front camera, her face large "
                     "in a tall vertical frame, slight wide-angle stretch, the "
                     "room behind her thrown out of focus.",
            "motion": "She leans in a little closer to the lens and says "
                      "something quietly, glancing once to the side and back. "
                      "Small movement only — the frame is nearly still.",
        },
        "hair-and-check": {
            "label": "Fixing her hair",
            "camera": "front", "subject": True, "seconds": 5,
            "still": "Front camera at arm's length, her face and shoulders in a "
                     "tall vertical frame, caught between poses.",
            "motion": "She tucks her hair back behind one ear, checks her own "
                      "face in the screen, and looks back at the lens. Her "
                      "raised hand passes briefly through the lower frame.",
        },
        "show-and-tell": {
            "label": "Holding something up",
            "camera": "front", "subject": True, "seconds": 5,
            "still": "Front camera at arm's length, her face to one side of a "
                     "tall vertical frame and her other hand raised into the "
                     "frame beside it, holding something up toward the lens.",
            "motion": "She lifts what she is holding closer to the lens, looks "
                      "from it back to the camera, and grins. The object comes "
                      "briefly out of focus as it nears the lens.",
        },
        "sunglasses": {
            "label": "Glasses on or off",
            "camera": "front", "subject": True, "seconds": 4,
            "still": "Front camera at arm's length outdoors, bright daylight, "
                     "her face filling much of a tall vertical frame.",
            "motion": "She pushes her sunglasses up onto her head, squints "
                      "against the light, and laughs at the lens. Her hand "
                      "leaves the frame at the top.",
        },
    },

    # ------------------------------------------------------------------- back
    # Nobody is in these. They are the cheap half and they cannot fail the gate,
    # because there is nothing in them to score.
    "Back camera — what she sees": {
        "street-ahead": {
            "label": "Walking, street ahead",
            "camera": "back", "subject": False, "seconds": 5,
            "still": "Shot on a phone in tall vertical format, the frame looking straight down a busy "
                     "street at eye level, held while walking — shopfronts and "
                     "signage down both sides, the pavement running away ahead. "
                     "No one is looking at the camera.",
            "motion": "The camera walks forward at a normal pace — the whole "
                      "frame rises and falls slightly with each step and the "
                      "street slides toward the lens. Nothing else is directed.",
        },
        "shopfront-pan": {
            "label": "Panning a shopfront",
            "camera": "back", "subject": False, "seconds": 5,
            "still": "Shot on a phone in tall vertical format, the frame of a shopfront from across a "
                     "narrow pavement — window display, lettering above, awning.",
            "motion": "The camera pans slowly and a little unevenly along the "
                      "shopfront, the way a hand pans rather than a tripod, and "
                      "comes to rest.",
        },
        "food-down": {
            "label": "Looking down at food",
            "camera": "back", "subject": False, "seconds": 4,
            "still": "Shot on a phone in tall vertical format, the frame looking down onto a café table "
                     "from her seat — the plate, a glass, cutlery, the table "
                     "edge, taken at a slight angle rather than flat overhead.",
            "motion": "The camera drifts slowly over the table and steadies on "
                      "the plate. Steam moves; a hand may enter the lower frame "
                      "and reach toward the food.",
        },
        "feet-walking": {
            "label": "Her feet on the pavement",
            "camera": "back", "subject": False, "seconds": 4,
            "still": "Shot on a phone in tall vertical format, the frame angled steeply down at the "
                     "pavement, her own shoes mid-stride at the bottom of the "
                     "frame. No face, no upper body.",
            "motion": "Two or three steps: the shoes move forward in turn and "
                      "the pavement scrolls beneath them, the frame swinging "
                      "gently with her arm.",
        },
        "tilt-up": {
            "label": "Tilting up a building",
            "camera": "back", "subject": False, "seconds": 5,
            "still": "Shot on a phone in tall vertical format, the frame at the base of a building "
                     "looking up its face, strong perspective, sky at the top.",
            "motion": "The camera tilts up the building to the sky in one slow, "
                      "slightly unsteady movement, and holds there.",
        },
        "hand-door": {
            "label": "Pushing a door open",
            "camera": "back", "subject": False, "seconds": 4,
            "still": "Shot on a phone in tall vertical format, the frame facing a shop or café door "
                     "from just outside it, one hand entering the frame toward "
                     "the handle.",
            "motion": "The hand pushes the door and the camera walks through it "
                      "— the interior brightens and opens out as the door swings "
                      "away from the lens.",
        },
        "outfit-flatlay": {
            "label": "The outfit on the bed",
            "camera": "back", "subject": False, "seconds": 4,
            "still": "Shot on a phone in tall vertical format, the frame looking down at clothes laid "
                     "out on a bed — the outfit arranged flat, shoes beside it, "
                     "taken at a slight angle rather than straight overhead.",
            "motion": "The camera drifts slowly across the laid-out clothes and "
                      "settles. A hand may enter the lower frame and straighten "
                      "a sleeve.",
        },
        "closet-scan": {
            "label": "Panning the closet rail",
            "camera": "back", "subject": False, "seconds": 4,
            "still": "Shot on a phone in tall vertical format, the frame of a hanging rail in an open "
                     "wardrobe, garments packed along it, one pulled slightly "
                     "forward.",
            "motion": "The camera pans along the rail and stops on one garment; "
                      "a hand reaches in and pushes a hanger aside.",
        },
        "market-bustle": {
            "label": "The street, standing still",
            "camera": "back", "subject": False, "seconds": 5,
            "still": "Shot on a phone in tall vertical format, the frame of a busy street corner or "
                     "market from a standing position, people mid-movement and "
                     "none of them looking at the camera.",
            "motion": "The camera holds roughly still with small handheld drift "
                      "while traffic and people move through the frame.",
        },
    },
}


# A vlog that is all talking heads is not a vlog; one that is all b-roll has no
# author. Real ones alternate, and they open on her face so the viewer knows
# whose day this is. These are starting points the owner reorders, not a format.
SHAPES: dict[str, dict] = {
    "walk": {
        "label": "Street walk (~27s)",
        "note": "Opens on her, cuts out to what she is seeing, comes back.",
        "beats": ["walk-and-talk", "street-ahead", "reaction-face",
                  "shopfront-pan", "walk-and-talk", "tilt-up"],
    },
    "cafe": {
        "label": "Café stop (~26s)",
        "note": "Arriving, ordering, the food, her verdict on it.",
        "beats": ["hand-door", "whisper-close", "food-down", "reaction-face",
                  "walk-and-talk", "market-bustle"],
    },
    "getting-ready": {
        "label": "Getting ready (~26s)",
        "note": "Indoors, uses the places she already has rather than new plates.",
        "beats": ["closet-scan", "hair-and-check", "outfit-flatlay",
                  "show-and-tell", "whisper-close", "walk-and-talk"],
    },
    "quick": {
        "label": "Quick post (~13s)",
        "note": "The cheapest thing that still reads as a vlog: three beats.",
        "beats": ["walk-and-talk", "street-ahead", "reaction-face"],
    },
}


def beat(bid: str) -> dict | None:
    """One beat by id, with its id and group folded in."""
    for group, items in BEATS.items():
        if bid in items:
            return {**items[bid], "id": bid, "group": group}
    return None


def all_beats() -> list[dict]:
    return [{**b, "id": i, "group": g}
            for g, items in BEATS.items() for i, b in items.items()]


def shape(name: str) -> list[dict]:
    """A named shape resolved to its beats. Unknown ids are dropped rather than
    raising: the vocabulary is data and may be edited underneath a saved plan."""
    spec = SHAPES.get(name) or {}
    return [b for b in (beat(i) for i in spec.get("beats", [])) if b]
