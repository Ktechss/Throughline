"""Describe an uploaded outfit image with Claude vision.

The manual workflow this replaces: screenshot an outfit off the internet, paste
it into a chat AI, ask it to describe the clothes, copy the answer back into the
create-outfit box. This does that call directly — upload the reference, get a
clean garment-only description, review it, then feed it to
/api/wardrobe/create.

Deliberately garment-only. The turnaround generator already owns the face and
body (her references); the reference outfit photo contributes ONLY its clothing.
A description that leaks the stranger's face, pose, or background would fight
her identity references at generation time — the exact wardrobe-leak this
project keeps designing around. So the prompt asks for the clothes and nothing
else.

Also returns a STRUCTURED breakdown of the small details a reference photo often
crops out or hides — shoes, nail colour (hands + feet), lipstick, outfit colour,
lower-garment type. Each is filled only if visible; anything not visible comes
back empty so the UI can highlight it for the user to supply by hand.
"""

from __future__ import annotations

import base64
import json
import os

from . import config  # noqa: F401 — importing it runs load_dotenv(.env)

_MEDIA = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "webp": "image/webp", "gif": "image/gif",
}

# The detail fields the turnaround needs but a reference photo often doesn't show
# (heels cropped out, hands out of frame, no feet, lips not clear). Keys here are
# the contract with the frontend; order is display order.
DETAIL_KEYS = ["outfit_color", "lower_garment", "shoes", "hair", "jewellery",
               "bag", "outerwear", "belt", "sunglasses", "watch", "hair_accessory",
               "hosiery", "fingernails", "toenails", "lipstick"]

_SCHEMA = {
    "type": "object",
    "properties": {"description": {"type": "string"},
                   **{k: {"type": "string"} for k in DETAIL_KEYS}},
    "required": ["description", *DETAIL_KEYS],
    "additionalProperties": False,
}

_PROMPT = (
    "You are a fashion stylist describing an outfit so an image model can "
    "recreate it on a different person. Return a JSON object.\n\n"
    "`description`: ONLY the clothing, footwear, and worn accessories, garment by "
    "garment — type, colour(s), fabric/material and finish, fit and silhouette, "
    "notable details (neckline, sleeves, hemline, prints, embellishments, "
    "hardware). Cover top, then bottom (or the dress as one piece), footwear, "
    "then jewellery/accessories. One flowing paragraph, no preamble or markdown. "
    "Do NOT describe the person's face, body, hair, skin, pose, or the "
    "background.\n\n"
    "Then these specific fields — fill each ONLY with what is clearly visible in "
    "the image; if it is not visible or you cannot tell, return an empty string "
    "\"\" (do NOT guess):\n"
    "- `outfit_color`: the dominant colour(s) of the outfit\n"
    "- `lower_garment`: the lower-body garment TYPE (e.g. shorts, mini skirt, "
    "wide-leg trousers, jeans, or 'dress' if one-piece)\n"
    "- `shoes`: footwear / heels (type, colour, heel height)\n"
    "- `hair`: the hairstyle AND hair colour (e.g. 'sleek high ponytail, jet "
    "black', 'loose beach waves, honey brown', 'braided updo, dark brown')\n"
    "- `jewellery`: earrings, necklace, bracelets, rings (type, metal, stones)\n"
    "- `bag`: handbag or clutch (type, colour, hardware)\n"
    "- `outerwear`: any jacket, coat, blazer, shrug or dupatta layered over\n"
    "- `belt`: belt (type, colour, buckle)\n"
    "- `sunglasses`: sunglasses / eyewear (shape, colour)\n"
    "- `watch`: wristwatch (type, colour)\n"
    "- `hair_accessory`: worn scarf, headband, hair clip or hat\n"
    "- `hosiery`: opaque tights, stockings or socks (colour) — opaque only\n"
    "- `fingernails`: fingernail polish colour\n"
    "- `toenails`: toenail polish colour\n"
    "- `lipstick`: lip colour\n"
)


