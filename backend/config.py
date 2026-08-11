"""Paths and env. Single source of truth — nothing else builds a path by hand.

MULTI-CHARACTER (phase 4): the per-character state (images, refs, gallery, bio,
wardrobe, …) now lives under data/characters/<id>/, and the path constants below
are LIVE PROXIES that resolve against whichever character is ACTIVE. That is what
lets `from .config import IMAGES` stay unchanged in every module while IMAGES
follows the active character — single user, single process, so one process-global
active id is enough. The global database (data/eve1.db) and the fal endpoint
config are NOT per-character and stay plain constants.
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
CHARACTERS = DATA / "characters"      # one folder per character
DEFAULT_CHARACTER = "kiara"           # the original single-character build
_ACTIVE_FILE = DATA / "active_character.json"

CHARACTERS.mkdir(parents=True, exist_ok=True)

# The active character is cached in a module global and mirrored to a tiny file
# so it survives a restart. set_active() is the ONLY writer.
_active_id: str | None = None

# A per-request override of the active character.
#
# The process global below is the LAST RESORT, not the source of truth. It is one
# mutable value shared by every caller, so anything that switched it — a second
# tab, a script, another window — silently redirected work that was already in
# flight somewhere else. Observed: a wardrobe generated while the browser showed
# one character was filed under a different one, because a switch had happened
# between the page loading and the button being pressed.
#
# A ContextVar makes the answer per-request: the browser states which character
# it is looking at on every call (the X-Character header), the middleware sets it
# here for the life of that request, and concurrent requests for different
# characters cannot overwrite each other the way a global does.
#
# ⚠ Background threads do NOT inherit this. A job that outlives its request must
# take an explicit character id — see generate(character=...) — which is why that
# parameter exists and why every long build passes it.
_active_ctx: ContextVar[str | None] = ContextVar("active_character", default=None)


def get_active() -> str:
    scoped = _active_ctx.get()
    if scoped:
        return scoped
    global _active_id
    if _active_id is None:
        try:
            _active_id = json.loads(_ACTIVE_FILE.read_text())["id"]
        except Exception:  # noqa: BLE001 — missing/corrupt file -> the default
            _active_id = DEFAULT_CHARACTER
    return _active_id


def scope_active(cid: str | None):
    """Pin the active character for the current request. Returns the token to
    reset with, or None if nothing was pinned."""
    return _active_ctx.set(cid) if cid else None


def unscope_active(token) -> None:
    if token is not None:
        _active_ctx.reset(token)


def set_active(cid: str) -> None:
    """Change the PERSISTENT default — the character a fresh page or a background
    job gets. Deliberately separate from the per-request scope above."""
    global _active_id
    _active_id = cid
    _ACTIVE_FILE.write_text(json.dumps({"id": cid}))


def char_base(cid: str | None = None) -> Path:
    """The folder holding one character's entire state."""
    return CHARACTERS / (cid or get_active())


class CharPath:
    """A Path-like proxy that resolves against the ACTIVE character's folder on
    every operation. `IMAGES = CharPath("images")` makes `IMAGES / "x.png"`,
    `IMAGES.glob(...)`, `open(IMAGES/..)` and `str(IMAGES)` all follow whichever
    character is active — so no call site has to thread a character id through."""

    __slots__ = ("_parts",)

    def __init__(self, *parts: str):
        self._parts = parts

    def _resolve(self) -> Path:
        return char_base().joinpath(*self._parts)

    def __truediv__(self, other) -> Path:
        return self._resolve() / other

    def __fspath__(self) -> str:            # open(), os.path, shutil, FileResponse
        return str(self._resolve())

    def __str__(self) -> str:               # f-strings, str()
        return str(self._resolve())

    def __repr__(self) -> str:
        return f"CharPath({'/'.join(self._parts)!r} -> {self._resolve()})"

    def __getattr__(self, name):            # .exists/.glob/.mkdir/.iterdir/.name/…
        return getattr(self._resolve(), name)


# --- per-character paths (resolve against the active character) ---------------
IMAGES = CharPath("images")           # generated images
REFS = CharPath("refs")               # identity references — the face we're holding
WARDROBE = CharPath("wardrobe")       # outfit reference images (@image2 per shot)
POSE_REFS = CharPath("pose-refs")     # pose reference images of HER (keyword-selected)
NAILS = CharPath("nails")             # manicure/nail-style reference images (attached @imageN)
PLACES = CharPath("places")           # location/home reference images (attached @imageN)
POSES = CharPath("poses")             # saved skeletons
BODIES = CharPath("bodies")           # saved BODY types (figure references, selectable)
GOLD = CharPath("gold")               # human-APPROVED shots — the curated LoRA dataset.
                                      # Approvals accumulate HERE, never in the gallery
                                      # (that stays frozen — feeding it generated output
                                      # drifts the yardstick; see gate.py).
