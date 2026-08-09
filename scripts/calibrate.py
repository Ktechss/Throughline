"""Derive the threshold from every verified FRONTAL face of her we have.

    .venv-win\\Scripts\\python.exe scripts\\calibrate.py [--apply]

## Why frontal-only

Pairwise similarity across mixed poses measures head angle, not identity
(corr(|yaw|,sim) = -0.761). A threshold calibrated on pooled poses is a
threshold calibrated on yaw. Frontal-against-frontal is the only comparison
that isolates the thing we want to threshold.

## What the spread actually captures

The frontals span different makeup looks, different lighting setups, different
lenses and different generation runs — all the same woman. So the distribution
is "how much does she vary while still being her, on this pipeline". That is
precisely the question a threshold answers, and it is why a number from a forum
does not transfer: ArcFace thresholds tuned on real photographs do not describe
generated ones.

## The trap this script refuses to walk into

mean - 2*sigma answers "is this a STRANGER?" — a floor, not a quality bar. The
previous project shipped an image at 0.450 that cleared its 0.431 stranger
threshold and read as a different woman to the eye. So this reports both, and
recommends the stranger floor only as a floor.
"""
from __future__ import annotations

import argparse
import itertools
import json
import statistics as stats
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, ingest                          # noqa: E402
from backend.config import THRESHOLD_PATH             # noqa: E402
from backend.gate import analyze, similarity                # noqa: E402

INBOX = Path("data/inbox")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sigma", type=float, default=2.0)
    args = ap.parse_args()

    faces = []
    for src in sorted(INBOX.glob("*.png")) + [config.bio_face()]:
        for p in ingest.detect(src):
            if p.bucket != "front" or not p.usable:
                continue
            try:
                c = ingest.crop(src, p, Path("data/.calib"))
            except ingest.CropFailed:
                continue
            faces.append((f"{src.name}", analyze(c)))

    if len(faces) < 5:
        print(f"only {len(faces)} usable frontals — need >=5")
        return 1

    print(f"{len(faces)} verified frontal faces:")
    for n, f in faces:
        print(f"  {n:<42} yaw {f.yaw:>+5.1f}  {f.width:>3}px")

    sims = [similarity(a.vector, b.vector) for (_, a), (_, b)
            in itertools.combinations(faces, 2)]
    mean, sd = stats.mean(sims), stats.pstdev(sims)
    floor = round(max(0.0, mean - args.sigma * sd), 3)

    print(f"\n{len(sims)} front-to-front pairs, all the same woman")
    print(f"  mean   {mean:.3f}")
    print(f"  stdev  {sd:.3f}")
    print(f"  min    {min(sims):.3f}      <- her own worst agreement with herself")
    print(f"  max    {max(sims):.3f}")
    print(f"\n  stranger floor (mean - {args.sigma}sd) = {floor}")
    print(f"  ^ a FLOOR, not a quality bar. Anything below this is very likely")
    print(f"    not her. Passing it only means 'not obviously a stranger'.")
    print(f"\n  Her own frontals agree at {mean:.3f} on average. Nothing generated")
    print(f"  should be expected to beat that — it is the practical ceiling.")

    result = {"threshold": floor, "mean": round(mean, 3), "std": round(sd, 3),
              "min": round(min(sims), 3), "max": round(max(sims), 3),
              "n_images": len(faces), "n_pairs": len(sims), "sigma": args.sigma,
              "pose": "front only", "sources": sorted({n for n, _ in faces}),
              "warning": "Stranger floor, not a quality bar. Her own frontals "
                         f"agree at {mean:.3f}; set quality bars against that."}
    if not args.apply:
        print("\nreport only — pass --apply to write threshold.json")
        return 0
    THRESHOLD_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(f"\nwritten -> {THRESHOLD_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
