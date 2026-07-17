"""Build a LoRA training set from the verified reference sheets.

    .venv-win\\Scripts\\python.exe scripts\\build_lora_set.py [--apply]

## The captioning rule, which is the whole game

**Anything present in every image but left UNNAMED is absorbed into the trigger.**

That is the mechanism that makes `eve1sdx` mean *her* — and it runs in our favour
or against us depending entirely on what we name. Caption her face and the
trigger learns nothing (the words carry it instead). Leave the white background
uncaptioned across 40 studio panels and `eve1sdx` quietly comes to mean "her, in
a studio, under flat light", and every Hauz Khas sunset gets dragged back to a
cyclorama.

So: name the background and the light in every caption, never name her face.

## Framing and pose balance

The first LoRA on the previous project saw 9% full-body images and could only
ever shoot her close. Balance is reported below and is worth reading before
spending a training run.

## Why pitch/yaw variety is WELCOME here, unlike the gallery

The gallery rejects tilted heads because a yardstick must be comparable. A
training set wants the opposite: every angle she can be photographed from,
including the top-down and low-angle panels the gallery threw away. Different
job, opposite rule.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import ingest                                  # noqa: E402

INBOX = Path("data/inbox")
OUT = Path("data/lora")
ZIP = Path("data/lora-set.zip")

TRIGGER = "eve1sdx"

# Training images may be smaller than gallery entries: the trainer downscales to
# 1024 anyway, and a 110px face still carries learnable structure even though it
# cannot adjudicate identity.
MIN_TRAIN_PX = 100

# Per-sheet: what is CONSTANT in that sheet and therefore must be named, or it
# gets absorbed into the trigger. Written by reading each sheet, not guessed.
CONTEXT = {
    "face close-up.png": "plain pale grey studio background, soft even studio lighting",
    "Kiara-Sheet.png": "blurred city street background, soft natural daylight",
    "Kiara-Facial-Data.png": "blurred city street background, soft natural daylight",
    "Facial-Expression.png": "blurred neutral background, soft even lighting",
    "Makeup-Reference-Sheet.png": "plain neutral background, soft even studio lighting",
    "Lighting reference sheet.png": "plain neutral background",
    "camera and lens consistency sheet.png": "plain neutral background, soft even lighting",
    "Close and Distance shot.png": "plain white studio background, soft even studio lighting",
    "Kiara-Body-Data.png": "plain white studio background, flat even lighting",
    "Body proportion reference.png": "plain white studio background, flat even lighting",
}

POSE_WORDS = {
    "profile_left": "head in left profile",
    "three_quarter_left": "head turned three-quarters to her left",
    "front": "facing the camera",
    "three_quarter_right": "head turned three-quarters to her right",
    None: "head turned at an angle",
}


def pose_words(p: ingest.Panel) -> str:
    base = POSE_WORDS.get(p.bucket, POSE_WORDS[None])
    if p.pitch < -22:
        base += ", head tilted down, seen from above"
    elif p.pitch > 22:
        base += ", chin raised, seen from below"
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.apply:
        shutil.rmtree(OUT, ignore_errors=True)
        OUT.mkdir(parents=True, exist_ok=True)

    kept, skipped = [], 0
    for src in sorted(INBOX.glob("*.png")):
        ctx = CONTEXT.get(src.name)
        if ctx is None:
            print(f"  ⚠ {src.name}: no context written — skipped rather than let "
                  f"an unnamed constant leak into the trigger")
            continue
        for p in ingest.detect(src):
            if p.det < ingest.MIN_DET_SCORE or p.face_px < MIN_TRAIN_PX:
                skipped += 1
                continue
            if not args.apply:
                kept.append((src.name, p))
                continue
            try:
                crop = ingest.crop(src, p, OUT)
            except ingest.CropFailed:
                skipped += 1
                continue
            # Caption names ONLY what varies. Her face is never described — that
            # is what the trigger is for.
            caption = f"{TRIGGER}, {pose_words(p)}, {ctx}"
            crop.with_suffix(".txt").write_text(caption + "\n", encoding="utf-8")
            kept.append((src.name, p))

    print(f"\n{len(kept)} training images, {skipped} skipped\n")
    print("  pose balance:")
    for b in ("profile_left", "three_quarter_left", "front",
              "three_quarter_right", None):
        n = sum(1 for _, p in kept if p.bucket == b)
        print(f"    {str(b):<22} {n:>3}")
    big = sum(1 for _, p in kept if p.face_px >= 160)
    print(f"\n  face size:  {big} >=160px,  {len(kept)-big} smaller")
    print("  per sheet:")
    for s in sorted({s for s, _ in kept}):
        print(f"    {s:<42} {sum(1 for x, _ in kept if x == s):>3}")

    print(f"\n  ⚠ Every image here is a portrait against a plain or blurred")
    print(f"    background. Named in the captions, so it attaches to the words")
    print(f"    rather than to her — but this set teaches her FACE, not her")
    print(f"    world. Expect the LoRA to be weak at full-body and at scenes.")

    if not args.apply:
        print("\n  report only — pass --apply to write the set")
        return 0

    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.iterdir()):
            z.write(f, f.name)
    print(f"\n  -> {OUT}/  ({len(kept)} images + captions)")
    print(f"  -> {ZIP}  ({ZIP.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
