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
import sys
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


def get_active() -> str:
    global _active_id
    if _active_id is None:
        try:
            _active_id = json.loads(_ACTIVE_FILE.read_text())["id"]
        except Exception:  # noqa: BLE001 — missing/corrupt file -> the default
            _active_id = DEFAULT_CHARACTER
    return _active_id


def set_active(cid: str) -> None:
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
GPT_IMAGE = {"openai/gpt-image-2/edit", "openai/gpt-image-2",
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

# --------------------------------------------------------------------------
# Local generation — $0 per image, on the 8GB RTX 5070 (Blackwell, sm_120).
# --------------------------------------------------------------------------
# The torch/diffusers stack lives in a SEPARATE venv (.venv-gen) and runs as a
# subprocess — the web backend never imports torch. LOCAL_ENDPOINT is the
# sentinel generate() keys off to shell out instead of calling fal.
LOCAL_ENDPOINT = "local/sdxl-ip-adapter"
# The .venv-gen layout differs by OS: Windows puts the interpreter in
# Scripts/python.exe, POSIX in bin/python. Resolve it so the same code shells out
# correctly on Linux servers and Windows dev boxes.
_GEN_BIN, _GEN_PY = ("Scripts", "python.exe") if sys.platform == "win32" else ("bin", "python")
LOCAL_PY = ROOT / ".venv-gen" / _GEN_BIN / _GEN_PY
LOCAL_WORKER = ROOT / "local" / "generate_local.py"
