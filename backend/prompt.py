"""The prompt as editable parts, not a wall of text.

Every part is individually editable, toggleable and reorderable from the UI, and
`compose()` assembles them into the final prompt. Nothing here is a fixed string
the UI can't reach — that is the whole point.

## Two rules the schema enforces, because they were expensive to learn

**1. Identity parts are OFF once a reference image exists.** Describing a face
measurably produces a stranger who matches the description: reference + terse
"don't change her" scored 0.860, reference + full description 0.834, description
alone 0.531. Words cannot specify a person. So `identity=True` parts are for the
SEED HUNT only — the phase where you have no reference and are shopping for a
face. The moment a face is chosen they become actively harmful, and `compose()`
drops them when a reference is present rather than trusting anyone to remember.

**2. Sections, not keyword soup.** Attention dilutes across a prompt. A
structured brief (Scene / Subject / Pose / Wardrobe / Lighting / Camera / Skin /
Constraints) survives that far better than 700 words of comma-separated
micro-detail, which is what the first attempt was and which could not specify a
person at all.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# Words that mark AI slop. The UI warns on these rather than blocking — a banned
# word inside a quoted brand name or a scene description is sometimes correct.
BANNED = (
    "stunning", "ethereal", "hyper-realistic", "8k", "ultra-detailed", "perfect",
    "glowing", "symmetrical", "flawless", "editorial", "fashion shoot",
    "masterpiece", "breathtaking", "gorgeous", "beautiful", "cinematic", "bokeh",
)

# Order here is render order within a section.
SECTIONS = ["subject", "face", "body", "hair", "skin", "wardrobe",
            "pose", "scene", "lighting", "camera", "constraints"]

# Which sections are prose blocks vs joined fragments.
BLOCK_SECTIONS = {"skin", "constraints"}


@dataclass
class Part:
    id: str
    section: str
    label: str
    text: str
    enabled: bool = True
    # True = this part DESCRIBES her. Dropped automatically once a reference
    # image is in play. See rule 1 above.
    identity: bool = False
    # True = load-bearing; the UI shows a warning before disabling it.
    critical: bool = False
    note: str = ""

    def dict(self) -> dict:
        return asdict(self)


def default_parts() -> list[Part]:
    """The starting tree. Everything is editable; nothing here is sacred except
    where `critical` says otherwise."""
    P = Part
    return [
        # -- subject ---------------------------------------------------------
        P("subject.age", "subject", "Age & who", "A 26-year-old South Asian woman",
          identity=True),
        P("subject.energy", "subject", "Energy",
          "a working fashion stylist in South Delhi; carries the end-of-day "
          "energy of someone who has been on her feet since six. Real person, "
          "not a model on a shoot. Lived-in."),

        # -- face (SEED HUNT ONLY) -------------------------------------------
        P("face.eyes", "face", "Eyes", "large almond dark-brown eyes", identity=True),
        P("face.brows", "face", "Brows", "naturally thick, softly arched brows", identity=True),
        P("face.nose", "face", "Nose", "a straight nose with a narrow bridge", identity=True),
        P("face.lips", "face", "Lips", "medium-full lips, muted dusty rose", identity=True),
        P("face.shape", "face", "Face shape", "a soft oval face with a gently tapered jaw", identity=True),
        P("face.marks", "face", "Distinguishing marks",
          "a small mole above the left side of the upper lip, one beneath the "
          "right cheekbone, faint freckles across the nose bridge", identity=True,
          note="Asymmetric marks are the cheapest identity anchor there is — "
               "but only during the seed hunt."),

        # -- body ------------------------------------------------------------
        # Granular on purpose. "Athletic build" is a wish; a generator resolves
        # it into whatever its training data thinks that means, which is a
        # 8.5-head fashion plate with a corseted waist. Each part below is a
        # place to push back against a specific default.
        P("body.height", "body", "Height", "167cm"),
        P("body.frame", "body", "Frame", "natural hourglass, roughly 7.5 heads tall",
          note="7.5 heads is a real adult. Generators drift to 8.5 — the "
               "fashion-illustration proportion — and it reads as uncanny."),
        P("body.shoulders", "body", "Shoulders",
          "shoulders roughly in line with her hips, not broadened"),
        P("body.bust", "body", "Bust / chest",
          "a full bust, 36D, with natural shape and weight — sitting where real "
          "breasts sit, not spherical, not lifted",
          critical=True,
          note="Load-bearing, same class of tell as the waist. Generators "
               "default to spherical, gravity-defying, unnaturally high. "
               "'Natural shape and weight' is the pushback; drop it and you get "
               "the default. For a male subject, edit this text to the chest "
               "you want (e.g. 'a broad flat chest, natural pectoral shape, "
               "visible collarbone') — the part is the slot, not the gender."),
        P("body.waist", "body", "Waist", "a defined but NOT cinched or corseted waist",
          critical=True,
          note="Load-bearing. The over-snatched waist is one of the clearest AI "
               "tells and generators default to it. Push back every time."),
        P("body.hips", "body", "Hips", "hips balancing the bust, natural width"),
        P("body.legs", "body", "Legs", "notably long legs, a high leg-to-torso ratio"),
        P("body.posture", "body", "Posture", "elegant posture, a long neck"),

        # -- hair / skin -----------------------------------------------------
        P("hair.base", "hair", "Hair",
          "very long jet-black hair to the waist, centre part, soft waves from "
          "shoulder level", identity=True),
        P("skin.tone", "skin", "Tone", "warm neutral beige skin with a golden undertone",
          identity=True),
        P("skin.facts", "skin", "Photographic facts",
          "— Visible pores across the nose and inner cheeks, micro-shadows falling away from the key light\n"
          "— Faint sheen at the temples and along the nose bridge; the rest matte\n"
          "— Lips slightly dry at the outer edges, natural colour, no gloss\n"
          "— Two or three loose baby hairs escaping at the temple, catching the light\n"
          "— Peach fuzz visible along the jawline where the key light rakes across\n"
          "— Fine sensor noise in the shadow side of her face, consistent with a phone at this light level",
          critical=True,
          note="Photographic FACTS, never adjectives. A model can render a fact; "
               "it cannot render a wish. 'Visible pores with micro-shadow "
               "direction' beats 'realistic skin' every time."),

        # -- wardrobe / pose / scene ----------------------------------------
        P("wardrobe.main", "wardrobe", "Outfit",
          "a plain fitted cream cotton kurta with slim charcoal trousers and "
          "flat leather sandals"),
        P("wardrobe.logos", "wardrobe", "No logos", "No visible brand logos on any item.",
          critical=True),
        P("pose.ref", "pose", "Pose", "standing, weight on one hip, not posing",
          note="The pose REFERENCE IMAGE is what actually carries this. Text "
               "pose control returned frontal on 3 of 4 probes — see FINDINGS."),
        P("scene.place", "scene", "Place", "a plain white studio cyclorama"),
        P("scene.empty", "scene", "Emptiness",
          "The location is empty of other people.", critical=True,
          note="Other people are a consistency liability, not realism."),

        # -- lighting / camera ----------------------------------------------
        P("lighting.main", "lighting", "Light",
          "soft neutral studio lighting, flat and even, no colour cast"),
        P("camera.body", "camera", "Camera",
          "iPhone 16 Pro, 24mm main lens, f/1.78, handheld, automatic settings, "
          "natural sensor noise in shadows. Never a professional camera.",
          critical=True,
          note="The single highest-leverage line in the prompt. Shallow depth of "
               "field and studio lighting are the tells that make an image read "
               "as AI or as an ad."),

        # -- constraints -----------------------------------------------------
        P("constraints.main", "constraints", "Constraints",
          "No people anywhere in the background. The subject is the clear focal "
          "point. Phone photo — no bokeh, no professional lighting setup, no "
          "beauty retouching. Real pore texture and skin imperfections must be "
          "visible. This image must be indistinguishable from a real photo a "
          "friend posted on Instagram.", critical=True),
    ]


SYSTEM = (
    "You render photographs that are indistinguishable from a real photo a "
    "friend posted to Instagram. Handheld phone, natural found light, real "
    "location, zero professional photography setup, zero retouching. Never "
    "produce anything that reads as a fashion shoot, a studio session, or a "
    "rendered image."
)

# What replaces every identity part once a face exists. Terse on purpose: this
# exact phrasing measured 0.860 where a full description measured 0.834 and no
# reference measured 0.531.
IDENTITY_LOCK = (
    "She is the woman in the reference image and must remain exactly this "
    "person. Do not regenerate, reinterpret or beautify her face."
)

TITLES = {
    "subject": "Subject", "face": "Face", "body": "Build", "hair": "Hair",
    "skin": "Skin (concrete photographic facts, not adjectives)",
    "wardrobe": "Wardrobe & details", "pose": "Pose", "scene": "Scene",
    "lighting": "Lighting", "camera": "Camera & capture",
    "constraints": "Constraints",
}


def compose(parts: list[Part], *, has_reference: bool = False,
            pose_note: str = "") -> str:
    """Parts -> the final prompt.

    `has_reference=True` drops every identity part and substitutes IDENTITY_LOCK.
    That is not a convenience — it is the schema refusing to let anyone hand the
    model a face description and a face reference at the same time, which is the
    0.531 case.
    """
    live = [p for p in parts if p.enabled]
    if has_reference:
        live = [p for p in live if not p.identity]

    chunks: list[str] = []
    for section in SECTIONS:
        got = [p for p in live if p.section == section]
        if not got:
            continue
        title = TITLES.get(section, section.title())

        if section == "pose" and pose_note:
            body = "; ".join(p.text.strip().rstrip(".") for p in got)
            body = f"{body}. {pose_note}" if body else pose_note
        elif section in BLOCK_SECTIONS:
            body = "\n".join(p.text.strip() for p in got)
        else:
            body = "; ".join(p.text.strip().rstrip(".") for p in got)
            if body and not body.endswith("."):
                body += "."

        if section in ("subject", "face", "body", "hair") and has_reference:
            continue  # folded into the identity lock below
        chunks.append(f"{title}: {body}" if section not in BLOCK_SECTIONS
                      else f"{title}:\n{body}")

    if has_reference:
        # Rebuild the non-identity half of subject/body/hair that we just skipped.
        keep = [p for p in live if p.section in ("subject", "body", "hair")]
        if keep:
            body = "; ".join(p.text.strip().rstrip(".") for p in keep) + "."
            chunks.insert(0, f"Subject: {IDENTITY_LOCK} {body}")
        else:
            chunks.insert(0, f"Subject: {IDENTITY_LOCK}")

    return "\n\n".join(chunks)


# Negations. "no bokeh" and "zero retouching" are the prompt doing its job —
# flagging them as slop is how a linter teaches people to ignore it.
_NEGATED = re.compile(r"\b(no|not|never|zero|without|avoid)\s+(\w+\s+){0,2}$")


def _slop_hits(text: str) -> list[str]:
    """Banned words actually used as wishes.

    Word-boundary matched, because substring matching fires on 'imperfections'
    for 'perfect' — which is the exact opposite of the word we're policing.
    """
    hits = []
    low = text.lower()
    for w in BANNED:
        for m in re.finditer(rf"\b{re.escape(w)}\b", low):
            if _NEGATED.search(low[:m.start()]):
                continue
            hits.append(w)
            break
    return hits


def lint(parts: list[Part], *, has_reference: bool = False) -> list[dict]:
    """Warnings, never blocks. The UI shows these next to the offending part."""
    out = []
    for p in parts:
        if not p.enabled:
            if p.critical:
                out.append({"id": p.id, "level": "warn",
                            "msg": f"'{p.label}' is load-bearing and is disabled. {p.note}"})
            continue
        for w in _slop_hits(p.text):
            out.append({"id": p.id, "level": "warn",
                        "msg": f"'{w}' is an AI-slop marker — it reads as a wish, not a fact."})
        if has_reference and p.identity:
            out.append({"id": p.id, "level": "info",
                        "msg": "Dropped automatically: a reference image is in play, "
                               "and describing her measured 0.834 vs 0.860 terse."})
    return out
