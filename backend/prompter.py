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
    "4. Keep it SHORT and directive: roughly 40-110 words. Concrete photographic "
    "facts beat adjectives.\n"
    "5. Do NOT sexualise: no revealing/tight/skimpy intensifiers, no anatomical "
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


# The video director: a scenario -> a full clip plan (dialogue, scene, camera,
# duration) that fills the happy-horse configurator. Same iron rule as the image
# prompter: it directs the SCENE and her WORDS, never her face — identity lives
# in the still.
_VIDEO_SYSTEM = (
    "You are a short-form video director for a photorealistic character named "
    "Kiara — a warm, quietly witty South Delhi fashion stylist who dresses brides "
    "and styles everyday looks. The user gives a scenario; you turn it into a plan "
    "for a short vertical (9:16) clip that animates a still photo of her on an "
    "image-to-video model.\n\n"
    "ABSOLUTE RULES:\n"
    "1. NEVER describe her face, body, hair, skin, age or identity — she is a "
    "fixed reference image. Describe only the SCENE, the MOVEMENT, atmosphere, "
    "wardrobe-in-motion, lighting and camera.\n"
    "2. DIALOGUE: only if she actually speaks. Write it in her own voice — first "
    "person, warm, natural, a little dry, never salesy. Fit ~2.5 spoken words per "
    "second of duration. For a silent action/mood clip (a runway walk, a turn, "
    "dancing), return an empty dialogue string.\n"
    "3. SCENE / MOTION — this is the most important field. Image-to-video models "
    "follow MOVEMENT described as ONE continuous, ordered action in plain language "
    "(they ignore timestamps and bracketed beats — never use them). Describe where "
    "she starts, how she moves through the shot, and how it ends, as a single "
    "flowing sentence or two. For a runway/walk: name the stride, the pace, the "
    "hip sway from posture, the fabric catching the movement, whether she comes "
    "toward or moves away from camera, any pause or turn. Keep the FRAMING the "
    "scenario asks for (full-body / wide for a walk; waist-up or close for "
    "talking). Concrete and physical. No AI-slop words.\n"
    "4. camera_move — pick ONE from the exact list of valid moves given in the "
    "user message (they cover framing angles, dolly/zoom pushes, pans/tilts/"
    "cranes, orbits, and handheld/FPV/whip specials). For a subject who walks "
    "toward the camera, prefer 'static' (let HER move) or a gentle 'dolly-in'; "
    "match the move to the mood.\n"
    "5. model — 'happy-horse' when she SPEAKS (it lip-syncs dialogue); 'seedance' "
    "for silent motion/action (stronger, cleaner body and scene movement).\n"
    "6. duration — an integer 3-15 seconds that fits the action/dialogue.\n"
    "7. resolution — '1080p' by default (hero/close/talking shots); '720p' only "
    "for a very long or quick throwaway clip.\n"
    "8. image_brief — describe the STILL PHOTO to generate that this clip will "
    "animate: the location/setting, the FRAMING (a waist-up or close portrait for "
    "a talking clip so her face is large; full-body/wide for a walk or full-look "
    "reveal), her pose, and the mood/light. This is a photo brief, not the motion "
    "— still NEVER describe her face or identity.\n"
    "9. wardrobe — from the exact wardrobe id list given in the user message, pick "
    "the ONE outfit that best fits the scene (a wedding -> a saree/ethnic look; a "
    "club/gala -> a gown; office -> workwear; casual day -> everyday). Return an "
    "empty string if none clearly fits or the scene doesn't call for a set look.\n"
    "10. note — ONE short sentence explaining your picks (outfit, model, camera, "
    "duration) so the user trusts the defaults. They can override anything.\n\n"
    "Output ONLY a JSON object, no prose, no code fences: {\"dialogue\": string, "
    "\"scene\": string, \"image_brief\": string, \"wardrobe\": string, "
    "\"camera_move\": string, \"model\": string, \"duration\": integer, "
    "\"resolution\": string, \"note\": string}."
)


_STORYBOARD_SYSTEM = (
    "You are a short-form video director for a photorealistic character named "
    "Kiara — a warm, quietly witty South Delhi fashion stylist. The user gives a "
    "scenario and a target length; you break it into a STORYBOARD of short scenes "
    "for a single vertical (9:16) clip. Each scene will be a separate still photo "
    "of her that gets animated, then all the clips are stitched together in order.\n\n"
    "ABSOLUTE RULES:\n"
    "1. NEVER describe her face, body, hair, skin, age or identity — she is a "
    "fixed reference. Describe only location, action, expression, wardrobe-in-"
    "motion, light and camera.\n"
    "2. ONE wardrobe for the whole video (continuity): from the wardrobe id list "
    "given, pick the single outfit that best fits, or empty if none fits.\n"
    "3. ONE model for the whole video: 'happy-horse' if ANY scene has spoken "
    "dialogue (it lip-syncs); otherwise 'seedance' (cleaner silent motion).\n"
    "4. Break the scenario into scenes of ~2-4 seconds each so the durations sum "
    "to about the target length (e.g. a 15s clip = about 4-6 scenes). Each scene "
    "is a distinct beat — a change of location, action, angle or expression.\n"
    "5. For EACH scene give: location, action (what she physically does), "
    "expression (mood), image_brief (the still to generate: setting + FRAMING + "
    "pose + light — waist-up/close for talking or expression beats, full-body/"
    "wide for movement), motion (the ordered continuous movement for the video, "
    "no timestamps), camera_move (one valid value), dialogue (her spoken line for "
    "this beat, or empty), and duration (integer seconds).\n\n"
    "Output ONLY a JSON object, no prose, no code fences: {\"wardrobe\": string, "
    "\"model\": string, \"note\": string, \"scenes\": [{\"location\": string, "
    "\"action\": string, \"expression\": string, \"image_brief\": string, "
    "\"motion\": string, \"camera_move\": string, \"dialogue\": string, "
    "\"duration\": integer}]}."
)


