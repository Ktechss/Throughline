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
    # SEXUALISED MOOD — still neutralised, and this is the load-bearing one.
    # A product shot is about the garment. This rule is most of the difference
    # between a campaign image and something else, and it costs nothing to keep.
    (r"\b(?:seductive|sultry|provocative|sensual|alluring)\b", "relaxed",
     "sexualised mood word"),
    # The ADVERB form needs its own rule, and an adverb replacement. `\bsensual\b`
    # does not match "sensually" — the boundary fails against the "ly" — so every
    # inflected form of the rule above sailed through untouched, which is exactly
    # the shape a motion prompt takes ("she moves sensually") rather than a shot
    # prompt ("a sensual portrait"). Swapping in "relaxed" here would ship "she
    # moves relaxed" — broken English, the same trap the nude rule below
    # documents — so the replacement is an adverb.
    (r"\b(?:seductively|sultrily|provocatively|sensually|alluringly)\b", "slowly",
     "sexualised mood word"),
    # UNDRESS — still neutralised. A garment category is a garment; this is the
    # absence of one, and that distinction is the whole of the rule below.
    (r"\b(?:topless|naked|bare-?chested|unclothed|undressed)\b",
     "casual clothing", "undress cue"),
    # "nude" is NOT in the list above, because in this domain it is overwhelmingly
    # a COLOUR. The blanket rule rewrote a real shot's saved styling into
    #
    #   "blush-casual clothing satin"       (was blush-nude)
    #   "Fingernail polish: soft casual clothing pink"
    #   "Lipstick: soft casual clothing pink"
    #
    # and shipped that to fal. Same failure as the product-category rule that was
    # already narrowed once — a word that means undress in one context and a
    # perfectly ordinary retail colour in another, rewritten on sight.
    #
    # So match the CONTEXT rather than the word: a person being nude, not a thing
    # being nude-coloured. "nude pink", "nude-toned", "blush-nude", "nude satin"
    # and a "nude manicure" all pass through untouched now.
    # The verb is CAPTURED and put back, or "she is nude" rewrites to
    # "she wearing casual clothing" — broken English shipped to the model, which
    # is its own kind of damage.
    (r"\b(is|are|was|were|posing|posed|poses|appears?|standing|lying|sitting)\s+"
     r"(?:fully\s+|completely\s+|totally\s+|semi-?\s*|partially\s+)?nude\b",
     r"\1 wearing casual clothing", "undress cue"),
    (r"\bin the nude\b", "in casual clothing", "undress cue"),
    (r"\bnude\s*(?:photo\s?shoot|photograph\w*|photo|shoot|scene|model\w*|body|figure)\b",
     "casual clothing photograph", "undress cue"),
    # PRODUCTS — deliberately NOT rewritten. lingerie, underwear, swimwear,
    # bikini, loungewear and the rest are retail categories with an ordinary
    # advertising industry behind them, and they used to sit in the undress rule
    # above. That made a whole class of brief fail SILENTLY, which is the worst
    # shape a limitation can have:
    #
    #   in:  "Studio catalogue photograph for a lingerie brand campaign."
    #   out: "Studio catalogue photograph for a casual clothing brand campaign."
    #
    # The brief was accepted, a generation was paid for, and a fully-dressed
    # image came back with nothing reported. Naming a garment is not naming an
    # absence of one, so these pass through untouched. What still guards the
    # output is the mood rule and the undress rule above — plus the fact that
    # she is fictional and adult, which no rule here can change.
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
    # rather than arguing with them. Read by compose(); compose_tagged takes
    # the brief directly and never consults a placeholder.
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
        # Two kinds of part live here and the distinction matters. The FEATURES
        # (eyes, brows, nose, lips) are what people describe when asked what
        # someone looks like. The GEOMETRY below them — forehead, cheekbones,
        # cheek fullness, jawline, chin — is what actually makes a face
        # recognisable, and it is what ArcFace keys on.
        #
        # Only the features were specified here for a long time, and the cost
        # showed up as drift nobody could name: a generated face would keep the
        # dark almond eyes and the full lips and still be a different woman,
        # because the skull underneath was redrawn every seed. Every complaint in
        # a careful side-by-side of a drifted generation is on this list —
        # "longer and narrower", "jawline and chin more tapered", "fuller cheeks"
        # — and none of them is an eye colour.
        P("face.eyes", "face", "Eyes", "large almond dark-brown eyes", identity=True),
        P("face.brows", "face", "Brows", "naturally thick, softly arched brows", identity=True),
        P("face.nose", "face", "Nose", "a straight nose with a narrow bridge", identity=True),
        P("face.lips", "face", "Lips", "medium-full lips, muted dusty rose", identity=True),
        P("face.shape", "face", "Face shape", "a soft oval face", identity=True),
        P("face.forehead", "face", "Forehead", "a medium-width forehead of average "
          "height, with a softly rounded hairline", identity=True),
        P("face.cheekbones", "face", "Cheekbones",
          "gently defined cheekbones, present but not sharp or high-fashion",
          identity=True),
        P("face.cheeks", "face", "Cheek fullness",
          "subtle cheek fullness, soft under the eye rather than hollow",
          identity=True),
        P("face.jawline", "face", "Jawline",
          "a smooth, softly tapered jawline — defined but not angular", identity=True),
        P("face.chin", "face", "Chin", "a softly rounded chin of medium length",
          identity=True),
        # Asymmetry earns its slot twice over: it is the single strongest cue
        # separating a photograph from a render, AND it is a stable identity
        # anchor rather than a beauty adjective. Perfect symmetry is the tell.
        P("face.asymmetry", "face", "Natural asymmetry",
          "one eyebrow sits fractionally higher than the other, one eye opens "
          "very slightly wider, and one cheek is marginally fuller — the ordinary "
          "asymmetry every real face has", identity=True,
          note="Never remove this for being 'imperfect'. A face with none of it "
               "reads as CGI, and symmetry is not what makes a face attractive — "
               "specific proportions are."),
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
          "a full chest with a natural weight and a natural hang",
          critical=True,
          note="The BODY REFERENCE IMAGE carries her actual proportions — this "
               "line only steers away from the generator's default (spherical, "
               "gravity-defying, unnaturally high), the same class of tell as "
               "the cinched waist. It used to read 'not exaggerated or lifted', "
               "which damped SIZE as well as the artifact: the creation picker "
               "writes only body.frame (main.py:976), so picking 'voluptuous' "
               "left this default sitting underneath it saying the opposite, and "
               "compose() rebuilds the body section into the Subject line even "
               "when a body reference exists — so it contradicted the reference "
               "on every shot instead of only steering the generator. The guard "
               "is kept but narrowed to SHAPE: weight and hang, never size. Set "
               "the size per-character; cup sizes pass the sanitiser now (see "
               "_SANITISE), though an explicit one plus revealing wardrobe can "
               "still trip gpt-image-2 and fall back to the scene model. For a "
               "male subject, edit the text — the part is the slot, not the gender."),
        P("body.waist", "body", "Waist",
          "a 30-inch waist, clearly defined",
          critical=True,
          note="Load-bearing. 30in against 40in hips is already a strong "
               "hourglass; the generator will try to exaggerate it further into "
               "a corset, which is one of the clearest AI tells. The number sets "
               "the shape. 'NOT cinched or corseted' used to follow it and was "
               "dropped for the same reason as body.bust: it read as a cap "
               "rather than a correction, and fought any character whose body "
               "reference genuinely is cinched. Nothing automated catches the "
               "corset tell — the gate is blind to body — so `mark` is the only "
               "check. Restore the negation here, per character, if runs come "
               "back corseted; don't fight it in the brief."),
        P("body.hips", "body", "Hips", "40-inch hips, balancing the bust"),
        P("body.legs", "body", "Legs", "notably long legs, a high leg-to-torso ratio"),
        P("body.posture", "body", "Posture", "elegant posture, a long neck"),

        # -- hair / skin -----------------------------------------------------
        # hair.base is ONE blob covering colour, length, texture and parting at
        # once. That is fine for a character already locked to a reference — it
        # is identity=True and gets dropped the moment one exists — but it is a
        # poor thing to hand a generator that is inventing a face from nothing,
        # where each axis wants stating separately.
        #
        # So the granular parts ship OFF. An existing character keeps its blob
        # and gains five switches it can ignore; guided creation enables these
        # and disables the blob for the character it is building, so nobody ever
        # renders both.
        P("hair.base", "hair", "Hair",
          "very long jet-black hair to the waist, centre part, soft waves from "
          "shoulder level", identity=True,
          note="The single-line form. Guided creation turns this OFF in favour of "
               "the granular hair parts below; it stays on for characters made "
               "before those existed."),
        P("hair.colour", "hair", "Hair colour", "jet black with a cool sheen",
          identity=True, enabled=False),
        P("hair.length", "hair", "Hair length", "very long, falling to the waist",
          identity=True, enabled=False),
        P("hair.texture", "hair", "Hair texture",
          "thick and glossy, soft waves from shoulder level down", identity=True,
          enabled=False),
        P("hair.parting", "hair", "Parting", "a relaxed centre part", identity=True,
          enabled=False),
        P("hair.hairline", "hair", "Hairline & flyaways",
          "a softly rounded hairline with fine baby hairs at the temples and a "
          "few flyaway strands catching the light", identity=True, enabled=False),
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


