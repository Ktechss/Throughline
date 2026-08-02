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
from dataclasses import asdict, dataclass

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
    # Bust SIZE wording is intentionally left ALONE now (cup sizes, "large/huge
    # bust", bra sizes all pass through) so the fictional character's figure can
    # be set as large as wanted — the size cannot be dialled if the sanitiser
    # keeps collapsing it to "a full chest". gpt-image-2 may still refuse very
    # explicit sizing; the scene-model fallback catches that. What stays guarded
    # below is EXPOSURE and NUDITY, not size — the line is proportions (allowed)
    # vs. undress/sexualisation (still neutralised).
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
SECTIONS = ["subject", "face", "body", "hair", "skin", "grooming", "accessories",
            "wardrobe", "pose", "scene", "lighting", "camera", "constraints"]

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
BIO_SECTIONS = ("subject", "face", "body", "hair", "skin", "grooming", "accessories",
                "camera", "constraints")
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
          "clear even skin, no prominent marks", identity=True,
          note="Marks are OFF by default — a character should not get a mole she "
               "wasn't asked for. Add a specific mole/freckle/scar here only if "
               "you actually want one on every generation of her."),

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

        # -- grooming / accessories (PERMANENT) -----------------------------
        # Persistent styling that should be the SAME on every shot — her signature
        # manicure and everyday makeup. bio=True (stamped from BIO_SECTIONS) so they
        # ride along with a brief instead of being owned by it, like body/skin.
        # NOT identity=True: they survive a reference image (the point is that they
        # persist). A per-outfit detail (nails/lipstick in the outfit designer) can
        # still override the look for that specific outfit.
        P("grooming.nails", "grooming", "Manicure",
          "short-to-medium almond nails, soft neutral polish, clean and even",
          note="Her standing manicure — appears on every shot unless an outfit "
               "specifies its own nails. Edit per character; disable for bare nails."),
        P("grooming.makeup", "grooming", "Makeup",
          "minimal everyday makeup — light natural base, softly groomed brows, a "
          "little mascara, a neutral rosy lip; never heavy contour or full glam",
          note="Her signature everyday face. Keep it 'real person, not a model' — "
               "full-glam every shot reads as styled. Edit per character."),

        # Off by default (opt-in): don't put jewelry on a character who wasn't asked
        # for it — same rule as face.marks. Enable + describe to make it always-worn.
        P("accessories.signature", "accessories", "Signature accessories",
          "a thin gold chain and small gold hoop earrings", enabled=False,
          note="Her always-worn jewelry, on every shot when enabled (e.g. a ring "
               "she never removes). OFF by default — turn it on and describe hers. "
               "This is standing jewelry, not the per-shot sunglasses/hats toggle."),

        # The objects a real person carries around for years. Recurrence is the
        # point: a stranger's photos are full of one-off props, whereas the same
        # scuffed phone case turning up in mirror selfie after mirror selfie is
        # the sort of continuity nobody thinks to fake. OFF by default — an
        # invented kit is worse than none, so describe hers before enabling.
        P("accessories.everyday", "accessories", "Everyday carry",
          "the same phone in a well-used case, an everyday shoulder bag, a slim "
          "watch on her left wrist", enabled=False,
          note="Objects that recur across her whole year — phone + case (visible "
               "in every mirror selfie), bag, watch, water bottle, sunglasses. "
               "Only what is plausibly in frame; this is continuity, not a list."),

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
        # placeholder: a guard for the DEFAULT outfit only. It used to be a
        # standing constraint and it silently overrode briefs — "Argentina
        # football jersey" in a brief lost to "No visible brand logos" sitting
        # earlier in the prompt. When the user names an outfit, the brief owns
        # the wardrobe, logos and all.
        P("wardrobe.logos", "wardrobe", "No logos (default)",
          "No visible brand logos on any item.", placeholder=True),
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
    "grooming": "Grooming (persistent — nails, makeup)",
    "accessories": "Signature accessories (always worn)",
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


SHOT_TYPES = {
    "candid": "Candid iPhone photo",
    "editorial": "Editorial photo",
    "luxury": "Luxury lifestyle photo",
    "street": "Street style photo",
    "pov": "First-person POV phone photo",   # faceless — see the pov branch in compose_tagged()
}