def storyboard(scenario: str, wardrobe_ids: list[str] | None = None,
               total_duration: int = 15) -> dict:
    """Break a scenario into an ordered multi-scene storyboard. Raises PrompterError."""
    if not scenario.strip():
        raise PrompterError("describe the video first")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise PrompterError("ANTHROPIC_API_KEY is not set in .env")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise PrompterError("the 'anthropic' package is not installed") from exc

    from . import video as _video
    moves = ", ".join(_video.CAMERA_MOVES.keys())
    wardrobe = ", ".join(wardrobe_ids or []) or "(none available)"
    total = max(4, min(30, int(total_duration)))

    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model="claude-opus-4-8", max_tokens=2000, system=_STORYBOARD_SYSTEM,
            messages=[{"role": "user",
                       "content": (f"Scenario: {scenario.strip()}\n\n"
                                   f"Target total length: about {total} seconds.\n"
                                   f"Valid camera_move values: {moves}\n"
                                   f"Wardrobe ids to choose from: {wardrobe}\n\n"
                                   "Write the JSON storyboard now.")}])
    except anthropic.APIStatusError as exc:
        raise PrompterError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise PrompterError("could not reach the Claude API") from exc

    import json
    import re
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise PrompterError("the director did not return a storyboard")
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise PrompterError("could not parse the storyboard") from exc

    raw_scenes = d.get("scenes") or []
    if not raw_scenes:
        raise PrompterError("the storyboard had no scenes")
    scenes = []
    any_dialogue = False
    for s in raw_scenes[:8]:   # cap at 8 scenes
        cam = str(s.get("camera_move", "dolly-in"))
        try:
            sdur = max(2, min(8, int(s.get("duration", 3))))
        except (TypeError, ValueError):
            sdur = 3
        dlg = str(s.get("dialogue") or "").strip()
        any_dialogue = any_dialogue or bool(dlg)
        scenes.append({
            "location": str(s.get("location") or "").strip(),
            "action": str(s.get("action") or "").strip(),
            "expression": str(s.get("expression") or "").strip(),
            "image_brief": str(s.get("image_brief") or "").strip(),
            "motion": str(s.get("motion") or s.get("action") or "").strip(),
            "camera_move": cam if cam in _video.CAMERA_MOVES else "dolly-in",
            "dialogue": dlg,
            "duration": sdur,
        })
    ward = str(d.get("wardrobe") or "").strip()
    if wardrobe_ids is not None and ward and ward not in wardrobe_ids:
        ward = ""
    mdl = str(d.get("model") or "").strip()
    if mdl not in ("happy-horse", "seedance"):
        mdl = "happy-horse" if any_dialogue else "seedance"
    return {"wardrobe": ward, "model": mdl, "note": str(d.get("note") or "").strip(),
            "scenes": scenes}


def direct_video(scenario: str, wardrobe_ids: list[str] | None = None) -> dict:
    """Expand a scenario into a clip plan for the video studio. Raises PrompterError."""
    if not scenario.strip():
        raise PrompterError("describe a scenario first — the director needs something to work with")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise PrompterError("ANTHROPIC_API_KEY is not set in .env")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise PrompterError("the 'anthropic' package is not installed") from exc

    from . import video as _video
    moves = ", ".join(_video.CAMERA_MOVES.keys())
    wardrobe = ", ".join(wardrobe_ids or []) or "(none available)"

    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model="claude-opus-4-8", max_tokens=900, system=_VIDEO_SYSTEM,
            messages=[{"role": "user",
                       "content": (f"Scenario: {scenario.strip()}\n\n"
                                   f"Valid camera_move values (pick exactly one): {moves}\n\n"
                                   f"Wardrobe ids to choose from (pick one that fits, or empty): {wardrobe}\n\n"
                                   "Write the JSON clip plan now.")}])
    except anthropic.APIStatusError as exc:
        raise PrompterError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise PrompterError("could not reach the Claude API") from exc

    import json
    import re
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise PrompterError("the director did not return a usable plan")
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise PrompterError("could not parse the director's plan") from exc

    cam = str(d.get("camera_move", "dolly-in"))
    mdl = str(d.get("model", "")).strip()
    try:
        dur = max(3, min(15, int(d.get("duration", 8))))
    except (TypeError, ValueError):
        dur = 8
    dialogue = str(d.get("dialogue") or "").strip()
    # silent action -> seedance (cleaner motion); talking -> happy-horse (lip-sync)
    if mdl not in ("happy-horse", "seedance", "kling"):
        mdl = "happy-horse" if dialogue else "seedance"
    res = str(d.get("resolution", "1080p")).strip()
    ward = str(d.get("wardrobe") or "").strip()
    if wardrobe_ids is not None and ward and ward not in wardrobe_ids:
        ward = ""   # the director must pick a real id or nothing
    return {
        "dialogue": dialogue,
        "scene": str(d.get("scene") or "").strip(),
        "image_brief": str(d.get("image_brief") or "").strip(),
        "wardrobe": ward,
        "camera_move": cam if cam in _video.CAMERA_MOVES else "dolly-in",
        "model": mdl,
        "duration": dur,
        "resolution": res if res in ("720p", "1080p") else "1080p",
        "note": str(d.get("note") or "").strip(),
    }
