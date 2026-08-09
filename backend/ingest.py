"""Ingest a multi-view reference sheet into per-angle identity references.

## Why detect rather than crop on a grid

The sheets don't share a layout — one is 5 panels in 2 ragged rows, another is
14 in 3 rows of different widths. A grid crop would need hand-tuning per sheet
and would fail silently when it drifted, handing the gallery a half-face.

So: detect every face, read its ACTUAL yaw, and bucket by that. The panel label
("LEFT PROFILE") is a claim; the measured yaw is the fact. When they disagree,
the yaw wins — this is the same project that shipped a "profile" experiment that
was four frontal photos.

## Why a sheet at all

Panels resolved in ONE generation share one latent commitment to her bone
structure, so they cannot drift from each other. Four separately generated
angles are four rolls of the dice. Measured on the previous project: 0.854 for
sheets against 0.564 shot-by-shot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2

from .gate import _get_app

# Buckets by measured yaw. Wide and overlapping-free; a face that lands between
# two buckets is reported as unbucketed rather than forced into the nearer one.
BUCKETS: list[tuple[str, float, float]] = [
    ("profile_left", -100.0, -55.0),
    ("three_quarter_left", -55.0, -25.0),
    ("front", -15.0, 15.0),
    ("three_quarter_right", 25.0, 55.0),
    ("profile_right", 55.0, 100.0),
]

# Pitch is the same confound as yaw, on the other axis, and it is easy to miss
# because a top-down view is still yaw~0 and looks "frontal" to a bucket that
# only reads yaw.
#
# Measured on this project's own reference sheets: the TOP VIEW panels score
# 0.474 and 0.574 against true frontals OF THE SAME WOMAN, where the true
# frontals score 0.896 against each other. Filed as "front" they would have
# entered the gallery as frontal references and dragged every later verdict
# toward a face nobody is photographing.
#
# So a panel must be level as well as facing the right way.
PITCH_MAX = 20.0

# A gallery entry is the yardstick; it deserves more signal than a candidate.
# The body sheet's faces land at 24-35px and score 0.01-0.26 against everything
# including each other — pure noise, correctly excluded here rather than
# averaged in.
MIN_GALLERY_PX = 160

# Reference sheets contain detail crops — an eye, a mouth, a patch of skin — and
# the detector will happily hallucinate a face across one.
#
# Measured on 'face close-up.png': the EYES OPEN panel produced a 477px "frontal
# face" at det 0.58, where every real face on that sheet scored 0.78-0.88. It
# was the biggest "face" on the sheet, so biggest-wins would have made a crop of
# two eyeballs the primary frontal reference for the entire project.
#
# The det_score gap is wide and clean, so the guard is cheap.
MIN_DET_SCORE = 0.70

# Crop this much of the bbox's size as padding on every side. Generous on
# purpose: a tight crop loses the hairline and jaw, which is where resemblance
# actually lives, and ArcFace re-detects inside the crop anyway.
PAD = 0.9


@dataclass
class Panel:
    source: str
    bucket: str | None
    yaw: float
    pitch: float
    face_px: int
    box: tuple[int, int, int, int]
    det: float = 1.0       # detector confidence — low means "probably not a face"
    rejected: str = ""     # why this panel is not gallery material

    @property
    def usable(self) -> bool:
        return bool(self.bucket) and not self.rejected

    @property
    def name(self) -> str:
        return f"{Path(self.source).stem}__{self.bucket or 'unbucketed'}_{self.face_px}px"


def bucket_for(yaw: float, pitch: float) -> tuple[str | None, str]:
    """(bucket, rejection reason). Both axes, because both confound identity."""
    if abs(pitch) > PITCH_MAX:
        return None, (f"pitch {pitch:+.0f} exceeds +/-{PITCH_MAX:.0f} — a tilted "
                      f"head scores like a different woman")
    for name, lo, hi in BUCKETS:
        if lo <= yaw < hi:
            return name, ""
    return None, f"yaw {yaw:+.0f} falls between buckets"


def detect(path: Path) -> list[Panel]:
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"could not read {path}")
    h, w = img.shape[:2]
    out = []
    for f in _get_app().get(img):
        x1, y1, x2, y2 = (int(v) for v in f.bbox)
        yaw, pitch = float(f.pose[1]), float(f.pose[0])
        det = float(f.det_score)
        px = x2 - x1
        bucket, why = bucket_for(yaw, pitch)

        # Order matters: check what it IS before checking how it's posed. A
        # hallucinated face with a plausible yaw is the dangerous case.
        if det < MIN_DET_SCORE:
            bucket, why = None, (f"detector confidence {det:.2f} < {MIN_DET_SCORE} — "
                                 f"probably a detail crop, not a face")
        elif x1 < 0 or y1 < 0 or x2 > w or y2 > h:
            bucket, why = None, ("bounding box runs outside the image — a partial "
                                 "or hallucinated detection")
        elif bucket and px < MIN_GALLERY_PX:
            why = f"face {px}px is under the {MIN_GALLERY_PX}px gallery floor"

        out.append(Panel(source=path.name, bucket=bucket, yaw=yaw, pitch=pitch,
                         face_px=px, box=(x1, y1, x2, y2), det=det, rejected=why))
    return sorted(out, key=lambda p: p.yaw)


class CropFailed(Exception):
    """The crop could not be made to contain the intended face, alone."""


# How far the cropped face's yaw may sit from the panel we selected before we
# conclude we cropped a different face.
YAW_TOLERANCE = 8.0

# Padding is tried widest-first: generous framing keeps the hairline and jaw,
# which is where resemblance lives. But on a contact sheet, generous padding
# reaches into the next panel.
PAD_LADDER = (0.9, 0.6, 0.4, 0.25, 0.12)


def crop(path: Path, panel: Panel, dest_dir: Path) -> Path:
    """Write a crop that provably contains the face we chose — and only it.

    ## Why this verifies instead of just cropping

    `analyze()` takes the LARGEST face in an image. On a contact sheet, padding
    that spills into the neighbouring panel can catch a face bigger than the one
    we meant, and the gallery silently gets the wrong angle.

    Worse than "wrong panel": a face cut vertically by the crop edge reads to
    the detector as a PROFILE. Measured here on 'face close-up.png' — selecting
    the +26.0 three-quarter panel produced a crop whose largest face measured
    **-67.5**. Half of the neighbouring frontal, mistaken for a profile, filed
    as our right-three-quarter reference.

    So: crop, re-detect, and require the result to be the face we picked. Shrink
    the padding until it is, or refuse. A reference we cannot verify is worse
    than a missing one — the gallery is what every later verdict trusts.
    """
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    bx1, by1, bx2, by2 = panel.box
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{panel.name}.png"

    for pad in PAD_LADDER:
        px, py = int((bx2 - bx1) * pad), int((by2 - by1) * pad)
        x1, y1 = max(0, bx1 - px), max(0, by1 - py)
        x2, y2 = min(w, bx2 + px), min(h, by2 + py)
        patch = img[y1:y2, x1:x2]
        found = _get_app().get(patch)
        if not found:
            continue
        big = max(found, key=lambda f: f.bbox[2] - f.bbox[0])
        if abs(float(big.pose[1]) - panel.yaw) <= YAW_TOLERANCE:
            cv2.imwrite(str(dest), patch)
            return dest

    raise CropFailed(
        f"{panel.source} {panel.bucket} (yaw {panel.yaw:+.1f}): every padding "
        f"produced a crop whose largest face was not this one — panels are too "
        f"close together to isolate it"
    )


def best_per_bucket(panels: list[Panel]) -> dict[str, Panel]:
    """Biggest usable face wins within a bucket — more pixels, more signal."""
    out: dict[str, Panel] = {}
    for p in panels:
        if not p.usable:
            continue
        if p.bucket not in out or p.face_px > out[p.bucket].face_px:
            out[p.bucket] = p
    return out