STATE = CharPath("state")             # part tree, gallery, threshold, bio (per character)

GALLERY_PATH = CharPath("state", "gallery.npz")
GALLERY_META = CharPath("state", "gallery.json")   # per-entry yaw/face_px — needed to
                                                   # know whether a comparison is fair
THRESHOLD_PATH = CharPath("state", "threshold.json")
PARTS_PATH = CharPath("state", "parts.json")
BODIES_META = CharPath("state", "bodies.json")     # body-type metadata: build text + active
NAILS_META = CharPath("state", "nails.json")       # nail-style metadata: {stem: {description}}
PLACES_META = CharPath("state", "places.json")     # place metadata: {stem: {name, category}}
HOME_PATH = CharPath("state", "home.json")         # her home: {style}; corner images live in places/<key>.*
BIO_PATH = CharPath("state", "bio.json")           # reference / body_reference / calib_seed


def bio_face() -> Path:
    """The ACTIVE character's identity reference, resolved at call time.

    Scripts used to hardcode `REFS / "Kiara.png"`. That filename stopped existing
    the moment the identity was re-seeded from a calibration face, and five
    scripts broke silently-at-startup together. A reference is per-character and
    gets renamed; the only durable answer is to ask bio.json who she is now.
    """
    try:
        name = json.loads(BIO_PATH.read_text())["reference"]
    except Exception:  # noqa: BLE001 — no bio yet / malformed: fall back below
        name = ""
    p = REFS / name if name else None
    if p and p.exists():
        return p
    faces = sorted(REFS.glob("*.webp")) + sorted(REFS.glob("*.png"))
    if not faces:
        raise FileNotFoundError(f"no identity reference in {REFS}")
    return faces[0]
TIMELINE_PATH = CharPath("state", "timeline.json")  # her year: {eras: [{from, name, hair, note}]}


def ensure_char_dirs(cid: str | None = None) -> None:
    """Create the full folder skeleton for one character (idempotent)."""
    base = char_base(cid)
    for name in ("images", "refs", "wardrobe", "pose-refs", "poses",
                 "bodies", "gold", "nails", "places", "state"):
        (base / name).mkdir(parents=True, exist_ok=True)


# Ensure the active character's folders exist on import (fresh installs + the
# default character). Other characters get their dirs at creation time.
ensure_char_dirs()

# fal endpoints. Local inference is off the table — an 8GB laptop GPU cannot run
# FLUX.2 (32B) or klein 4B (~13GB).
#
# gpt-image-2 is the identity generator. Measured 2026-07-17 on one face
# reference, frontal close-up, scored on the 5-angle gallery:
#
#   openai/gpt-image-2/edit .... 0.813   <- above her own sheets
#   her own reference sheets ... 0.797
#   ideogram/character ......... 0.750
#   FLUX LoRA @1000 ............ 0.742
#   flux-pulid ................. 0.713
#   nano-banana-pro/edit ....... 0.678
#
# ⚠ That number is a FRONTAL STUDIO CLOSE-UP — the easiest shot there is.
# Off-frontal, full-body and real-scene behaviour is UNMEASURED. Both previous
# generators collapsed exactly there (nano-banana 0.678 -> 0.562 full body;
# LoRA 0.742 -> 0.522/abstain). Run scripts/variety_test.py before trusting
# gpt-image-2 for anything but a close-up.
EDIT = "openai/gpt-image-2/edit"
TEXT2IMG = "fal-ai/gpt-image-2"

# Kept: nano-banana is still the best SCENE and realism model, and it exposes a
# separate system_prompt field where the iPhone-realism rules live. The intended
# split is identity first, scene second.
SCENE_EDIT = "fal-ai/nano-banana-pro/edit"
SCENE_TEXT2IMG = "fal-ai/nano-banana-pro"