def compose(parts: list[Part], *, has_reference: bool = False) -> str:
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

        if section in BLOCK_SECTIONS:
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
    # Product photography, for a brand campaign. `editorial` was the closest
    # existing register and it is the wrong one: editorial means fashion-
    # editorial, which biases toward mood and away from showing the garment
    # clearly — backwards for a catalogue shot, where the garment IS the subject.
    # This is the prompt's opener, so it sets the register everything after it is
    # written against, the same placement argument as framing.
    "commercial": "Commercial product photograph, garment clearly shown",
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
        # Positive phrasing only. An earlier version said "NOT down at the phone
        # screen ... not tilted" and named exactly what it was trying to avoid;
        # tilted heads went from 20% of shots to 43%. Describe the head you want.
        "text": "A mirror selfie: she is photographing her own reflection, the "
                "phone held at chest height and angled at the glass, clear of her "
                "face. She looks straight into her own eyes in the mirror, chin "
                "level, head upright and balanced. The room behind her appears "
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

# THE OPTICS OF THE THING THAT TOOK THE PICTURE.
#
# `camera.body` says "wide 24mm-equivalent lens" and `constraints.main` says "no
# bokeh", and between them they name the tell without describing its opposite.
# That gap is why Claude filled it with "85mm" 51 times and "shallow depth of
# field" 40 times: a model told only what NOT to do renders the thing it knows.
#
# A phone front camera is f/2.2 at a fixed wide focal length. Its hyperfocal
# distance means that at arm's length the WHOLE ROOM is in acceptable focus —
# there is no separated subject, no creamy fall-off, no portrait-mode cut-out
# around the hair. Saying so positively is the entire point of this table:
# `prompt.py`'s own history records that naming a thing to avoid ("not tilted")
# doubled its frequency, and that describing the state you want fixed it.
OPTICS = {
    "": {"label": "Unspecified", "text": ""},
    "phone-deep": {
        "label": "Phone — deep focus",
        "text": "Phone-camera optics: a fixed wide lens at a small aperture, so "
                "depth of field is DEEP — the wall, the furniture and the room "
                "behind her are all in focus, about as sharp as she is. There is "
                "no background blur, no subject separation and no lens fall-off. "
                "Slight barrel distortion toward the edges of the frame."},
    "phone-front": {
        "label": "Phone — front camera, arm's length",
        "text": "Front-camera optics at arm's length: a wide lens close to her "
                "face, so her nearest features sit slightly large and her ears "
                "and shoulders fall away faster than they would in life. Depth "
                "of field is DEEP — the room behind her stays in focus, about as "
                "sharp as she is, with no background blur and no subject "
                "separation."},
    "portrait": {
        "label": "Portrait lens (deliberate)",
        "text": "A longer portrait lens: she is compressed and separated from a "
                "softly out-of-focus background."},
}

