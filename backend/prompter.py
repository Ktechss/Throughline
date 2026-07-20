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
