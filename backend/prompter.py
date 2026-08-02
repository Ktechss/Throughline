"""Claude as a scene prompter: a terse brief -> a full fal-ready prompt.

The fixed "Candid iPhone photo of @image1. {brief}" template is crude — it can't
turn "she's at a Mumbai cafe in the evening" into a photograph with light, mood
and framing. This asks Claude to do that expansion.

But it expands the SCENE, never HER. The project's hard-won rule holds: describing
her face/body is measured to collapse identity (0.86 -> 0.53), because words
specify a type, not a person. So Claude is told, forcefully, to write everything
EXCEPT her — she is @image1 and the reference carries her. The output is then run
through the same moderation sanitiser as any other prompt, and shown to the user
to edit before it is ever sent. Nothing here bypasses review.
"""

from __future__ import annotations

import json
import os

from . import config  # noqa: F401 — runs load_dotenv(.env)

# The identity rule is non-negotiable (measured); the photographic STYLE follows
# the brief. The project DEFAULTS to candid-phone realism, but an explicit brief
# ("studio", "high-res camera", "editorial lighting") must win — the prompter's
# job is to realise the user's intent, not overrule it.
_SYSTEM = (
    "You are a photo-direction assistant for a photorealistic character image "
    "pipeline. You turn a short scene brief into ONE image-generation prompt for "
    "an image model that EDITS reference photos.\n\n"
    "ABSOLUTE RULES — breaking any of these ruins the image:\n"
    "1. NEVER describe the woman herself: not her face, eyes, nose, lips, hair, "
    "skin, age, ethnicity, body, or build. She is provided as reference image "
    "@image1 and MUST be referred to only as '@image1' or 'she'. Describing her "
    "makes the model draw a different person. This is the single most important "
    "rule. Her face, skin, hair and identity come ONLY from @image1 — other "
    "references (wardrobe @image2, a pose image @image3) may also show her, but "
    "you must take only the CLOTHING from a wardrobe ref and only the POSE from a "
    "pose ref, never identity. Never tell the model to take her face, skin or "
    "looks from any image other than @image1.\n"
    "2. FOLLOW the photographic style the brief asks for. If the brief calls for "
    "a studio shoot, a professional or high-resolution camera, editorial or flash "
    "lighting, a specific lens or f-stop, etc., write exactly that — a real, "
    "high-end professional photograph. If it asks for a candid phone snapshot, "
    "write that. If the brief does NOT specify a camera or setting, default to a "
    "natural candid photo in real found light (handheld, not a studio). Never "
    "force a phone when a studio is asked for, or a studio when it isn't.\n"
    "3. Keep it photorealistic with a SHARP, HIGH-DETAIL face: visible skin "
    "pores, fine skin texture and peach-fuzz, subtle natural imperfections, and "
    "her exact freckles, moles and beauty marks reproduced from @image1 — never "
    "plastic 'AI' smoothing, airbrushing or heavy retouching, and this applies to "
    "studio shots too. Crisp focus on the eyes. Do NOT use AI-slop words: "
    "stunning, ethereal, hyper-realistic, 8k, ultra-detailed, perfect, glowing, "
    "flawless, masterpiece, breathtaking, gorgeous.\n"
    "4. Keep it SHORT and directive: roughly 60-130 words. Concrete photographic "
    "facts beat adjectives.\n"
    "5. RENDER THE PLACE AS OBJECTS, NOT AS ITS NAME. An image model cannot draw "
    "a label. 'A cinema washroom' produces a generic home bathroom; what makes it "
    "a cinema washroom is a long row of identical sinks, a continuous vanity "
    "counter, an unbroken mirror wall, metal stall partitions, large-format wall "
    "tile, commercial fixtures. Name 3-5 things VISIBLE IN THE FRAME that could "
    "only exist in that specific place, and prefer them over adjectives. Anything "
    "that is narrative rather than visible — what film she is seeing, that it is "
    "the interval, what she did earlier — cannot be drawn: either drop it or turn "
    "it into a prop that IS in shot (a ticket stub and a popcorn cup on the "
    "counter). If a named place would otherwise render as somewhere generic, that "
    "is the failure this rule exists to prevent.\n"
    "6. FRAME HER CLOSE ENOUGH TO BE RECOGNISABLE. Identity is measured off the "
    "face, and below roughly 400px of face the score falls off with framing alone "
    "(measured: 0.55 at 250-400px vs 0.61 at 400-600px; bigger than that buys "
    "nothing). Unless the brief explicitly asks for a wide, full-body or "
    "environmental shot, choose the tighter framing that still tells the story — "
    "waist-up or closer — and light her face from the front or side rather than "
    "behind. If the brief DOES ask for a wide shot, write it as asked; just don't "
    "drift wide by default.\n"
    "6a. HER HEAD. Write these as plain positive description — never as a negation.\n"
    "   (i) Where she is looking: in a selfie, at the lens; in a mirror shot, at "
    "her own reflection. Prefer that over writing her looking down at a phone, a "
    "screen or her hands, unless the brief asks for it.\n"
    "   (ii) Her head sits level and upright, balanced on her neck.\n"
    "   (iii) Face toward the camera, with a natural expression — a smile rather "
    "than a scream or a wide-open mouth.\n"
    "   Say what you DO want and stop there. Naming a thing you don't want ('not "
    "tilted', 'no tilt') tends to produce it: after an earlier version of this "
    "rule told you to write 'not tilted', the share of tilted heads went from 20% "
    "to 43%. Describe the head you want and never mention tilting at all.\n"
    "7. Do NOT sexualise: no revealing/tight/skimpy intensifiers, no anatomical "
    "focus. Describe the scene and action neutrally.\n\n"
    "STRUCTURE the prompt as: lead with @image1 as the subject and what she is "
    "doing (place, time, mood, activity), then the framing/pose and the "
    "camera/lighting the brief implies, then keep the reference directives you "
    "are told to include verbatim, then a short realism tail matching the chosen "
    "style (for a phone shot: 'shot on a phone, no retouching'; for a studio/pro "
    "shot: 'high-resolution professional capture, real skin texture, no plastic "
    "retouching').\n\n"
    "Output ONLY the final prompt text — no preamble, no headings, no quotes, no "
    "explanation."
)