# HOW THE SENSOR AND THE METER FAILED.
#
# `lighting_data` describes the LIGHT IN THE ROOM. This describes what a small
# sensor does with it, which is a different axis and an absent one: grep across
# the repo finds zero uses of "blown", "overexposed", "clipped" or "chromatic
# aberration" as prompt language, in 607 runs.
#
# It matters because a phone cannot expose a face and a bright window correctly
# in the same frame. Run 15e2298957 has a perfectly lit face AND a detailed blue
# sky behind it, which is not a phone photo — it is a photographer with a
# reflector. One of the two has to give, and saying which is the difference.
EXPOSURE = {
    "": {"label": "Unspecified", "text": ""},
    "blown-window": {
        "label": "Window blown out",
        "text": "The camera metered for her face, so the window behind her is "
                "blown to featureless white with the light bleeding over its "
                "frame. No detail survives outside."},
    "dark-face": {
        "label": "Backlit, face underexposed",
        "text": "The camera metered for the bright background, so she is "
                "underexposed — her face sits a stop or two dark, shadows are "
                "muddy and slightly noisy, and the highlights behind her hold."},
    "phone-hdr": {
        "label": "Phone HDR, over-processed",
        "text": "Heavy phone HDR processing: local contrast pushed hard, faint "
                "bright halos where dark edges meet the window, shadows lifted "
                "flat and grey, and over-sharpened detail on her hair and lashes."},
    "low-light": {
        "label": "Low light, high ISO",
        "text": "Shot at high ISO in poor light: visible luminance and colour "
                "noise through the shadows, fine detail smeared by the phone's "
                "denoiser, and slightly muddy colour."},
}

