"""Paths and env. Single source of truth — nothing else builds a path by hand."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
IMAGES = DATA / "images"          # generated images
REFS = DATA / "refs"              # identity references — the face we're holding
WARDROBE = DATA / "wardrobe"      # outfit reference images (@image2 per shot)
POSE_REFS = DATA / "pose-refs"    # pose reference images of HER (keyword-selected)
POSES = DATA / "poses"            # saved skeletons
STATE = DATA / "state"            # part tree, gallery, threshold

GALLERY_PATH = STATE / "gallery.npz"
GALLERY_META = STATE / "gallery.json"   # per-entry yaw/face_px — needed to know
                                        # whether a comparison is even fair
THRESHOLD_PATH = STATE / "threshold.json"
PARTS_PATH = STATE / "parts.json"
RUNS_PATH = STATE / "runs.json"

for d in (IMAGES, REFS, WARDROBE, POSE_REFS, POSES, STATE):
    d.mkdir(parents=True, exist_ok=True)

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
# The project long assumed local inference was impossible here. It is not:
# torch 2.11+cu128 runs on this card, and SDXL fits with model CPU offload.
# gpt-image-2 (0.813) still leads on quality; this trades quality for zero
# marginal cost. The gate scores both the same way, so the trade is measured.
#
# The torch/diffusers stack lives in a SEPARATE venv (.venv-gen) and runs as a
# subprocess — the web backend never imports torch. LOCAL_ENDPOINT is the
# sentinel generate() keys off to shell out instead of calling fal.
LOCAL_ENDPOINT = "local/sdxl-ip-adapter"
LOCAL_PY = ROOT / ".venv-gen" / "Scripts" / "python.exe"
LOCAL_WORKER = ROOT / "local" / "generate_local.py"
