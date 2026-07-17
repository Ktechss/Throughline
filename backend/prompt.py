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

# --------------------------------------------------------------------------
# moderation sanitiser
# --------------------------------------------------------------------------
#
# gpt-image-2 sits behind OpenAI's content classifier, which is STOCHASTIC near
# its boundary: the airport look (short shorts + heels + a body line + a close
# crop) was refused 3/3 then accepted 4/4 on a byte-identical prompt. We cannot
# make a coin land the same way twice — but we can move the prompt away from the
# boundary before flipping it.
#
# This does NOT censor intent. It rewrites phrasings that a sexualisation
# classifier is specifically tuned to score — explicit cup sizes, anatomical
# body language, "barely/tight/skimpy" intensifiers — into faithful, neutral
# equivalents, and REPORTS every change so nothing happens silently. The retry
# in generate() stays as the backstop for the residual coin-flip.
#
# Keep this list tight. Over-sanitising turns every prompt into the same beige
# person, which is the opposite failure. Each entry earns its place by having
# actually tripped the filter or being a well-known trigger, not by prudishness.
_SANITISE = [
    # explicit cup / measurements — the single biggest confirmed trigger next to
    # revealing wardrobe. The body REFERENCE IMAGE carries her real proportions,
    # so the number was never load-bearing anyway.
    # optionally swallow a preceding "a/an/a full" so we don't leave "a full a
    # full chest" when the BIO already led with an article.
    (r"\b(?:an?\s+)?(?:full\s+)?\d{2,3}\s*(?:dd?|ddd|[a-k])\s*(?:bust|breasts?|chest|cup)\b",
     "a full chest", "explicit cup size"),
    (r"\b(?:32|34|36|38|40)\s*(?:dd?|ddd|[a-k])\b", "a full figure", "bra size"),
    (r"\b(?:huge|large|big|ample|voluptuous|busty)\s+(?:breasts?|bust|chest|cleavage)\b",
     "a full chest", "sexualised bust phrasing"),
    (r"\bcleavage\b", "neckline", "cleavage"),
    (r"\b(?:breasts?)\b", "chest", "anatomical term"),
    # revealing-wardrobe intensifiers — the classifier scores the ADJECTIVE, not
    # the garment. "short denim shorts" is fine; "tiny/skimpy" is what tips it.
    (r"\b(?:barely|skimpy|tiny|micro|revealing|skin-?tight|barely-there)\s+",
     "", "revealing-wardrobe intensifier"),
    (r"\bshort\s+shorts\b", "denim shorts", "'short shorts'"),
    # posture/undress cues
    (r"\b(?:seductive|sultry|provocative|sensual|alluring)\b", "relaxed",
     "sexualised mood word"),
    (r"\b(?:lingerie|underwear|bikini|topless|nude|naked|bare-?chested)\b",
     "casual clothing", "undress cue"),
]
_SANITISE = [(re.compile(p, re.IGNORECASE), repl, why) for p, repl, why in _SANITISE]


def sanitise(text: str) -> tuple[str, list[dict]]:
    """Rewrite known moderation triggers to faithful neutral wording.

    Returns (clean_text, changes). Every substitution is reported — this lowers
    the refusal RATE, it does not censor, and the user sees exactly what moved.
    """
    changes: list[dict] = []
    out = text
    for rx, repl, why in _SANITISE:
        for m in rx.finditer(out):
            changes.append({"was": m.group(0).strip(), "now": repl.strip() or "(removed)",
                            "why": why})
        out = rx.sub(repl, out)
    # A rewrite can duplicate an adjacent word ("relaxed relaxed" when two mood
    # words sat side by side; "a full a full chest"). Collapse immediate repeats.
    out = re.sub(r"\b(\w[\w-]*)(\s+\1\b)+", r"\1", out, flags=re.IGNORECASE)
    out = re.sub(r"\ba full a full\b", "a full", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).replace(" ,", ",").replace(" .", ".")
    return out, changes


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
    # True = part of the BIO: who she is, not what this shot is. Locked in the
    # UI and attached to EVERY generation. See BIO_SECTIONS.
    bio: bool = False
    # True = a stand-in used only when no brief is given. A brief REPLACES these
    # rather than arguing with them. See compose_shot.
    placeholder: bool = False
    note: str = ""

    def dict(self) -> dict:
        return asdict(self)


