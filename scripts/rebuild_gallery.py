"""Rebuild the gallery from the verified reference sheets in data/inbox.

    .venv-win\\Scripts\\python.exe scripts\\rebuild_gallery.py [--apply]

Without --apply this only reports. The gallery is the source of truth for every
verdict the project will ever make; it should not change as a side effect of
running a script to look at something.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import ingest                                    # noqa: E402
from backend.config import GALLERY_META, GALLERY_PATH, REFS   # noqa: E402
from backend.gate import add_to_gallery, analyze, similarity   # noqa: E402

INBOX = Path("data/inbox")
# Priority order: the sheet has the biggest faces (185-222px), so it wins any
# bucket it covers. The facial sheet fills the angles the sheet lacks.
SOURCES = ["Kiara-Sheet.png", "Kiara-Facial-Data.png", "Kiara-Body-Data.png"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write the gallery")
    args = ap.parse_args()

    chosen: dict[str, tuple[ingest.Panel, Path]] = {}
    print(f"{'source':<24} {'yaw':>7} {'pitch':>7} {'px':>5}  bucket / why not")
    print("-" * 86)
    for name in SOURCES:
        src = INBOX / name
        if not src.exists():
            continue
        for p in ingest.detect(src):
            tag = p.bucket if p.usable else f"— {p.rejected}"
            print(f"{name:<24} {p.yaw:>+7.1f} {p.pitch:>+7.1f} {p.face_px:>5}  {tag}")
            if not p.usable:
                continue
            # First source to claim a bucket keeps it; SOURCES is priority order.
            if p.bucket in chosen and chosen[p.bucket][0].source != name:
                continue
            if p.bucket not in chosen or p.face_px > chosen[p.bucket][0].face_px:
                chosen[p.bucket] = (p, ingest.crop(src, p, REFS / "gallery"))

    print(f"\n{len(chosen)} gallery entries selected:")
    for b, (p, path) in sorted(chosen.items()):
        print(f"  {b:<22} {p.source:<24} yaw {p.yaw:>+6.1f}  {p.face_px}px")

    # Sanity: entries must agree with each other where the comparison is fair.
    # Cross-angle pairs are yaw-contaminated and prove nothing, so this only
    # asserts that no entry is a STRANGER (below the ~0.326 ceiling).
    print("\npairwise (cross-angle: yaw-depressed by design, strangers only):")
    vecs = {b: analyze(path).vector for b, (_, path) in chosen.items()}
    worst = 1.0
    for a in sorted(vecs):
        row = "  ".join(f"{similarity(vecs[a], vecs[b]):.3f}" for b in sorted(vecs))
        print(f"  {a:<22} {row}")
        for b in vecs:
            if a != b:
                worst = min(worst, similarity(vecs[a], vecs[b]))
    print(f"  order: {', '.join(sorted(vecs))}")
    print(f"\n  worst cross-angle pair: {worst:.3f}", end="  ")
    print("(above the 0.326 stranger ceiling — no impostor)" if worst > 0.326
          else "⚠ BELOW the stranger ceiling — one of these is not her")

    if not args.apply:
        print("\nreport only — pass --apply to write the gallery")
        return 0

    GALLERY_PATH.unlink(missing_ok=True)
    GALLERY_META.unlink(missing_ok=True)
    for b, (_, path) in sorted(chosen.items()):
        f = add_to_gallery(path, b)
        print(f"  + {b:<22} yaw {f.yaw:>+6.1f}  {f.width}px")
    print(f"\ngallery rebuilt: {len(chosen)} entries -> {GALLERY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
