"""Give the capture metrics an absolute meaning, from real photographs.

`backend/capture.py` measures four things about an image — how much of the frame
her face fills, how sharp the background is against her, how much noise sits in
the shadows, how much of the highlight range is clipped. Two of those are
readable on their own: `face_frac` is geometry, and it already separates "held
at arm's length" from "photographed from across the room".

The other two are not. `shadow_noise` of 2.8 and `clip_pct` of 1.1 are numbers
without a scale. They can tell you image A differs from image B; they cannot
tell you whether either looks like it came out of a camera. That needs a
reference band, exactly as a similarity score needed a gallery before it meant
anything.

WHAT TO POINT THIS AT

Real photographs taken on a phone. Nothing else works:

  - they need not be of anyone in particular, or of a person at all
  - nothing is embedded, nothing is uploaded, nothing leaves the machine
  - a spread is better than a set — indoors and out, day and night, some badly
    lit. The band is meant to describe what a camera does, not what a good
    photograph looks like.
  - 20 or more gives a usable 10th-90th percentile; 8 is the floor

⚠ NEVER CALIBRATE ON GENERATED IMAGES. The whole point of the band is to say how
far our output sits from a real capture. Building it from our own output makes
that distance zero by construction — the measurement would agree with itself
forever and report nothing. This script checks EXIF for a camera make or model
and refuses anything without one, which is a blunt test that a screenshot fails
and a phone photo passes.

    ./.venv/bin/python scripts/calibrate_capture.py ~/Pictures/camera-roll
    ./.venv/bin/python scripts/calibrate_capture.py <dir> --allow-no-exif   # opt out
"""
import argparse
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

from backend import capture                                   # noqa: E402

SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"}
MIN_PHOTOS = 8


def has_camera_exif(p: Path) -> bool:
    """True when the file carries a camera make or model.

    Tags 271 and 272 are Make and Model. A phone photo has them; a screenshot,
    a download and every image this pipeline generates do not.
    """
    try:
        from PIL import Image
        with Image.open(p) as im:
            exif = im.getexif() or {}
        return bool(exif.get(271) or exif.get(272))
    except Exception:                              # noqa: BLE001 — unreadable is not real
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--allow-no-exif", action="store_true",
                    help="accept files with no camera metadata. Only for photos you "
                         "know were captured and have been stripped or re-encoded.")
    ap.add_argument("--character", default=None,
                    help="store the band against one character instead of globally")
    args = ap.parse_args()

    if not args.folder.is_dir():
        print(f"not a directory: {args.folder}", file=sys.stderr)
        return 2

    found = sorted(p for p in args.folder.rglob("*") if p.suffix.lower() in SUFFIXES)
    if not found:
        print(f"no images under {args.folder}", file=sys.stderr)
        return 2

    if args.allow_no_exif:
        photos, skipped = found, []
    else:
        photos = [p for p in found if has_camera_exif(p)]
        skipped = [p for p in found if p not in set(photos)]

    print(f"{len(found)} files, {len(photos)} with camera metadata")
    if skipped:
        print(f"  skipped {len(skipped)} without it "
              f"(screenshots, downloads, and anything generated):")
        for p in skipped[:5]:
            print(f"    {p.name}")
        if len(skipped) > 5:
            print(f"    ... and {len(skipped) - 5} more")
        print("  pass --allow-no-exif to include them, but read the warning first")

    if len(photos) < MIN_PHOTOS:
        print(f"\nneed at least {MIN_PHOTOS} real photographs, have {len(photos)}. "
              f"A band from fewer describes those photos, not phone cameras.",
              file=sys.stderr)
        return 1

    print(f"\nmeasuring {len(photos)} photographs at a {capture.NORM_PX}px long edge...")
    band = capture.calibrate(photos, args.character)

    print(f"\nband stored — {band['n']} photographs\n")
    print(f"  {'metric':16s} {'10th':>8s} {'median':>8s} {'90th':>8s}")
    for k, v in (band.get("band") or {}).items():
        print(f"  {k:16s} {v['lo']:8.3f} {v['median']:8.3f} {v['hi']:8.3f}")

    print("\nEvery generation from here reports `verdict.capture.distance` — how far "
          "outside this band it sits, per axis, 0.0 meaning inside.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