class PrompterError(RuntimeError):
    """Anything that stops us returning a rewritten prompt."""


def rewrite(brief: str, *, shot_type: str = "candid", has_wardrobe: bool = False,
            pose_ref_tag: str = "", pose_text: str = "") -> str:
    """Expand a brief into a full fal prompt via Claude. Raises PrompterError."""
    if not brief.strip():
        raise PrompterError("write a scene brief first — the prompter needs "
                            "something to expand")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise PrompterError("ANTHROPIC_API_KEY is not set in .env")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise PrompterError("the 'anthropic' package is not installed") from exc

    # The reference directives Claude must fold in verbatim — these are the
    # measured, load-bearing lines, not things to paraphrase. The photographic
    # style (studio / candid / etc.) is chosen from the brief, per rule 2.
    directives = ["Make @image1 the subject of the opening line, and choose the "
                  "shot type (studio, editorial, candid phone, street, …) to "
                  "match the brief."]
    if pose_ref_tag:
        # A pose reference image is attached — defer to it, and make clear it is
        # POSE-ONLY so it can't drift her face/identity (that stays with @image1).
        directives.append(
            f"Include, close to verbatim: 'Match her body pose and head "
            f"orientation to {pose_ref_tag} — same stance, same head angle. Take "
            f"only the pose and orientation from {pose_ref_tag}; her face and "
            f"identity come only from @image1.'")
    elif pose_text:
        directives.append(f"Work this pose into the scene naturally: {pose_text}")
    else:
        # No pose reference — YOU pick the pose. Choose a specific, natural pose
        # and head orientation that fits the scene and describe it concretely.
        directives.append(
            "No pose reference is attached, so choose a specific, natural body "
            "pose and head orientation that suits this exact scene and describe "
            "it concretely — stance, weight, what her hands are doing, where she "
            "is looking. Keep her head upright and level (not tilted) unless the "
            "scene clearly calls for a tilt.")
    if has_wardrobe:
        # @image2 is a turnaround of HER wearing the outfit, so it carries her
        # face/skin too. Make the exclusion explicit or the model pulls identity
        # from the wardrobe image and it overrides @image1 — same guard as pose.
        directives.append(
            "Include, close to verbatim: 'She is wearing the complete outfit "
            "from @image2 — reproduce every clothing item and accessory exactly "
            "as shown. Take ONLY the clothing and accessories from @image2; her "
            "face, skin, hair, features and identity come only from @image1, "
            "never from @image2.'")

    user = (
        f"Scene brief: {brief.strip()}\n\n"
        "Requirements for this prompt:\n- " + "\n- ".join(directives) +
        "\n\nWrite the single prompt now.")

    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=600,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIStatusError as exc:
        raise PrompterError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise PrompterError("could not reach the Claude API") from exc

    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not text:
        raise PrompterError("Claude returned an empty prompt")
    return text


