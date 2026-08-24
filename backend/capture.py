"""Is this a PHOTOGRAPH? — a number, the way `gate` makes "is this her" a number.

The project's spine says identity is measured, never eyeballed. Photographic
realism was the one axis with no number at all: `gate.Verdict` reports
similarity, yaw, pitch, roll, face_px, pose_class and face count, and nothing
whatsoever about whether the image looks like it came out of a camera. So "this
looks AI" stayed a judgement call, made by a human, on every single image —
exactly the kind of step CLAUDE.md says to replace with a measurement.

This module is that measurement. It is deliberately NOT part of the gate:

  ⚠ A capture score is not an identity score and the two must never be summed.
    A perfect capture distance does not make a picture her, and 0.9 similarity
    does not make it a photograph. `verdict.capture` is a separate field for the
    same reason upscaled rows and video frames are quarantined — mixing a
    derived measurement into a corpus calibrated on something else is a
    measurement error, not extra information.


WHAT WAS TESTED, AND WHAT SURVIVED

Measured on 12 real runs from data/eve1.db on 2026-08-24, before any of this was
written, because a metric that has not been checked against real images is a
guess with a decimal point on it.

  face_frac        WORKS, WITH A CEILING. Bed selfie 0.113; car selfies
                   0.201-0.272; full-length mirror selfie 0.099. It separates
                   "photographed from across the room" from "held at arm's
                   length", which was the exact failure of run 15e2298957.

                   ⚠ It measures FRAMING, not VIEWPOINT, and the difference bit
                   immediately. Run 4930945a94 (seedream) scored 0.2166 — better
                   than the nano run it lost to on every other axis — while
                   putting the phone IN the frame with a RECORD overlay and her
                   reflection on its screen. A third camera three feet away
                   produces the same face fraction as a front camera at arm's
                   length. Nothing here can tell them apart; only looking can.

  edge_sharp       CANDIDATE. Gradient magnitude sampled only at edge pixels,
                   face against the top quarter of the frame. Bed selfie 2.04,
                   car-cabin selfies 0.71-1.49. Right direction, modest spread,
                   NOT yet trustworthy without a real-photo band.

  shadow_noise     NEEDS A BAND. Ranges 0.88-12.4 across runs and means nothing
                   without knowing what a real phone photo scores.

  clip_pct         NEEDS A BAND. Same.

  dof_ratio        DISCARDED. Laplacian variance of the face region over the
                   background scored the visibly shallow-focus bed shot LOWEST
                   (0.83), because smooth skin has low variance and rumpled
                   bedding has high variance. It measured how textured the
                   subject was, not how focused. Recorded here so nobody
                   re-derives it: the obvious formulation of the most obvious
                   metric does not work.

Everything is measured at a NORMALISED long edge. A 4K render and a 2K render
are not comparable per-pixel — upsampling halves the apparent noise — and the
first version of this analysis compared them directly and got nonsense.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

# Long edge every image is resampled to before anything is measured. Large
# enough to keep pore-scale detail, small enough that a 4K render and a 2K
# render are being asked the same question.
NORM_PX = 1600

# Fraction of the frame's width the face spans. Not a pass/fail — a reading.
# `gate.FACE_PLATEAU_PX` is the identity-side version of the same axis; this is
# the framing-side one, and unlike face_px it does not move when resolution does.
SELFIE_FACE_FRAC = 0.18     # at or above this, the framing is selfie-like
DISTANT_FACE_FRAC = 0.08    # at or below this, nobody was holding the phone


class NoFace(Exception):
    """No face, so the framing metrics have nothing to be relative to."""


@dataclass
class Capture:
    face_frac: float | None     # face width / frame width
    edge_sharp: float | None    # face edge sharpness / background edge sharpness
    shadow_noise: float         # high-pass std in the darkest 12% of the frame
    clip_pct: float             # % of pixels at or above 250
    norm_px: int = NORM_PX

    def dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in asdict(self).items()}

    @property
    def framing(self) -> str:
        """What the face fraction says about who took the picture."""
        if self.face_frac is None:
            return "no-face"
        if self.face_frac >= SELFIE_FACE_FRAC:
            return "arms-length"
        if self.face_frac <= DISTANT_FACE_FRAC:
            return "distant"
        return "mid"


def _edge_sharpness(g: np.ndarray, mask: np.ndarray) -> float | None:
    """Mean gradient magnitude at the region's OWN strongest edges.

    Gating on edges is what makes this independent of how textured a region is,
    which is precisely where the discarded Laplacian-variance ratio failed: a
    sharp edge has a steep gradient whether it sits on skin or on bedding, and
    a blurred one does not.
    """
    if not mask.any():
        return None
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, 3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, 3)
    mag = cv2.magnitude(gx, gy)
    inside = mag[mask]
    if inside.size < 500:
        return None
    edges = mask & (mag > np.percentile(inside, 90))
    sel = mag[edges]
    return float(np.mean(sel)) if sel.size >= 50 else None


def measure(path: str | Path, *, face_box: tuple[int, int, int, int] | None = None
            ) -> Capture:
    """Measure one image. `face_box` is (x1, y1, x2, y2) at native resolution.

    Pass the box in when the caller already has it — `gate.check` runs the
    detector anyway, and running insightface twice per image to learn something
    it already knows is a waste of several seconds per generation.
    """
    im = cv2.imread(str(path))
    if im is None:
        raise ValueError(f"not a readable image: {path}")

    if face_box is None:
        from . import gate
        face_box = gate.face_box(path)

    h0, w0 = im.shape[:2]
    scale = NORM_PX / max(h0, w0)
    im = cv2.resize(im, (max(1, int(w0 * scale)), max(1, int(h0 * scale))),
                    interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape

    face_frac = edge_sharp = None
    if face_box:
        x1, y1, x2, y2 = (max(0, int(v * scale)) for v in face_box)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 > x1 and y2 > y1:
            face_frac = (x2 - x1) / w
            fm = np.zeros(g.shape, bool)
            fm[y1:y2, x1:x2] = True
            # Background is the TOP QUARTER only. The rest of the frame is her
            # body, which sits at the same distance as her face — comparing a
            # face against a shoulder measures nothing about depth of field.
            bm = ~fm
            bm[int(h * 0.25):, :] = False
            fs, bs = _edge_sharpness(g, fm), _edge_sharpness(g, bm)
            if fs and bs and bs > 1e-6:
                edge_sharp = fs / bs

    hp = g - cv2.GaussianBlur(g, (0, 0), 1.2)
    shadow = hp[g <= np.percentile(g, 12)]
    noise = float(np.std(shadow)) if shadow.size else 0.0
    clip = float((g >= 250).mean() * 100)

    return Capture(face_frac=face_frac, edge_sharp=edge_sharp,
                   shadow_noise=round(noise, 3), clip_pct=round(clip, 3))


# ── the reference band ───────────────────────────────────────────────────────
#
# The gate needed a gallery before a similarity number meant anything. This
# needs the same: a handful of GENUINE phone photographs, which set what
# `shadow_noise` and `edge_sharp` look like when a real sensor made the picture.
#
# They need not be of anyone in particular — no identity is involved, nothing is
# embedded, and none of them are ever sent anywhere. Any real phone photo works.

BAND_KEYS = ("shadow_noise", "clip_pct", "edge_sharp")


def _band_path(cid: str | None):
    from . import config
    base = config.char_base(cid) if cid else config.DATA
    return base / "state" / "capture-band.json"


def calibrate(paths: list[Path], cid: str | None = None) -> dict:
    """Measure real photographs and store the range they occupy."""
    seen = [measure(p) for p in paths]
    if not seen:
        raise ValueError("no readable photographs to calibrate from")

    band: dict[str, dict] = {}
    for key in BAND_KEYS:
        vals = [v for v in (getattr(c, key) for c in seen) if v is not None]
        if not vals:
            continue
        a = np.array(vals, float)
        # 10th-90th percentile, not min-max: one atypical photo should widen the
        # band a little, not define it. Same spirit as the gate's sigma.
        band[key] = {"lo": round(float(np.percentile(a, 10)), 4),
                     "hi": round(float(np.percentile(a, 90)), 4),
                     "median": round(float(np.median(a)), 4)}

    out = {"n": len(seen), "norm_px": NORM_PX, "band": band}
    p = _band_path(cid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2) + "\n")
    return out


def load_band(cid: str | None = None) -> dict:
    p = _band_path(cid)
    return json.loads(p.read_text()) if p.exists() else {}


def distance(cap: Capture, cid: str | None = None) -> dict | None:
    """How far outside the real-photo band this image sits, per axis.

    0.0 means inside the band. Returns None when no band exists — an
    uncalibrated number is worse than no number, which is the lesson
    `gate.load_threshold`'s "Stranger floor, not a quality bar" warning records.
    """
    b = (load_band(cid) or {}).get("band") or {}
    if not b:
        return None

    out: dict[str, float] = {}
    for key, rng in b.items():
        v = getattr(cap, key, None)
        if v is None:
            continue
        span = max(rng["hi"] - rng["lo"], 1e-6)
        if v < rng["lo"]:
            out[key] = round((rng["lo"] - v) / span, 3)
        elif v > rng["hi"]:
            out[key] = round((v - rng["hi"]) / span, 3)
        else:
            out[key] = 0.0
    if not out:
        return None
    out["total"] = round(sum(out.values()), 3)
    return out