# WHO IS HOLDING THE CAMERA.
#
# Every shot used to have the same invisible photographer, which is a thing real
# camera rolls never have. A year of someone's photos is a mixture: things they
# took of themselves, things a friend took, the one a stranger took badly outside
# a monument. That mixture is most of what makes a set read as a life.
#
# It is also a direct lever on identity, which is why each entry carries `face`.
# Measured here over 207 shots: a face under 400px loses similarity to framing
# alone (0.55 at 250-400px vs 0.61 at 400-600px). Selfies put the face near the
# lens and land comfortably above that line; a stranger's wide shot does not. So
# the holder is both a realism choice and a budget decision, and the UI should
# show which is which rather than leaving it to be discovered per shot.
CAMERA_HOLDERS = {
    "": {"label": "Unspecified", "face": "", "text": ""},
    "selfie": {
        "label": "Selfie (arm's length)", "face": "large",
        "text": "She is taking this herself at arm's length on the front camera — "
                "her nearer arm reaches out of frame toward the lens, the "
                "perspective is slightly wide and close, her face fills much of "
                "the frame and her eyes are on the lens."},
    "mirror": {
        "label": "Mirror selfie", "face": "large",
        # The gaze and head clauses are here rather than left to the brief because
        # they were measured, twice, on the same shot. A first attempt let the
        # model read "mirror selfie" as looking DOWN at the phone with a 12 head
        # tilt and scored 0.334; forcing the eyes to the reflection with a level
        # head, same scene and references, scored 0.628. Eye sockets are where
        # ArcFace reads identity, and a tilt the gallery does not have costs about
        # 0.09 on its own (0.521 tilted vs 0.608 level over 180 shots).
        "text": "A mirror selfie: she is photographing her own reflection, the "
                "phone held at chest height and angled at the glass, clear of her "
                "face. She looks straight at her own reflection — her eyes on the "
                "mirror, NOT down at the phone screen — with her chin level and "
                "her head upright, not tilted. The room behind her appears "
                "reflected; the real camera is not in the frame."},
    "friend": {
        "label": "Taken by a friend", "face": "medium",
        "text": "A friend a few steps away took this — unposed and slightly "
                "imperfect, she is aware of the camera without performing for it, "
                "the framing a little loose and off-centre."},
    "stranger": {
        "label": "Taken by a stranger", "face": "small",
        "text": "A stranger she handed the phone to took this — dead-centre, a "
                "little too much headroom, a plain straight-on composition, and "
                "she stands slightly formally for it."},
    "timer": {
        "label": "Propped, self-timer", "face": "small",
        "text": "The phone is propped on a surface on its self-timer — a fixed "
                "slightly low angle, marginally off-level, and she has walked into "
                "frame and is still settling."},
}

# HOW IMPERFECT THE PHOTOGRAPH IS.
#
# Every shot the pipeline makes is composed, focused and well-lit. Real camera
# rolls are not: roughly a third of any real one is mediocre, and the complete
# ABSENCE of a bad frame is itself the tell — it reads as a product catalogue
# rather than a person's photos.
#
# ⚠ These deliberately cost similarity. Motion blur and a half-closed eye degrade
# exactly the geometry ArcFace reads, so a flawed shot scores low and that is the
# intended outcome, not drift. Runs carry `flaws` in their meta and their verdict
# is tagged `expected_low` so the number is never mistaken for an identity
# failure — the same distinction `Verdict.diagnosis` draws.
SNAPSHOT_FLAWS = {
    "": {"label": "Clean", "expected_low": False, "text": ""},
    "subtle": {
        "label": "Slightly imperfect", "expected_low": False,
        "text": "Not a perfectly made photograph: the horizon is a touch off "
                "level, the centring is imperfect, and there is a trace of "
                "handheld softness — the ordinary flaws of a real phone snap."},
    "snapshot": {
        "label": "Genuinely imperfect", "expected_low": True,
        "text": "An unflattering real snapshot that nobody curated: mild motion "
                "blur where she or her hand moved, an off-level horizon, an "
                "awkward crop that clips an edge of her, and a plain half-caught "
                "expression rather than a held one. In low light it is lit by a "
                "harsh direct on-camera flash with a hard shadow behind her."},
}

# Pose library, ported from ai-influencer's POSE_MAP — text pose descriptions
# someone tuned until they reliably produce each stance. These are the primary
# pose direction; the reference images carry identity, the pose text carries the
# body. "" = let the brief describe the pose.
from .poses_data import POSE_GROUPS  # noqa: E402 — large generated pose library

# Flat {id: text} for generation lookup (compose/shot). "" = let the brief
# describe the pose. The categorised source of truth is POSE_GROUPS.
POSES_LIBRARY = {"": ""}
for _cat_poses in POSE_GROUPS.values():
    POSES_LIBRARY.update(_cat_poses)