# --------------------------------------------------------------------------
# Character bio writer (phase 4): turn a name + short description into the
# concrete, photographable identity fields the pipeline generates HER from.
# Unlike rewrite() — which must NOT describe her — this is the ONE place we DO
# write her description, because a brand-new character has no reference yet, and
# the seed face has to come from words. Once she is calibrated, the reference
# takes over and these fields stop mattering (compose() drops them).
# --------------------------------------------------------------------------
_BIO_SYSTEM = (
    "You design fictional characters for a photorealistic image pipeline. Given a "
    "name and a short description of a woman, you write the concrete VISUAL "
    "identity fields she will be generated from.\n\n"
    "RULES:\n"
    "1. Fill EVERY requested field. Each value is a short, specific noun phrase in "
    "the style of the given example — a photographable fact ('large almond "
    "dark-brown eyes'), never a vague adjective ('pretty eyes') or a sentence.\n"
    "2. Make her ONE coherent, distinctive person who matches the description, "
    "drawing on the REAL, WIDE DIVERSITY of human faces. Vary the actual "
    "structure from character to character — eye shape and spacing, brow "
    "character, nose bridge and tip, lip proportion, face shape and jawline, "
    "cheekbones, hairline, skin texture and undertone — so no two characters "
    "look alike. Prefer real, natural, lived-in features over a generic "
    "'attractive' template. Where the description is silent, invent specific, "
    "believable features that genuinely fit her.\n"
    "3. Distinguishing marks (moles, beauty spots, freckles, scars) are OFF BY "
    "DEFAULT. For 'face.marks' write exactly 'clear even skin, no prominent "
    "marks' UNLESS the description EXPLICITLY names a mark — and then include "
    "only and exactly what it names. NEVER invent a mole, beauty spot or freckle "
    "on your own; identity comes from bone structure and proportion, not added "
    "marks.\n"
    "4. Body fields: real, natural adult proportions. Keep them TASTEFUL and "
    "NON-EXPLICIT — never bra/cup sizes, measurements of intimate areas, or "
    "sexualised wording; an image model's moderation refuses those and the whole "
    "generation fails. Describe shape and balance, not numbers.\n"
    "5. She is ENTIRELY fictional. Never reference or resemble a real person or "
    "celebrity, and never use a real person's name in a value.\n"
    "6. Output ONLY a JSON object mapping each field id to its value — no prose, "
    "no markdown fences."
)


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    return t.strip()


