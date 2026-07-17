"""Paths and env. Single source of truth — nothing else builds a path by hand."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
IMAGES = DATA / "images"          # generated images
REFS = DATA / "refs"              # identity references — the face we're holding
POSES = DATA / "poses"            # saved skeletons
STATE = DATA / "state"            # part tree, gallery, threshold

GALLERY_PATH = STATE / "gallery.npz"
THRESHOLD_PATH = STATE / "threshold.json"
PARTS_PATH = STATE / "parts.json"
RUNS_PATH = STATE / "runs.json"

for d in (IMAGES, REFS, POSES, STATE):
    d.mkdir(parents=True, exist_ok=True)

# fal endpoints. Local inference is off the table — an 8GB laptop GPU cannot run
# FLUX.2 (32B) or klein 4B (~13GB).
TEXT2IMG = "fal-ai/nano-banana-pro"
EDIT = "fal-ai/nano-banana-pro/edit"

# 4K because the gate needs face pixels. At 2K a full-body face lands under the
# 160px abstain floor and the gate reports "I can't tell" on exactly the shots
# that most need checking.
RESOLUTION = "4K"
