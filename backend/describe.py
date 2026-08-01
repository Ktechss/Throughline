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


_NAIL_PROMPT = (
    "This is a photo of a manicure. In ONE or TWO sentences, describe the NAILS "
    "only — nail shape (almond/square/coffin/oval/stiletto/round), length "
    "(short/medium/long), base colour and finish (glossy/matte/chrome), and any "
    "nail art (French tip, ombré, glitter, stones, floral, etc.). Be concrete and "
    "specific so the manicure can be reproduced. Do NOT describe the hand, skin, "
    "rings, background, or anything but the nails. Reply with the description only, "
    "no preamble."
)


def describe_nails(image_bytes: bytes, media: str = "image/png") -> str:
    """Return a short manicure description for the nails in the image (Claude vision)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise DescribeError(
            "ANTHROPIC_API_KEY is not set in .env — add it to use AI describe.")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - install-time only
        raise DescribeError(
            "the 'anthropic' package is not installed in this venv") from exc

    image_bytes, media = _fit_image(image_bytes, media)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media, "data": b64}},
                    {"type": "text", "text": _NAIL_PROMPT},
                ],
            }],
        )
    except anthropic.APIStatusError as exc:
        raise DescribeError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise DescribeError("could not reach the Claude API — check your connection") from exc

    return "".join(b.text for b in msg.content if b.type == "text").strip()


# Reference-face INSPIRATION, not likeness. This deliberately extracts only
# GENERAL, non-identifying attributes so we can create a NEW fictional person with
# a similar overall look — never a copy of a real individual (the project's hard
# rule: no real person's likeness, ever). The specific identity is intentionally
# discarded here; the face is then generated from text, with no image identity ref.
_FACE_ATTR_PROMPT = (
    "You are helping design an ORIGINAL, entirely fictional character inspired by "
    "the GENERAL look of this photo — never a likeness of the person shown. In 2-3 "
    "sentences describe only GENERAL, non-identifying attributes: approximate age "
    "range, skin tone, hair colour/length/texture, eye colour, general face shape, "
    "and overall vibe/energy. Describe a TYPE, not this individual. Do NOT attempt "
    "to capture their unique identity or likeness, do NOT name or guess who they "
    "are, and do NOT mention any distinctive identifying marks. Reply with the "
    "description only, no preamble."
)


def describe_face_attributes(image_bytes: bytes, media: str = "image/png") -> str:
    """General, non-identifying appearance attributes for a reference face (Claude
    vision) — inspiration for a NEW fictional person, NOT the specific likeness."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise DescribeError(
            "ANTHROPIC_API_KEY is not set in .env — add it to use AI describe.")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - install-time only
        raise DescribeError(
            "the 'anthropic' package is not installed in this venv") from exc

    image_bytes, media = _fit_image(image_bytes, media)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    client = anthropic.Anthropic()
    try:
        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media, "data": b64}},
                    {"type": "text", "text": _FACE_ATTR_PROMPT},
                ],
            }],
        )
    except anthropic.APIStatusError as exc:
        raise DescribeError(f"Claude API error: {exc.message}"[:300]) from exc
    except anthropic.APIConnectionError as exc:
        raise DescribeError("could not reach the Claude API — check your connection") from exc

    return "".join(b.text for b in msg.content if b.type == "text").strip()