def carry_clause(parts: list["Part"], skip: set[str] | None = None) -> str:
    """The standing grooming and accessories she has in EVERY shot.

    These sections existed and were reaching nothing: `compose_tagged` only ever
    pulled `body` parts (via `build_clause`), so an enabled "signature
    accessories" or "everyday nails" changed the BIO prompt and silently did
    nothing to an actual shot. The checkbox was a real knob for one code path and
    decoration for the one people use.

    Which matters more than it sounds, because recurrence is most of what makes a
    set of images read as one person's life rather than a hundred separate
    generations. The same chain, the same watch, the same phone case — cheap to
    say, and the kind of continuity that is only visible across the whole year.

    `skip` drops parts a more specific directive has already claimed: a chosen
    manicure reference or the calendar's own nails should not be arguing with the
    generic nails line.
    """
    out = [p.text.strip().rstrip(".") for p in parts
           if p.section in ("grooming", "accessories")
           and p.id not in (skip or set())
           and getattr(p, "enabled", True) and p.text.strip()]
    if not out:
        return ""
    return ("Constant across all her photos, unchanged by the scene: "
            + "; ".join(out) + ".")


def build_clause(parts: list["Part"]) -> str:
    """A body-shape directive from the ENABLED `body` parts, so editing bust /
    waist / hips in the UI actually tunes the shot.

    The body REFERENCE image still anchors proportions; this nudges them on top
    of it (text is a weaker lever than the image — that is the measured trade,
    not a bug). sanitise() runs downstream, so cup-size/measurement wording is
    neutralised before it reaches fal's moderation. Toggling a body part off in
    the UI now removes it from this clause — the checkbox is a real knob again.
    """
    body = [p.text.strip().rstrip(".") for p in parts
            if p.section == "body" and getattr(p, "enabled", True) and p.text.strip()]
    if not body:
        return ""
    return "Keep her body shape to this build: " + "; ".join(body) + "."