class DescribeError(RuntimeError):
    """Anything that stops us returning a description — surfaced to the UI."""


def media_type(filename: str, content_type: str | None) -> str:
    if content_type and content_type.startswith("image/"):
        return content_type
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MEDIA.get(ext, "image/png")


def _fit_image(image_bytes: bytes, media: str) -> tuple[bytes, str]:
    """Claude caps request images at 10 MB (and resizes to ~1568px anyway), so a
    full-res outfit photo blows the limit. Downscale large inputs to a 1568px long
    edge and re-encode as JPEG; small ones pass through untouched. Any failure
    falls back to the original bytes so describe never breaks on this."""
    if len(image_bytes) < 4_000_000:
        return image_bytes, media
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        im.thumbnail((1568, 1568))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 — describe must not break on downscaling
        return image_bytes, media


def describe_outfit(image_bytes: bytes, media: str = "image/png") -> dict:
    """Return {description, details:{...}} for the outfit in the image.

    `details` has one key per DETAIL_KEYS; a value is "" when Claude could not
    see that detail, which the UI highlights as a field the user must supply.

    Uses Claude Opus 4.8 vision with a strict JSON schema. Raises DescribeError
    with a readable message on any failure so the endpoint can 400 cleanly.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise DescribeError(
            "ANTHROPIC_API_KEY is not set in .env — add it to use AI describe.")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - install-time only
        raise DescribeError(
            "the 'anthropic' package is not installed in this venv") from exc

    image_bytes, media = _fit_image(image_bytes, media)   # keep under Claude's 10 MB cap
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    client = anthropic.Anthropic()   # key from ANTHROPIC_API_KEY
    try:
        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media, "data": b64}},
                    {"type": "text", "text": _PROMPT},
                ],
            }],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
    except anthropic.APIStatusError as exc:
        raise DescribeError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise DescribeError("could not reach the Claude API — check your "
                            "connection") from exc

    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DescribeError("Claude returned malformed JSON") from exc

    description = (data.get("description") or "").strip()
    if not description:
        raise DescribeError("Claude returned no description for this image")
    details = {k: (data.get(k) or "").strip() for k in DETAIL_KEYS}
    return {"description": description, "details": details}


# ------------------------------------------------------------- motion direction
#
# Read a still and propose what should MOVE in it.
#
# The identity rule survives the jump to video, for the same measured reason it
# exists on stills: words specify a type, not a person. Frame one already carries
# her — describing her again in the motion prompt invites the video model to
# redraw the face it was handed. So this is told, forcefully, to direct motion
# and camera and nothing else.
#
# The second rule is specific to image-to-video and is not obvious: a clip cannot
# use what the frame does not show. Direct a hand gesture on a shot cropped at the
# shoulders and the model invents hands — which is drift the gate cannot even
# score, because frame scoring is Phase 2.
_MOTION_KEYS = ["read", "caution", "best", "best_why",
                "suggested_duration", "duration_why", "suggestions"]

_MOTION_SCHEMA = {
    "type": "object",
    "properties": {
        "read": {"type": "string"},
        "caution": {"type": "string"},
        # How long the transition actually needs. Only meaningful with two
        # frames: with one there is nothing to arrive at, so the length is a
        # taste call and this echoes what was asked for.
        "suggested_duration": {"type": "integer"},
        "duration_why": {"type": "string"},
        # Which of the three to shoot. Three equally-weighted options is a
        # decision handed back to the owner unmade — and the model has just read
        # the frame closely enough to have an opinion, so it states one.
        "best": {"type": "integer"},
        "best_why": {"type": "string"},
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "prompt": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["title", "prompt", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": _MOTION_KEYS,
    "additionalProperties": False,
}


def _beats(duration: int) -> str:
    """How much can actually happen in `duration` seconds, said plainly.

    A 5s clip that is directed like a 10s one runs out of time mid-gesture and
    the model either rushes it or loops. Stating the beat budget is the cheapest
    fix, and it has to be computed rather than hardcoded because the catalogue
    spans 2s (seedance) to 20s (sora).
    """
    if duration <= 3:
        return ("about ONE small beat — a breath, a blink, a single shift of "
                "weight. Nothing with a beginning and an end.")
    if duration <= 6:
        return ("ONE continuous beat — a single gesture or look that starts and "
                "settles. Do not chain two actions.")
    if duration <= 12:
        return ("TWO beats at most — one action, then a settle or a second, "
                "smaller reaction. Still one continuous take.")
    return ("THREE beats at most, unhurried. Long clips drift more, so keep each "
            "beat small rather than adding more of them.")


_MOTION_PROMPT = (
    "You are directing a short image-to-video clip. The attached image is FRAME "
    "ONE — it is fixed and already rendered. Your job is to say what happens "
    "next. Return a JSON object.\n\n"
    "ABSOLUTE RULES — breaking any of these ruins the clip:\n"
    "1. NEVER describe the woman: not her face, eyes, hair, skin, age, build, "
    "or clothing. The frame already carries all of that. Describing her makes "
    "the video model redraw her as a different person, which is the single "
    "worst failure this pipeline has. Refer to her only as 'she'.\n"
    "2. Direct MOTION and CAMERA only — what moves, how much, how fast, and "
    "what the camera does (or, better, does not do).\n"
    "3. ONE CONTINUOUS TAKE. No cuts, no scene changes, no new location, no "
    "one else entering frame, no change of outfit. The clip cannot leave this "
    "moment.\n"
    "4. YOU CANNOT USE WHAT THE FRAME DOES NOT SHOW. If her hands are outside "
    "the crop, do not direct a hand gesture; if it is a head-and-shoulders "
    "shot, do not direct her to walk. Anything off-frame gets invented, and an "
    "invented limb is worse than no motion.\n"
    "5. SMALL BEATS BIG. Subtle motion holds the likeness; fast or large motion "
    "smears the face across frames. Prefer breath, weight shifts, a slow turn, "
    "hair and fabric settling, light changing. Avoid anything sudden.\n"
    "6. Each prompt is 15-40 words, plain and directive. No adjectives about "
    "beauty or mood, no 'cinematic', 'stunning', '8k', 'masterpiece'.\n"
    "7. The video providers run a content classifier over the prompt AND the "
    "frame, and a refusal costs the render. Write motion the way a camera "
    "operator would call it — never 'sensual', 'seductive', 'sultry', "
    "'provocative', 'alluring', and no wording about her body being revealed. "
    "Describing a garment is fine; describing what it shows is not.\n\n"
    "Fields:\n"
    "- `read`: 1-2 sentences on what is ACTUALLY in this frame — the framing "
    "(how much of her is visible), what she appears to be doing, the setting, "
    "and what in it could plausibly move. This is observation, not direction.\n"
    "- `suggestions`: exactly THREE options that differ from each other in kind "
    "— not three phrasings of the same motion. Vary which of these leads: her "
    "own movement, the camera, or the environment (light, fabric, background "
    "life). Each has:\n"
    "    `title`: 2-4 words, e.g. 'Slow turn to camera'\n"
    "    `prompt`: the text sent to the video model, per the rules above\n"
    "    `why`: one sentence on why it suits THIS frame specifically\n"
    "- `best`: the index — 0, 1 or 2 — of the option you would actually shoot. "
    "Judge on two things together: which is most likely to hold her likeness "
    "(smaller, better-supported motion wins), and which produces a clip worth "
    "having rather than a still that merely wobbles. When those conflict, "
    "likeness wins — a beautiful clip of someone else is worthless here.\n"
    "- `best_why`: one sentence on what makes that one the pick OVER THE OTHER "
    "TWO specifically. Name the trade, don't just praise it.\n"
    "- `caution`: the one thing most likely to go wrong if this frame is "
    "animated — a crop that invites invented limbs, a pose too unstable to "
    "hold, a busy background that will churn. Empty string if nothing stands out."
)

_MOTION_IDEA = (
    "\n\nTHE OWNER HAS ASKED FOR SOMETHING SPECIFIC:\n{idea}\n\n"
    "All three suggestions must serve that idea — give three different ways to "
    "achieve it, not three unrelated motions with the idea bolted on. Every "
    "rule above still binds: if the idea cannot be done from this frame (it "
    "needs a limb that is cropped out, a second person, a cut, or motion large "
    "enough to smear her face), say so plainly in `caution`, then offer the "
    "closest thing the frame CAN support instead of silently substituting one."
)


_MOTION_END = (
    "\n\nTHERE ARE TWO IMAGES. The FIRST is frame one. The SECOND is the LAST "
    "frame — the clip must arrive there. Both are fixed and already rendered; "
    "the model interpolates between them.\n\n"
    "This changes the job entirely: you are not inventing a motion, you are "
    "describing the JOURNEY from the first pose to the second, and precision is "
    "what makes it land. Work it out before you write.\n\n"
    "First, compare the two frames along EVERY one of these axes and note which "
    "actually differ:\n"
    "  - body: what supports her weight, where each limb is, which way she faces\n"
    "  - head and gaze: angle, direction, eyeline\n"
    "  - hands: where each one starts and ends\n"
    "  - camera: height, distance, angle\n"
    "  - light: direction, intensity, where the shadow falls\n"
    "  - setting and wardrobe: anything present in one frame and not the other\n\n"
    "Then write each `prompt` as an ORDERED transition, not a mood: what moves "
    "first, what follows, what settles last, and where each moving part ends up. "
    "Name the end state explicitly — 'ending with both hands at her collarbone' "
    "beats 'she raises her hands'. Never direct a motion that would have to undo "
    "itself to reach frame two, and never direct a part that is identical in both "
    "frames to move.\n\n"
    "`read` must state what CHANGES between the two, axis by axis — not what is "
    "in either one on its own.\n\n"
    "`caution`: name any axis that cannot honestly be bridged — a change of "
    "support, of wardrobe, of location, or a second person. Those get covered by "
    "a smeared morph or an invented cut, and that is worth knowing before it is "
    "paid for."
)

_MOTION_DURATION = (
    "\n\n`suggested_duration`: how many seconds this transition HONESTLY needs. "
    "Choose from exactly these allowed values: {allowed}. Judge it by how much "
    "has to change, not by what was asked for — a small head or hand move reads "
    "well in 3-5s, a whole-body change of support or a camera move across the "
    "room needs 8-12s, and several axes changing at once needs the upper end. Too "
    "short and the model rushes or morphs; too long and it invents filler motion "
    "or loops. If the length currently selected is already right, return it "
    "unchanged.\n"
    "`duration_why`: one sentence naming what specifically needs the time."
)


def suggest_motion(image_bytes: bytes, media: str = "image/png", *,
                   duration: int = 5, context: str = "", idea: str = "",
                   end_bytes: bytes | None = None, end_media: str = "image/png",
                   allowed_durations: list[int] | None = None,
                   continuing: bool = False) -> dict:
    """Read one still and propose three ways to animate it, and name the best.

    `context` is whatever the run already knows about the shot — its brief, the
    outfit, the pose. It is supplied because the frame alone cannot say what the
    shot was FOR, and a suggestion that fights the brief is wasted.

    `idea` is the owner steering: "she laughs and looks away", "make it feel
    like a video call". With one, the three options become three ways to shoot
    THAT rather than three unrelated motions — and an idea the frame cannot
    support is refused in `caution` rather than quietly swapped for something
    else, because a silent substitution is how you pay for a clip you did not
    ask for.

    `continuing` marks a frame lifted off the end of an existing clip rather than
    an approved still: the motion should read as a continuation of movement
    already underway, not as a fresh start from rest.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise DescribeError(
            "ANTHROPIC_API_KEY is not set in .env — add it to use AI suggestions.")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - install-time only
        raise DescribeError(
            "the 'anthropic' package is not installed in this venv") from exc

    image_bytes, media = _fit_image(image_bytes, media)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    content = [{"type": "image", "source": {
        "type": "base64", "media_type": media, "data": b64}}]
    if end_bytes is not None:
        end_bytes, end_media = _fit_image(end_bytes, end_media)
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": end_media,
            "data": base64.standard_b64encode(end_bytes).decode("ascii")}})

    task = [_MOTION_PROMPT, f"\n\nThe clip is {duration} seconds long: {_beats(duration)}"]
    if end_bytes is not None:
        task.append(_MOTION_END)
        # Only ask for a length when there are two frames. With one there is
        # nothing to arrive at, so "how long does this need" has no answer the
        # image can support — it is a taste call, and inventing a number would
        # dress one up as a measurement.
        allowed = allowed_durations or [duration]
        task.append(_MOTION_DURATION.format(
            allowed=", ".join(f"{d}s" for d in allowed)))
    if continuing:
        task.append(
            "\n\nThis frame is the LAST FRAME of a clip that just played, not a "
            "posed still. She is already mid-movement. Direct motion that "
            "continues what is evidently underway — a clip that restarts from "
            "rest reads as a visible cut.")
    if context.strip():
        task.append(f"\n\nWhat this shot was for: {context.strip()}")
    if idea.strip():
        task.append(_MOTION_IDEA.format(idea=idea.strip()))

    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model="claude-opus-5",
            # Thinking counts against max_tokens, and the two-frame task is a
            # six-axis comparison plus a length judgement — far heavier than the
            # single-frame read this started as. At 2000 an overrun truncates the
            # JSON mid-object, which surfaces as "Claude returned malformed JSON"
            # rather than as the token limit it actually is.
            max_tokens=8000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user",
                       "content": [*content, {"type": "text", "text": "".join(task)}]}],
            # effort and format are both fields of output_config — passing them
            # as two arguments silently drops one.
            output_config={"effort": "medium",
                           "format": {"type": "json_schema",
                                      "schema": _MOTION_SCHEMA}},
        )
    except anthropic.APIStatusError as exc:
        raise DescribeError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise DescribeError("could not reach the Claude API — check your "
                            "connection") from exc

    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DescribeError("Claude returned malformed JSON") from exc

    picks = [
        {"title": (s.get("title") or "").strip(),
         "prompt": (s.get("prompt") or "").strip(),
         "why": (s.get("why") or "").strip()}
        for s in (data.get("suggestions") or [])
        if (s.get("prompt") or "").strip()
    ]
    if not picks:
        raise DescribeError("Claude returned no motion suggestions for this frame")

    # `best` is a model-supplied index into a list the same model produced, and
    # the two can disagree — a suggestion dropped above for an empty prompt
    # shifts every index after it. Clamped rather than trusted, because an
    # out-of-range pick would crash the panel over a cosmetic badge.
    try:
        best = int(data.get("best", 0))
    except (TypeError, ValueError):
        best = 0
    if not 0 <= best < len(picks):
        best = 0

    # Same treatment as `best`: a model-supplied number is clamped to what the
    # chosen video model can actually render, so a recommendation can never
    # offer a length the provider would reject.
    want = duration
    if end_bytes is not None:
        try:
            want = int(data.get("suggested_duration") or duration)
        except (TypeError, ValueError):
            want = duration
        allowed = allowed_durations or [duration]
        if want not in allowed:
            want = min(allowed, key=lambda d: abs(d - want))

    return {"read": (data.get("read") or "").strip(),
            "caution": (data.get("caution") or "").strip(),
            "best": best,
            "best_why": (data.get("best_why") or "").strip(),
            "suggested_duration": want,
            "duration_why": ((data.get("duration_why") or "").strip()
                             if end_bytes is not None else ""),
            "suggestions": picks}
