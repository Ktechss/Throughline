"""Identity as a number.

"Is this still her?" is a measurement, not a judgement. Every generated image is
embedded with ArcFace and scored against a reference gallery. Model-agnostic on
purpose: the generator is a swappable box in the middle.

## Read this before you trust a score

**Similarity tracks head angle.** corr(|yaw|, sim) = -0.761. A true profile of
the same woman scores ~0.45 against a frontal reference. Two consequences the
code enforces rather than documents:

- Scoring is against the NEAREST gallery entry, never one canonical frontal.
  A single frontal reference measures "how frontal is this?" and reports it as
  "is this her?".
- `Verdict` carries `yaw` and `face_px` and the UI shows them next to every
  score. A score read without its yaw is not evidence.

**Face pixels are a gradient, not a cliff.** Below `MIN_FACE_PX` the gate
ABSTAINS — "I can't tell" and "this is not her" are different claims, and a gate
that reports the second when it means the first silently deletes every distance
shot. But 161px is not "fine": the same woman at 660px scored 0.635 and at 298px
scored 0.450, at the same yaw. So `confidence` is reported as a gradient too.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from .config import GALLERY_PATH, THRESHOLD_PATH

_app: FaceAnalysis | None = None

# Below this, ArcFace has too little signal to make a claim either way.
MIN_FACE_PX = 160
# Below this the number ranks but does not adjudicate.
LOW_CONFIDENCE_PX = 320

# Fallback only. Calibrate against a real curated set; never hand-guess.
# NOTE: the previous project's 0.431 was calibrated as "is this a stranger?" and
# was too permissive to gate quality on — a 0.450 shot read as a different woman.
DEFAULT_THRESHOLD = 0.55


def _get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        _app = FaceAnalysis(name="buffalo_l",
                            providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


class NoFaceFound(Exception):
    """No face detected. For a generated image this is itself a failure."""


@dataclass
class Face:
    vector: np.ndarray  # L2-normalised, 512-dim -> cosine == dot
    yaw: float
    pitch: float
    width: int

    @property
    def pose_class(self) -> str:
        a = abs(self.yaw)
        return "frontal" if a < 20 else "three_quarter" if a < 45 else "profile"


@dataclass
class Verdict:
    similarity: float
    matched: str
    threshold: float
    face: Face

    @property
    def abstained(self) -> bool:
        return self.face.width < MIN_FACE_PX

    @property
    def low_confidence(self) -> bool:
        return self.face.width < LOW_CONFIDENCE_PX

    @property
    def status(self) -> str:
        if self.abstained:
            return "abstain"
        return "kept" if self.similarity >= self.threshold else "rejected"

    def dict(self) -> dict:
        return {"similarity": round(self.similarity, 4), "matched": self.matched,
                "threshold": self.threshold, "status": self.status,
                "yaw": round(self.face.yaw, 1), "pitch": round(self.face.pitch, 1),
                "face_px": self.face.width, "pose_class": self.face.pose_class,
                "low_confidence": self.low_confidence}


def analyze(path: str | Path) -> Face:
    """Embed the largest face. Largest is right: she is always the subject."""
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"could not read image: {path}")
    faces = _get_app().get(img)
    if not faces:
        raise NoFaceFound(f"no face detected in {Path(path).name}")
    f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    return Face(vector=f.normed_embedding, yaw=float(f.pose[1]),
                pitch=float(f.pose[0]), width=int(f.bbox[2] - f.bbox[0]))


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def load_gallery() -> dict[str, np.ndarray]:
    if not GALLERY_PATH.exists():
        return {}
    with np.load(GALLERY_PATH) as z:
        return {k: z[k] for k in z.files}


def add_to_gallery(path: str | Path, name: str) -> Face:
    """Only ever call this on an image a human has confirmed is her.

    The gallery is the ground truth everything else trusts; a wrong entry
    silently widens the character to include someone else.
    """
    face = analyze(path)
    g = load_gallery()
    g[name] = face.vector
    GALLERY_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez(GALLERY_PATH, **g)
    return face


def load_threshold() -> float:
    if THRESHOLD_PATH.exists():
        return json.loads(THRESHOLD_PATH.read_text())["threshold"]
    return DEFAULT_THRESHOLD


def check(path: str | Path, threshold: float | None = None) -> Verdict:
    """Score against the NEAREST gallery entry — never a canonical frontal."""
    g = load_gallery()
    if not g:
        raise FileNotFoundError("gallery is empty — mark an approved image as a "
                                "reference view first")
    face = analyze(path)
    scores = {n: similarity(face.vector, v) for n, v in g.items()}
    name = max(scores, key=scores.get)
    thr = threshold if threshold is not None else load_threshold()
    return Verdict(scores[name], name, thr, face)


def calibrate(paths: list[Path], sigma: float = 2.0) -> dict:
    """Derive a threshold from images that are all, by construction, her.

    Their pairwise distribution IS the same-person distribution for this
    character on this pipeline. Two standard deviations below its mean beats a
    number from a forum — ArcFace thresholds tuned on real photographs do not
    transfer to generated ones.

    ⚠ This answers "is this a stranger?", which is a LOWER bar than "is this
    good?". The previous project shipped a 0.450 image that cleared its
    stranger threshold and read as someone else. Use this as a floor, and set
    quality floors per-pose well above it.
    """
    vecs = []
    for p in paths:
        try:
            vecs.append(analyze(p).vector)
        except (NoFaceFound, ValueError):
            continue
    if len(vecs) < 5:
        raise ValueError(f"need >=5 usable images to calibrate, got {len(vecs)}")
    sims = [similarity(a, b) for a, b in itertools.combinations(vecs, 2)]
    mean, std = float(np.mean(sims)), float(np.std(sims))
    result = {"threshold": round(max(0.0, mean - sigma * std), 3),
              "mean": round(mean, 3), "std": round(std, 3),
              "min": round(float(np.min(sims)), 3),
              "n_images": len(vecs), "n_pairs": len(sims), "sigma": sigma,
              "warning": "This is a stranger threshold, not a quality bar."}
    THRESHOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLD_PATH.write_text(json.dumps(result, indent=2) + "\n")
    return result