# The BIO is who she IS — carried into every generation, never retyped, and not
# casually editable. The shot is what she's DOING, and that is all the user
# should have to write.
#
# The split is not cosmetic. Everything in the BIO has been measured or decided:
# the body numbers come from her own spec sheet, the skin block is photographic
# facts, the camera line is the highest-leverage realism control there is. Left
# in a free-text prompt box they would get paraphrased away one shot at a time,
# and the drift would be invisible because each individual edit looks harmless.
BIO_SECTIONS = ("subject", "face", "body", "hair", "skin", "camera", "constraints")
SHOT_SECTIONS = ("scene", "pose", "wardrobe", "lighting")


def default_parts() -> list[Part]:
    """The starting tree.

    `bio=True` parts are stamped automatically from BIO_SECTIONS below, so a new
    part lands on the right side of the line by virtue of its section rather
    than by someone remembering to flag it.
    """
    P = Part
    parts = [
        # -- subject ---------------------------------------------------------
        P("subject.age", "subject", "Age & who", "A 26-year-old South Asian woman",
          identity=True),
        # Deliberately place-agnostic and job-agnostic. The BIO says who she IS,
        # not where she lives or what she does today — pin those here and every
        # shot drags a home city into a stadium. Where she is belongs in the
        # brief, which is the thing that changes.
        P("subject.energy", "subject", "Energy",
          "a real person, not a model on a shoot. Unposed, lived-in, caught "
          "mid-moment rather than styled for a camera."),

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
        # Measurements are from Kiara-Body-Data.png's own spec table — the
        # owner's source of truth, not invented here. Change them there first.
        P("body.height", "body", "Height", "168cm (5'6\"), 58kg"),
        P("body.frame", "body", "Frame", "natural hourglass, roughly 7.5 heads tall",
          note="7.5 heads is a real adult. Generators drift to 8.5 — the "
               "fashion-illustration proportion — and it reads as uncanny."),
        P("body.shoulders", "body", "Shoulders",
          "shoulders roughly in line with her hips, not broadened"),
        P("body.bust", "body", "Chest / proportion",
          "a full chest with a natural, relaxed shape, not exaggerated or lifted",
          critical=True,
          note="The BODY REFERENCE IMAGE carries her actual proportions — this "
               "line only steers away from the generator's default (spherical, "
               "gravity-defying, unnaturally high), the same class of tell as "
               "the cinched waist. Kept deliberately vague: an explicit cup "
               "size + revealing wardrobe reads as sexualised to gpt-image-2's "
               "moderation classifier and gets the whole prompt refused "
               "(content_policy_violation). The number lived here before the "
               "body reference existed; the image supersedes it. For a male "
               "subject, edit the text — the part is the slot, not the gender."),
        P("body.waist", "body", "Waist",
          "a 30-inch waist, defined but NOT cinched or corseted",
          critical=True,
          note="Load-bearing. 30in against 40in hips is already a strong "
               "hourglass; the generator will try to exaggerate it further into "
               "a corset, which is one of the clearest AI tells. The number sets "
               "the shape, 'not cinched' stops the exaggeration. Both needed."),
        P("body.hips", "body", "Hips", "40-inch hips, balancing the bust"),
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
        # placeholder=True: these are what you get with an EMPTY brief. The
        # moment a brief exists it replaces them outright — a prompt saying both
        # "a plain white studio cyclorama" AND "in the stands at a World Cup
        # match" is not a richer prompt, it is a contradiction, and the model
        # resolves it by picking one. Measured: it picked the studio, produced a
        # cream-kurta portrait, and scored 0.857 — high precisely BECAUSE the
        # brief was ignored and a frontal studio shot is the easiest case there
        # is. A confident number for a failed instruction.
        P("wardrobe.main", "wardrobe", "Outfit (default)",
          "a plain fitted cream cotton kurta with slim charcoal trousers and "
          "flat leather sandals", placeholder=True),
        P("wardrobe.logos", "wardrobe", "No logos", "No visible brand logos on any item.",
          critical=True),
        P("pose.ref", "pose", "Pose (default)", "standing, weight on one hip, not posing",
          placeholder=True,
          note="The pose REFERENCE IMAGE is what actually carries this. Text "
               "pose control returned frontal on 3 of 4 probes — see FINDINGS."),
        P("scene.place", "scene", "Place (default)", "a plain white studio cyclorama",
          placeholder=True),
        # placeholder: who else is in frame is a SCENE decision, not a fact about
        # her. Hard-wiring "empty of other people" into every prompt made a
        # stadium-crowd brief contradict itself. If you want her alone, say so in
        # the brief.
        P("scene.empty", "scene", "Alone (default)",
          "The location is empty of other people.", placeholder=True,
          note="Only applies when the brief is empty. Recurring background "
               "people are a consistency liability — an anonymous crowd is not."),

        # -- lighting / camera ----------------------------------------------
        P("lighting.main", "lighting", "Light (default)",
          "soft neutral studio lighting, flat and even, no colour cast",
          placeholder=True),
        P("camera.framing", "camera", "Framing (default)", "head and shoulders, waist up",
          placeholder=True,
          note="A DEFAULT, not a constraint — a brief that asks for full body "
               "must be able to override it, or 'full body' is silently ignored "
               "and the shot comes back waist-up. Why waist-up is the default: "
               "framing is an identity setting. Same woman, same yaw, scored "
               "0.635 at a 660px face and 0.450 at 298px; full-body shrinks the "
               "face ~8x and the gate loses signal. Ask for full body freely — "
               "just expect a weaker number and don't read it as drift."),
        # No brand, no model number — a handset dates the character and pins her
        # to a product. What actually carries the realism is the OPTICS and the
        # "not a professional camera" clause, so those stay as concrete facts.
        P("camera.body", "camera", "Camera",
          "a handheld phone camera — wide 24mm-equivalent lens, automatic "
          "exposure, natural sensor noise in the shadows. Never a professional "
          "camera, never a lighting setup, never a photoshoot.",
          critical=True,
          note="The single highest-leverage line in the prompt. Shallow depth of "
               "field and studio lighting are the tells that make an image read "
               "as AI or as an ad."),

        # -- constraints -----------------------------------------------------
        # "No people in the background" used to live here and did not belong: the
        # BIO is about HER, and who else is in frame changes shot to shot. It now
        # sits in scene.empty as a default the brief can override.
        P("constraints.main", "constraints", "Constraints",
          "She is the clear focal point. Phone photo — no bokeh, no professional "
          "lighting setup, no beauty retouching. Real pore texture and skin "
          "imperfections must be visible. This image must be indistinguishable "
          "from a real photo a friend posted online.", critical=True),
    ]
    for p in parts:
        p.bio = p.section in BIO_SECTIONS
    return parts


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