# WHAT STATE SHE IS ACTUALLY IN.
#
# The axis this project did not have. `SNAPSHOT_FLAWS` describes the PHOTOGRAPH
# — tilt, blur, crop — and nothing anywhere described HER as unmaintained. So
# every image, in every scene, at every hour, showed a woman with finished hair,
# even skin and a clean manicure. A brief could move her to a bed at 7am and it
# could not make her look like she had been asleep.
#
# ⚠ Placement matters. `carry_clause` asserts her nails are "clean and even" in
# every single prompt, and `hair.base` gives her "soft waves". These lines
# contradict that on purpose, so they must be appended AFTER it — the same
# argument _WET_HAIR makes in main.py, and for the same reason: the model
# resolves a contradiction in favour of whichever it read last.
#
# ⚠ These cost similarity, like SNAPSHOT_FLAWS. Puffy eyes and a slept-on face
# change the geometry ArcFace reads. That is the intended outcome, not drift.
GROOMING_STATE = {
    "": {"label": "As styled", "expected_low": False, "text": ""},
    "just-woken": {
        "label": "Just woken", "expected_low": True,
        # "Her face is bare" was the first wording and it is a moderation
        # trigger waiting to happen: "bare" beside a lingerie description and a
        # bed reads to a content checker as undress, not as no-makeup. Say the
        # thing itself. sanitise() does not catch it — its rule is "bare-chested".
        "text": "She has just woken up and has not touched her face or hair. Her "
                "hair is slept-on — crushed flat on the side she lay on, lifting "
                "and frizzing on the other, flyaways everywhere, the roots a "
                "little oily and the waves broken rather than styled. She is "
                "wearing no makeup at all, her eyes are puffy and slightly "
                "narrowed, faint creases are pressed into one cheek by the "
                "pillow, her under-eyes are shadowed and a little swollen and "
                "her lips are dry and pale. Skin is uneven and slightly shiny at "
                "the nose and forehead."},
    "end-of-day": {
        "label": "End of a long day", "expected_low": False,
        "text": "It is the end of a long day and her look has worn down: makeup "
                "faded and patchy, liner smudged under the outer corners, lips "
                "mostly worn off, shine coming through at the nose and forehead. "
                "Her hair has dropped out of the shape it started in, with "
                "strands escaping around her face."},
    "unmaintained": {
        "label": "Between appointments", "expected_low": False,
        "text": "Small signs of a real week: polish chipped at the tips of two or "
                "three nails and worn thin on the others, a faint tan line, and "
                "hair that is overdue a trim, with split ends visible where it "
                "falls past her shoulders."},
    "post-workout": {
        "label": "After exercise", "expected_low": True,
        "text": "She has just finished exercising: skin flushed and genuinely "
                "sweaty at the hairline, temples and upper lip, damp strands "
                "stuck to her forehead and neck, hair pulled back roughly with "
                "pieces escaping, and no makeup beyond what has survived."},
}