def write_bio(name: str, description: str, fields: list[dict]) -> dict:
    """Claude writes a value for each identity field. `fields` is a list of
    {id, label, hint}. Returns {id: value} for known ids. Raises PrompterError."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise PrompterError("ANTHROPIC_API_KEY is not set in .env")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise PrompterError("the 'anthropic' package is not installed") from exc

    field_lines = "\n".join(f'- {f["id"]} ({f["label"]}) — example style: "{f["hint"]}"'
                            for f in fields)
    desc = description.strip() or "(no description given — invent a coherent, natural, distinctive woman)"
    user = (f"Character name: {name}\nDescription: {desc}\n\n"
            f"Write a value for each field (id, label, example style):\n{field_lines}\n\n"
            "Return ONLY the JSON object {id: value, ...}.")

    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model="claude-opus-4-8", max_tokens=1500,
            system=_BIO_SYSTEM, messages=[{"role": "user", "content": user}])
    except anthropic.APIStatusError as exc:
        raise PrompterError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise PrompterError("could not reach the Claude API") from exc

    text = _strip_fence("".join(b.text for b in msg.content if b.type == "text"))
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise PrompterError("Claude returned malformed bio JSON") from exc
    allowed = {f["id"] for f in fields}
    return {k: str(v).strip() for k, v in data.items()
            if k in allowed and str(v).strip()}


# --------------------------------------------------------------------------
# Outfit ENRICHER (wardrobe enrichment). The primary use is: the user uploads an
# outfit photo, describe_outfit() reads it into a base description, and this then
# ENRICHES that base — same garments, far richer and more precise detail — with
# the structured picks (occasion/style/fabric/…) as optional adaptations. With no
# base it also writes a fresh outfit from the picks/idea. Output is dropped
# verbatim into the wardrobe turnaround, so it must describe clothes and nothing else.
# --------------------------------------------------------------------------
_OUTFIT_SYSTEM = (
    "You are a fashion stylist producing ONE richly detailed outfit description "
    "for a photorealistic image pipeline. The text is dropped verbatim into a "
    "garment turnaround, so it must describe ONLY the clothes.\n\n"
    "ABSOLUTE RULES — breaking any of these ruins the image:\n"
    "0. ENRICH MODE: if a BASE outfit description is given below, your job is to "
    "ENRICH it — keep the SAME garments and the same overall look, and rewrite it "
    "with far richer, more precise, photographable detail (exact fabric weave, "
    "weight and finish; construction, seams, closures; cut, drape and how it "
    "falls; trims, hardware, stitching, prints/embroidery). Apply ONLY the "
    "adjustments the idea/attributes ask for (e.g. change the fabric, adapt to an "
    "occasion) — never swap it for a different outfit or drop its pieces. If NO "
    "base is given, design a complete new outfit from the idea and attributes.\n"
    "1. Describe ONLY the clothing, footwear and worn accessories, garment by "
    "garment: type, colour(s), fabric/material and finish, cut, fit and "
    "silhouette, neckline, sleeves, hemline/length, prints or embroidery, "
    "embellishments and hardware. Cover the top, then the bottom (or the dress/"
    "one-piece as a whole), then footwear, then jewellery and accessories.\n"
    "2. NEVER describe the person — not her face, body, hair, skin, age, "
    "ethnicity, build, expression or pose — and NEVER the background, setting or "
    "lighting. Those come from her own references. Write about garments only.\n"
    "3. TASTEFUL AND FULLY OPAQUE. Every garment is opaque and gives normal "
    "coverage. NEVER sheer, see-through, mesh, net, fishnet, transparent, "
    "cut-out, lingerie, underwear-as-outerwear, micro or otherwise revealing or "
    "explicit. Opaque and fitted is welcome; exposed or transparent is not. Keep "
    "it fashionable, editorial and elegant, never sexualised. This is a hard "
    "moderation limit — a revealing description makes the generation fail.\n"
    "4. Honour every constraint given (occasion, style, fabric, silhouette, "
    "formality, season) and the idea. Where silent, invent specific, believable, "
    "on-brief garment details. Prefer concrete, photographable facts over vague "
    "adjectives, and avoid AI-slop words (stunning, ethereal, hyper-realistic, "
    "8k, flawless, gorgeous).\n"
    "5. For Indian/ethnic looks (saree, lehenga, salwar kameez, anarkali, "
    "sharara, kurta set) describe the drape, blouse/choli, dupatta, borders, "
    "pleats and motifs precisely — and keep the blouse and coverage modest and "
    "opaque.\n\n"
    "Output ONLY the outfit description as one flowing paragraph — no preamble, "
    "no headings, no bullet points, no markdown, no quotes."
)

_OUTFIT_PICKS = [("occasion", "Occasion"), ("style", "Style / aesthetic"),
                 ("fabric", "Fabric"), ("silhouette", "Silhouette"),
                 ("formality", "Formality"), ("season", "Season")]


def write_outfit(base: str = "", idea: str = "", *, occasion: str = "",
                 style: str = "", fabric: str = "", silhouette: str = "",
                 formality: str = "", season: str = "") -> str:
    """ENRICH an existing outfit description (`base`, e.g. from a described image)
    into a richer, precise, opaque garment-only version — or, with no base, write
    a fresh outfit from the idea + structured picks. Raises PrompterError."""
    picks = {"occasion": occasion, "style": style, "fabric": fabric,
             "silhouette": silhouette, "formality": formality, "season": season}
    provided = {k: v.strip() for k, v in picks.items() if v and v.strip()}
    if not base.strip() and not idea.strip() and not provided:
        raise PrompterError("describe or type an outfit to enrich, or pick at "
                            "least one attribute / type an idea")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise PrompterError("ANTHROPIC_API_KEY is not set in .env")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise PrompterError("the 'anthropic' package is not installed") from exc

    label = dict(_OUTFIT_PICKS)
    lines = []
    if base.strip():
        lines.append("BASE outfit to enrich (keep these garments, add rich "
                     f"detail): {base.strip()}")
    if idea.strip():
        lines.append(f"{'Adjustments' if base.strip() else 'Outfit idea'}: {idea.strip()}")
    lines += [f"{label[k]}: {v}" for k, v in provided.items()]
    verb = ("Enrich the base outfit above into one richly detailed description"
            if base.strip() else
            "Design one outfit from these constraints (use only the ones given)")
    user = f"{verb}:\n" + "\n".join(lines) + "\n\nWrite the single outfit description now."

    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model="claude-opus-4-8", max_tokens=700,
            system=_OUTFIT_SYSTEM, messages=[{"role": "user", "content": user}])
    except anthropic.APIStatusError as exc:
        raise PrompterError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise PrompterError("could not reach the Claude API") from exc

    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not text:
        raise PrompterError("Claude returned an empty outfit description")
    return text