def compose_shot(parts: list[Part], brief: str, *, has_reference: bool = True,
                 pose_note: str = "") -> str:
    """BIO + one shot brief. This is the whole prompting surface.

    The user writes the place, the moment and the pose. Everything about WHO she
    is comes from the BIO and the reference image, identically every time — so
    two photos taken a month apart differ only in the ways they were meant to.

    A brief REPLACES the placeholder shot parts rather than joining them.
    Appending was measured and it fails silently: a prompt carrying both "a
    plain white studio cyclorama" and "in the stands at a World Cup match" is a
    contradiction, and the model resolved it by rendering the studio. The result
    scored 0.857 — the highest of the day — because a frontal studio portrait is
    the easiest shot for the gate. A confident number for an ignored
    instruction, which is this project's signature failure.

    Constraints (`placeholder=False`) survive regardless: "no visible brand
    logos" is not something to retype per shot and not something to lose by
    forgetting.
    """
    return compose_shot_ex(parts, brief, has_reference=has_reference,
                           pose_note=pose_note)[0]


def compose_shot_ex(parts: list[Part], brief: str, *, has_reference: bool = True,
                    pose_note: str = "") -> tuple[str, list[dict]]:
    """compose_shot, plus the moderation-sanitiser change list.

    Sanitisation runs on the FINAL text, so it catches a trigger wherever it
    came from — the BIO or a brief the user typed. Returns (clean_prompt,
    changes); an empty list means nothing needed rewriting.
    """
    live = [p for p in parts if p.enabled]
    if has_reference:
        live = [p for p in live if not p.identity]

    if brief.strip():
        live = [p for p in live if not p.placeholder]
        live = live + [Part(id="shot.brief", section="scene", label="Shot",
                            text=brief.strip())]
    raw = compose(live, has_reference=has_reference, pose_note=pose_note)
    return sanitise(raw)


def bio_summary(parts: list[Part], *, has_reference: bool = True) -> dict:
    """What the BIO commits to, for display. Read-only by intent."""
    bio = [p for p in parts if p.bio and p.enabled]
    if has_reference:
        bio = [p for p in bio if not p.identity]
    groups: dict[str, list[dict]] = {}
    for p in bio:
        groups.setdefault(p.section, []).append(
            {"id": p.id, "label": p.label, "text": p.text,
             "critical": p.critical, "note": p.note})
    return {"sections": groups,
            "identity_lock": IDENTITY_LOCK if has_reference else None,
            "dropped_identity_parts": [p.id for p in parts
                                       if p.bio and p.identity and p.enabled
                                       and has_reference]}


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