# How many reference images one shot may spend. @image1 (face) and @image2
# (outfit, or her build when no outfit is chosen) are the two that earn a slot;
# every reference after them measurably dilutes identity rather than reinforcing
# it. Measured here 2026-08-02 on shots at a matched 400-600px face size: 2 refs
# 0.622 (n=54) vs 3 refs 0.579 (n=23). FINDINGS saw it harder — three face crops
# 0.547 against one crop's 0.811. Raise this only with a measurement in hand.
REF_BUDGET = 2

# --------------------------------------------------------------------------
# How a finished image is ARCHIVED.
# --------------------------------------------------------------------------
# fal returns 4K PNG: ~25 MB per shot, 6.5 GB for 360 of them, and a migration
# that has to move it. WebP q90 is ~2 MB — 12x smaller.
#
# Measured 2026-08-02 on the six largest generated images with faces, re-encoded
# and re-scored against the real gallery:
#
#   webp-lossless  69% of size   worst delta +0.0000   mean +0.0000
#   webp q95       14%           worst      +0.0052    mean +0.0006
#   webp q90        8%           worst      +0.0104    mean +0.0002
#   webp q85        6%           worst      -0.0133    mean +0.0001
#
# NO verdict flipped at any setting and face size moved at most 1px. The shifts
# scatter both directions around zero — noise, not degradation.
#
# This applies ONLY to generated output. A REFERENCE is different in kind: it is
# read by ArcFace as ground truth and its quality propagates into every image she
# appears in, so refs/ and bodies/ stay lossless. Measured on references, lossy
# cost a real and consistent embedding shift (mean self-similarity 0.985, worst
# 0.969), where lossless was exactly 1.0000.
#
# Set ARCHIVE_QUALITY = 0 to keep the original PNG.
ARCHIVE_FORMAT = "webp"
ARCHIVE_QUALITY = 90

# Endpoints take different arguments and silently ignore foreign ones, which is
# worse than erroring — you get a 1024px image while believing you asked for 4K.
# generate() keys off this rather than guessing.
#
# ⚠ TEXT2IMG's id must be listed here VERBATIM. It was missing — the set had
# "openai/gpt-image-2" while TEXT2IMG is "fal-ai/gpt-image-2" — and the first
# thing that ever routed to it (character creation) hit exactly the failure this
# comment describes: build_args took the nano branch, sent aspect_ratio="3:4" and
# resolution="4K" to an endpoint that ignores both, and returned a 1024x768
# LANDSCAPE master face with a 306px subject, under gate.FACE_PLATEAU_PX. The
# run row recorded aspect 3:4 / 4K, so nothing looked wrong. Any endpoint added
# to EDIT/TEXT2IMG belongs in this set on the same commit.
GPT_IMAGE = {"openai/gpt-image-2/edit", "openai/gpt-image-2", "fal-ai/gpt-image-2",
             "fal-ai/gpt-image-1/edit-image", "fal-ai/gpt-image-1/text-to-image"}

# gpt-image-2 takes image_size as an OBJECT (gpt-image-1 wants an enum string —
# same family, different schema). Omit it and you get a square default: measured
# a 121px face, under the gate's 160px floor, on a shot that scored 0.800 and
# still had to abstain. The number looked fine and meant nothing.
#
# Portrait, because framing is an identity setting — a taller canvas spends more
# pixels on her face.
GPT_IMAGE_SIZE = {"width": 1024, "height": 1536}

# 4K because the gate needs face pixels. At 2K a full-body face lands under the
# 160px abstain floor and the gate reports "I can't tell" on exactly the shots
# that most need checking. Applies to nano-banana; gpt-image sizes itself.
RESOLUTION = "4K"


# WHO RENDERS. All three resell Google's nano-banana-pro, so the picture is the
# same and the bill is not. Measured 2026-08-11 on one prompt with three
# references at 4K, scored on her own gallery — provider was the only variable:
#
#     fal    0.4304   $0.30            66s
#     kie    0.4267   $0.12 (24 cr)   220s
#     poyo   0.4426   $0.175 (35 cr)  265s
#
# 0.016 of spread, against seed-to-seed variance of 0.12-0.63 on identical
# prompts — the same picture for 40% of the money. poyo's advertised $0.070 was
# $0.175 once the task record was actually read, which is why this says kie.
#
# fal stays the fallback and stays reachable per-call: it is 3x faster, and a
# second provider is only an asset while the first still works. Override with
# THROUGHLINE_PROVIDER=fal, or per call via generate(provider=...).
PROVIDER = os.environ.get("THROUGHLINE_PROVIDER", "kie").strip().lower()