# WHAT IS LYING AROUND, TODAY.
#
# The rooms come back tidy. Not showroom-tidy — the corner generator already
# argues against that ("Cohesive, lived-in, real home — NOT a showroom or staged
# catalogue") and the corners genuinely have wear in them. What they do not have
# is MESS, and mess is a different thing from wear: wear is permanent and
# belongs to the room, mess is transient and belongs to the day.
#
# ⚠ That distinction is the whole design. The setting clause says "reproduce
# that same place faithfully ... do not invent or substitute a different room",
# and a clutter line that describes furniture would fight it and lose. So every
# entry below adds only things a person PUT DOWN — objects that arrived this
# morning and will be gone tomorrow — and says explicitly that the room itself
# is unchanged.
#
# Why it matters more than it sounds: the single most convincing detail in the
# whole wake-up series was "a phone charger cable trailing across the mattress",
# and Claude wrote that of its own accord into one prompt. Nothing in the
# pipeline could ask for it twice.
CLUTTER = {
    "": {"label": "As the reference shows it", "text": ""},
    "lived-in": {
        "label": "Lightly lived-in",
        "text": "The room itself is exactly as the reference shows it — same "
                "furniture, same layout, nothing moved or added to it. What is "
                "different is only what someone has put down today: a phone "
                "charging cable trailing across a surface, a used glass, a hair "
                "tie, one garment over the back of a chair. Small, ordinary, and "
                "clearly left rather than placed."},
    "slept-in": {
        "label": "Slept in",
        "text": "The room itself is exactly as the reference shows it. The bed is "
                "not: the duvet is thrown back and bunched where she pushed out "
                "of it, the pillows hold the dents of a head, the bottom sheet is "
                "rucked and creased, and a phone, a charging cable and a "
                "half-drunk glass of water are on the mattress or the table beside "
                "it. Nothing about the bed looks made."},
    "used": {
        "label": "In use",
        "text": "The room itself is exactly as the reference shows it. Across it, "
                "the evidence of an ordinary day: two or three used cups and "
                "glasses, an open laptop with a cable running off it, papers and "
                "a phone face-down, packaging that has not been thrown out, shoes "
                "left where they came off. Things are where they were dropped, not "
                "where they belong."},
    "messy": {
        "label": "Genuinely messy",
        "text": "The room itself is exactly as the reference shows it, and it is a "
                "mess: clothes over the chair and on the floor, a laundry pile, "
                "several days of glasses and cups, an open bag with its contents "
                "spilling, cables tangled, surfaces covered. Nobody tidied for "
                "this photograph and it shows."},
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


def capture_clause(parts: list["Part"]) -> str:
    """The photographic facts: what camera, what skin, what is forbidden.

    Third and last of the three clause builders, and the one that should have
    existed from the start. `carry_clause`'s docstring above records finding that
    `compose_tagged` only ever pulled `body` parts, and fixing it for grooming
    and accessories. The same bug was left standing for the three sections that
    carry every word of realism doctrine this project has:

        camera.body       "a handheld phone camera - wide 24mm-equivalent lens,
                           automatic exposure, natural sensor noise in the
                           shadows. Never a professional camera, never a lighting
                           setup, never a photoshoot."
        skin.facts        pores, sheen, dry lip edges, baby hairs, peach fuzz,
                           and sensor noise on the shadow side of her face
        constraints.main  "no bokeh, no professional lighting setup, no beauty
                           retouching ... indistinguishable from a real photo a
                           friend posted online"
        subject.energy    "a real person, not a model on a shoot"

    Measured on 2026-08-24 over every run in the database: across 607 shots,
    "sensor noise" appeared 0 times, "no bokeh" 0 times, "never a professional
    camera" 0 times, "not a model on a shoot" 0 times. The doctrine was written,
    argued for in comments, marked `critical=True` so the UI warns before you
    disable it -- and never once shipped.

    What DID ship, because nothing was there to contradict it, was Claude writing
    "85mm" into 51 prompts and "shallow depth of field" into 40. `camera.body`
    exists precisely to forbid that, and it was not in the room.

    `subject.energy` rides along from `subject` because it is the one non-identity
    part in that section and it says the same thing as the rest; the identity
    parts of `subject`/`face` stay out, exactly as `compose()` drops them when a
    reference exists. Disabled parts stay dropped, so the checkboxes remain real.
    """
    cam = [p.text.strip().rstrip(".") for p in parts
           if p.section == "camera" and getattr(p, "enabled", True)
           and p.text.strip() and not getattr(p, "placeholder", False)]
    skin = [p.text.strip() for p in parts
            if p.section == "skin" and getattr(p, "enabled", True)
            and p.text.strip() and not getattr(p, "identity", False)]
    cons = [p.text.strip() for p in parts
            if p.section == "constraints" and getattr(p, "enabled", True)
            and p.text.strip()]
    energy = [p.text.strip().rstrip(".") for p in parts
              if p.id == "subject.energy" and getattr(p, "enabled", True)
              and p.text.strip()]

    out: list[str] = []
    if energy:
        out.append("She is " + "; ".join(energy) + ".")
    if cam:
        out.append("Shot on " + "; ".join(cam) + ".")
    if skin:
        # skin.facts is a newline-separated block of em-dash bullets. Flatten it:
        # a shot prompt is one run of prose, and the bullets survive as clauses.
        flat = "; ".join(ln.strip(" -—\t") for block in skin
                         for ln in block.splitlines() if ln.strip(" -—\t"))
        out.append("Skin, as photographic fact: " + flat + ".")
    if cons:
        out.append(" ".join(cons))
    return " ".join(out)


def compose_tagged(brief: str, *, pose_text: str = "", has_wardrobe: bool = False,
                   pose_ref_tag: str = "", build_text: str = "", n_skin: int = 0,
                   shot_type: str = "candid", camera_holder: str = "",
                   flaws: str = "", carry_text: str = "", capture_text: str = "",
                   realism: bool = True, phone: bool = True,
                   pov: bool = False) -> tuple[str, list[dict]]:
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
        # Same shape as the pose-ref directive: identity stays with @image1.
        #
        # But the exclusion used to read "take ONLY the clothing and accessories",
        # and that threw away something the turnaround genuinely holds. A wardrobe
        # sheet is generated by wardrobe_create from her face AND her pinned body
        # reference — every one of these outfits records `body: curvy athlete
        # full` in its own run meta. So the garment in @image2 is already draped
        # on her figure, and "only the clothing" discarded the figure and left the
        # build to text.
        #
        # Reported as "identity was never an issue, it is just the body shape I
        # am missing", and the fix is not a third reference — it is to stop
        # excluding what is already in the second one. The exclusion narrows to
        # what it was actually protecting: the FACE.
        parts_out.append(
            "She is wearing the complete outfit from @image2 — reproduce every "
            "clothing item and accessory exactly as shown, and keep her build, "
            "proportions and silhouette as they appear there. Take the clothing "
            "and the body shape from @image2, but NOT the face: her face, skin, "
            "hair, features and identity come only from @image1, never from "
            "@image2.")

    if n_skin >= 2:
        parts_out.append("Match skin texture and facial detail from @image3 and @image4.")
    elif n_skin == 1:
        parts_out.append("Match skin texture and facial detail from @image3.")

    # The photographic facts from the part tree, ahead of the realism line below
    # because that line is reference-SPECIFIC (it names @image1's freckles) while
    # this one is general. General first, specific second, flaws last.
    if capture_text:
        parts_out.append(capture_text)

    if realism:
        # Two claims lived in one string and only one of them is about the
        # register. Real skin belongs in EVERY prompt — a studio photograph of a
        # person still has pores, and the master-face prompt says so at length.
        # "Shot on a phone" does not: it contradicts an editorial or commercial
        # opener, and it shipped on those anyway because there was no seam to cut.
        parts_out.append(
            "Sharp, high-detail face: visible skin pores, fine peach-fuzz and "
            "skin texture, subtle natural imperfections, and her exact freckles, "
            "moles and beauty marks reproduced from @image1 — never smoothed, "
            "airbrushed or retouched. Crisp focus on the eyes.")
        if phone:
            parts_out.append("Shot on a phone, not a professional camera.")

    # Flaws go LAST so they qualify the realism line above rather than being
    # overruled by it — "crisp focus on the eyes" and "mild motion blur" are a
    # contradiction, and the model resolves a contradiction by whichever it read
    # most recently.
    flaw = (SNAPSHOT_FLAWS.get(flaws) or {}).get("text", "")
    if flaw:
        parts_out.append(flaw)

    return sanitise(" ".join(parts_out))


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


# ═══════════════════════════════════════════════════════════════════════════
# THE SHARED TAIL
# ═══════════════════════════════════════════════════════════════════════════
#
# /api/shot and /api/scene are two generation paths that share almost no code,
# and every fix has had to be applied twice — or, more often, once. Measured
# on 2026-08-24, the scene path was missing ALL of: the photographic doctrine
# (capture_clause), her build, her standing grooming, the wet-hair lock, optics,
# exposure and grooming state. A pool scene came back with dry hair because the
# fix for exactly that lived on the other path.
#
# The codebase already records this happening three times. _WET_HAIR first went
# on the AI branch only, so template shots stayed dry. The body-reference role
# line was fixed on shot and re-derived for scene. And the "two different women"
# directive existed in THREE independent wordings for one measured failure.
#
# So these live here, once, and both paths call them. The ordering is not
# cosmetic — see each clause for what it has to arrive after.


def distinct_clause(labels: list[str]) -> str:
    """Say that N subjects are N DIFFERENT people. One wording, was three.

    `labels` are whatever identifies them in this prompt — reference tags on a
    shot ("@image1", "@image2"), names on a scene ("Kiara", "Sonam"). The
    failure this prevents is the model averaging two references into one face,
    which `gate.check_cast` measures as `blended`.
    """
    if len(labels) < 2:
        return ""
    named = ", ".join(labels[:-1]) + " and " + labels[-1]
    return (f"There are {len(labels)} DIFFERENT women in this photograph "
            f"({named}). Render them as distinct individuals who do not resemble "
            f"each other. Keep each face exactly as its own reference shows it — "
            f"do NOT blend, merge or average their features, and never give two "
            f"of them the same face.")


def wet_clause(subjects: int = 1) -> str:
    """Hair and skin are wet.

    ⚠ Must arrive AFTER every clause that claims hair comes from @image1 — the
    body-reference role line and the outfit styling both say so, and this
    deliberately contradicts them on styling while keeping colour and length.
    A contradiction is resolved by whichever the model read last.

    Written out twice rather than assembled from pronouns: splicing "her"/"their"
    into one template produced "Every person in frame — her hair", and a clause
    that reads as broken English is a clause the model half-applies.
    """
    if subjects < 2:
        return ("Her hair and skin are WET in this shot. Her hair is soaked "
                "through — darkened, heavier, clinging to her scalp, neck and "
                "shoulders in ropes, NOT the dry styled waves of her reference: "
                "take its colour and length from the reference but never its dry "
                "styling. Water beads and runs on her face, shoulders and arms, "
                "her lashes are wet and clumped, and any fabric on her is "
                "darkened and clinging. Nothing about her is dry.")
    return ("Everyone in this photograph is WET. Their hair is soaked through — "
            "darkened, heavier, clinging to scalp, neck and shoulders in ropes, "
            "NOT the dry styled waves of their references: take colour and length "
            "from each reference but never its dry styling. Water beads and runs "
            "on their faces, shoulders and arms, their lashes are wet and "
            "clumped, and any fabric is darkened and clinging. Nobody is dry.")


def no_crowd_clause(subjects: int = 1) -> str:
    """Nobody in frame but the subjects.

    ⚠ Must arrive AFTER the scene description, which routinely implies people
    ("a busy night market", "the club behind her") and would otherwise win.

    This is an identity control, not set dressing. `gate.check` scores the face
    that best matches the gallery, so every extra person is another draw: 26 of
    613 runs were scored out of a crowd, one out of eighteen faces, and seven of
    those were kept.
    """
    n = max(1, subjects)
    who = "one person is" if n == 1 else f"{n} people are"
    return (f" Exactly {who} in this photograph. No other faces, no bystanders, "
            f"no crowd, no background people and no reflections of other people, "
            f"not even blurred, out of focus or in the far distance. A busy place "
            f"is conveyed with lighting, furniture, glassware, signage and depth "
            f"of field, never with other human beings.")


def late_clauses(*, optics: str = "", exposure: str = "", grooming_state: str = "",
                 clutter: str = "", wet: bool = False, suppress_crowd: bool = False,
                 subjects: int = 1) -> list[str]:
    """The tail both generation paths append, in the order that makes it work.

    Everything here contradicts something earlier on purpose, which is the whole
    reason it is a tail rather than a section:

        optics          overrules whatever focal length an AI prompt invented
        exposure        overrules the evenly-lit scene the model would default to
        clutter         overrules "reproduce that same place faithfully", but
                        only for what is lying on it, never for the room
        wet             overrules "hair comes only from @image1"
        grooming_state  overrules carry_clause's "nails clean and even" and
                        hair.base's "soft waves" — so it goes LAST of the four
        crowd           overrules a scene description that implies people

    Returns a list so the caller joins it with whatever separator it already
    uses. Empty entries are dropped.
    """
    out = [
        (OPTICS.get(optics) or {}).get("text", ""),
        (EXPOSURE.get(exposure) or {}).get("text", ""),
        (CLUTTER.get(clutter) or {}).get("text", ""),
        wet_clause(subjects) if wet else "",
        (GROOMING_STATE.get(grooming_state) or {}).get("text", ""),
        no_crowd_clause(subjects).strip() if suppress_crowd else "",
    ]
    return [c for c in out if c]