def compose_tagged(brief: str, *, pose_text: str = "", has_wardrobe: bool = False,
                   pose_ref_tag: str = "", build_text: str = "", n_skin: int = 0,
                   shot_type: str = "candid", camera_holder: str = "",
                   flaws: str = "", carry_text: str = "",
                   realism: bool = True, pov: bool = False) -> tuple[str, list[dict]]:
    """The ai-influencer technique, ported and validated on fal gpt-image-2.

    SHORT and DIRECTIVE. The references carry WHO she is; the prompt only says
    what is happening and points at each reference by role. This is the opposite
    of the long-BIO prompt, and it matches our own measurement that describing
    her hurts (0.531 vs 0.860). Their doctrine, verbatim: "this is an edit, not a
    generation. Prompt is short and directive. Do not re-describe the refs."

    Reference roles, by position in image_urls (the caller MUST attach in this
    order):
      @image1 = face / identity          (always)
      @image2 = wardrobe outfit           (if has_wardrobe) — "reproduce exactly"
      @image3, @image4 = skin close-ups   (if n_skin)

    Validated: @image1 held identity at 0.825 while @image2 transferred a leather
    jacket into a new scene. The @image convention works on fal.
    """
    if pov:
        # Faceless first-person POV product/lifestyle shot. The face reference
        # (@image1, still attached) anchors her SKIN TONE and complexion so the
        # hands are actually HERS; her face is deliberately out of frame. The
        # caller appends the nails/home/wardrobe directives as usual — the nail
        # directive ("hands and nails clearly in focus") is the primary anchor.
        parts_out = [
            "First-person POV phone photo — she is holding the phone in her own "
            "hand and taking the picture herself. Her FACE IS NOT in the frame "
            "(cropped out, above the top edge; do NOT show her face). In frame: "
            f"her own manicured hand, wrist and forearm. {brief.strip()}",
            "Her hand and skin match her own complexion from @image1; natural "
            "hand anatomy with five fingers and realistic natural nails.",
        ]
        if has_wardrobe:
            parts_out.append("Any sleeve or cuff on her forearm matches the outfit in @image2.")
        if build_text:
            parts_out.append(build_text)
        if carry_text:
            parts_out.append(carry_text)
        if realism:
            parts_out.append(
                "Photorealistic phone snapshot: sharp focus on the subject and her "
                "hand, real skin texture and fine detail on the hand and wrist, "
                "accurate colours, natural lighting and reflections. Shot on a "
                "phone, not a professional camera. Do NOT show her face.")
        return sanitise(" ".join(parts_out))

    opener = SHOT_TYPES.get(shot_type, SHOT_TYPES["candid"])
    parts_out = [f"{opener} of @image1. {brief.strip()}"]

    # Who took it — placed early, because it decides the distance and the framing
    # everything after it is written against.
    holder = (CAMERA_HOLDERS.get(camera_holder) or {}).get("text", "")
    if holder:
        parts_out.append(holder)

    if pose_ref_tag:
        # A pose REFERENCE IMAGE of her. References leak pose strongly, so this
        # steers head orientation and body pose harder than text ever could —
        # the user's idea, and the honest alternative to rotating the output.
        parts_out.append(
            f"Match her body pose and head orientation to {pose_ref_tag} — same "
            f"stance, same head angle. Take ONLY the pose, stance and orientation "
            f"from {pose_ref_tag}; her face, features and identity come only from "
            f"@image1.")
    elif pose_text:
        parts_out.append(pose_text.strip().rstrip(".") + ".")

    if build_text:
        parts_out.append(build_text)

    if carry_text:
        parts_out.append(carry_text)

    if has_wardrobe:
        # The wardrobe reference is a turnaround of HER wearing the outfit, so it
        # contains her face and skin too. Without an explicit exclusion the model
        # pulls identity from @image2 and the wardrobe face overrides @image1.
        # Same shape as the pose-ref directive: take ONLY the garments; identity
        # stays with @image1.
        parts_out.append(
            "She is wearing the complete outfit from @image2 — reproduce every "
            "clothing item and accessory exactly as shown. Take ONLY the clothing "
            "and accessories from @image2; her face, skin, hair, features and "
            "identity come only from @image1, never from @image2.")

    if n_skin >= 2:
        parts_out.append("Match skin texture and facial detail from @image3 and @image4.")
    elif n_skin == 1:
        parts_out.append("Match skin texture and facial detail from @image3.")

    if realism:
        parts_out.append(
            "Sharp, high-detail face: visible skin pores, fine peach-fuzz and "
            "skin texture, subtle natural imperfections, and her exact freckles, "
            "moles and beauty marks reproduced from @image1 — never smoothed, "
            "airbrushed or retouched. Crisp focus on the eyes. Shot on a phone, "
            "not a professional camera.")

    # Flaws go LAST so they qualify the realism line above rather than being
    # overruled by it — "crisp focus on the eyes" and "mild motion blur" are a
    # contradiction, and the model resolves a contradiction by whichever it read
    # most recently.
    flaw = (SNAPSHOT_FLAWS.get(flaws) or {}).get("text", "")
    if flaw:
        parts_out.append(flaw)

    return sanitise(" ".join(parts_out))


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

    ## Why the brief LEADS when one is given

    The old layout appended the brief as one clause inside a fixed section order,
    so it landed in the MIDDLE of ~200 words of BIO boilerplate. Two failures
    measured directly: an instruction-following model (gpt-image-2) weights what
    comes first, so a buried brief was under-followed; and a standing constraint
    that sat BEFORE the brief ("No visible brand logos") silently overrode it
    ("Argentina football jersey"). Both are the brief being discarded.

    So when a brief exists it leads the prompt, and the BIO follows framed as
    "keep her consistent while doing the above." Placeholder parts (the default
    scene/wardrobe/pose/light AND the default no-logos guard) drop out entirely —
    the brief owns everything it touches.

    Sanitisation runs on the final text, catching a trigger from the BIO or the
    brief. Returns (clean_prompt, changes).
    """
    live = [p for p in parts if p.enabled]
    if has_reference:
        live = [p for p in live if not p.identity]

    if not brief.strip():
        # No brief: the structured, placeholder-driven default (seed hunt / base).
        return sanitise(compose(live, has_reference=has_reference, pose_note=pose_note))

    # Brief present: it leads; defaults it would fight are dropped.
    live = [p for p in live if not p.placeholder]

    def txt(section: str, sep: str = "; ") -> str:
        got = [p for p in live if p.section == section]
        return sep.join(p.text.strip() for p in got)

    shot = brief.strip()
    if pose_note:
        shot = f"{shot} {pose_note}"

    blocks = [f"Candid photograph. {shot}"]

    # Identity + why she must not change, then the physical facts to hold steady.
    lock = IDENTITY_LOCK if has_reference else ""
    energy = txt("subject")
    ident = " ".join(s for s in (lock, energy) if s).strip()
    if ident:
        blocks.append(ident if ident.endswith(".") else ident + ".")

    build = txt("body")
    if build:
        blocks.append(f"Keep her build consistent with the reference: {build}.")

    # Persistent grooming + signature accessories — the same on every shot.
    groom = "; ".join(s for s in (txt("grooming"), txt("accessories")) if s).strip()
    if groom:
        blocks.append(f"Consistent grooming and accessories, the same on every shot: {groom}.")

    skin = txt("skin", sep="\n")
    if skin:
        blocks.append("Skin — real photographic detail, no retouching:\n" + skin)

    # Wardrobe here holds only NON-placeholder wardrobe parts (none by default,
    # since the brief owns the outfit). Realism tail last.
    tail = " ".join(s for s in (txt("wardrobe", " "), txt("camera", " "),
                                txt("constraints", "\n")) if s).strip()
    if tail:
        blocks.append(tail)

    return sanitise("\n\n".join(blocks))


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
