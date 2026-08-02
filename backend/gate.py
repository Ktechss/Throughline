"""Identity as a number.

"Is this still her?" is a measurement, not a judgement. Every generated image is
embedded with ArcFace and scored against a reference gallery. Model-agnostic on
purpose: the generator is a swappable box in the middle.

## The source of truth

The gallery is built ONLY from `data/refs/` — the reference images a human
chose. **A generated image can never become a gallery entry.** That is not
fussiness: the previous project let its family of sheets drift until the
original namesake disagreed with ten of its own descendants at 0.739. Score
against your own output and the yardstick moves with the thing it is measuring;
drift becomes undetectable by construction because it is now the definition.

So: the reference is never scored. It is what everything else is scored against.

## Read this before you trust a score

**Similarity tracks head angle.** corr(|yaw|, sim) = -0.761. A true profile of
the same woman scores ~0.45 against a frontal reference. Three consequences the
code enforces rather than documents:

- Scoring is against the NEAREST gallery entry, never one canonical frontal.
  A single frontal reference measures "how frontal is this?" and reports it as
  "is this her?".
- If the ONLY entry is frontal, that fallback is unavailable — so when the
  candidate's yaw is too far from the matched entry's, the gate **abstains**
  rather than reporting a number it knows is measuring angle. `POSE_DELTA_MAX`
  is where that line sits. This is the single most expensive mistake this
  project has made, twice, and it is worth a false abstain to avoid.
- `Verdict` carries `yaw` and `face_px` and the UI shows them next to every
  score. A score read without its yaw is not evidence.

To gate profiles honestly you need a profile of HER in the gallery — a
human-verified reference at that angle, imported like any other. Not a
generated one.

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

from .config import GALLERY_META, GALLERY_PATH, THRESHOLD_PATH

_app: FaceAnalysis | None = None

# Below this, ArcFace has too little signal to make a claim either way.
MIN_FACE_PX = 160
# Below this the number ranks but does not adjudicate.
LOW_CONFIDENCE_PX = 320

# Where the face-size gradient stops paying. Measured on this project's own 207
# shots (2026-08-02): <250px 0.472, 250-400px 0.548, 400-600px 0.612, 600+ 0.608.
# The curve is steep up to here and flat after, so a face under 400px is losing
# identity to FRAMING, and a bigger face than this buys nothing back. This is the
# number that turns "reject, 0.55" into "reframe closer" instead of a shrug.
FACE_PLATEAU_PX = 400

# Max |candidate.yaw - entry.yaw| before the comparison stops being about
# identity. corr(|yaw|, sim) = -0.761, so beyond this the score is dominated by
# head angle and reporting it as identity is how you delete every profile of the
# real woman. 25 deg is judgement, not measurement — it is roughly where
# "frontal" ends. Tighten it if you can afford the yield.
POSE_DELTA_MAX = 25.0

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


# Head tilt (roll) beyond this reads as a deliberate lean rather than a level
# head. The reference Kiara.png sits at -11.3, and generations inherited and
# amplified it to -14 avg. Surfacing it is what turns "every photo is annoyingly
# tilted" from an invisible drift into a number you can act on.
ROLL_LEVEL_MAX = 8.0


@dataclass
class Face:
    vector: np.ndarray  # L2-normalised, 512-dim -> cosine == dot
    yaw: float
    pitch: float
    roll: float          # in-plane tilt; 0 = level, +/- = ear toward shoulder
    width: int

    @property
    def pose_class(self) -> str:
        a = abs(self.yaw)
        return "frontal" if a < 20 else "three_quarter" if a < 45 else "profile"

    @property
    def tilted(self) -> bool:
        return abs(self.roll) > ROLL_LEVEL_MAX


@dataclass
class Verdict:
    similarity: float
    matched: str
    threshold: float
    face: Face
    source_yaw: float | None = None   # yaw of the reference it was scored against
    faces_in_frame: int = 1           # >1 means the subject was CHOSEN from several

    @property
    def pose_delta(self) -> float | None:
        if self.source_yaw is None:
            return None
        return abs(self.face.yaw - self.source_yaw)

    @property
    def pose_mismatch(self) -> bool:
        """The candidate and the reference are at angles too different to
        compare. The number is real; it just isn't about identity."""
        d = self.pose_delta
        return d is not None and d > POSE_DELTA_MAX

    @property
    def abstained(self) -> bool:
        return self.face.width < MIN_FACE_PX or self.pose_mismatch

    @property
    def low_confidence(self) -> bool:
        return self.face.width < LOW_CONFIDENCE_PX

    @property
    def diagnosis(self) -> str:
        """For a REJECTED verdict: which known confound explains the number.

        A low score has two very different meanings — "the model drew someone
        else" and "you gave the gate a face it cannot read" — and they call for
        opposite actions (re-roll vs reframe). Every confound below is measured,
        so which one is present is derivable from `face_px` and `yaw` rather than
        argued about per image. `drift` is returned only when none of them
        applies: that is the one case where the number really is about identity.

        Empty for anything that was not rejected — there is nothing to explain.
        """
        if self.status != "rejected":
            return ""
        if self.face.width < FACE_PLATEAU_PX:
            return "small-face"
        if self.face.pose_class != "frontal":
            return "off-frontal"
        if self.face.tilted:
            return "tilted"
        return "drift"

    @property
    def reason(self) -> str:
        # Always say so when the subject was picked out of a crowd: the score is a
        # max over candidates, which flatters it slightly, and knowing WHICH face
        # was measured is part of reading the number at all.
        crowd = (f"{self.faces_in_frame} faces in frame — scored the one best "
                 f"matching the gallery ({self.face.width}px at yaw "
                 f"{self.face.yaw:+.1f}). " if self.faces_in_frame > 1 else "")
        return crowd + self._reason

    @property
    def _reason(self) -> str:
        if self.face.width < MIN_FACE_PX:
            return (f"face is {self.face.width}px, under the {MIN_FACE_PX}px floor — "
                    f"too little signal to make any claim")
        if self.pose_mismatch:
            return (f"reference is at yaw {self.source_yaw:+.1f}, this is at "
                    f"{self.face.yaw:+.1f} — {self.pose_delta:.0f} apart. Beyond "
                    f"{POSE_DELTA_MAX:.0f} the score measures head angle, not "
                    f"identity. Import a reference at this angle to judge it.")
        # A rejection with a confound in it is a framing note, not a verdict on
        # her. Say which, and say what to do about it — the whole point of
        # recording yaw and face_px next to the score.
        d = self.diagnosis
        if d == "small-face":
            return (f"face is {self.face.width}px, under the {FACE_PLATEAU_PX}px "
                    f"plateau — identity falls off with framing below this "
                    f"(measured: 0.55 at 250-400px vs 0.61 at 400-600px). Reframe "
                    f"closer before reading this as drift.")
        if d == "off-frontal":
            return (f"head is {abs(self.face.yaw):.0f} off-frontal "
                    f"({self.face.pose_class.replace('_', '-')}) and the threshold "
                    f"is flat — corr(|yaw|, sim) = -0.761, so this number is partly "
                    f"measuring angle. Judge it against a same-angle reference.")
        if d == "tilted":
            return (f"head is rolled {self.face.roll:+.0f}, past the "
                    f"{ROLL_LEVEL_MAX:.0f} level mark — a lean the references do "
                    f"not have costs similarity on its own.")
        if d == "drift":
            return (f"face is {self.face.width}px and near-frontal "
                    f"({self.face.yaw:+.1f}) — no framing confound to explain "
                    f"this. The model drew someone else; re-roll or fix the prompt.")
        return ""

    @property
    def status(self) -> str:
        if self.abstained:
            return "abstain"
        return "kept" if self.similarity >= self.threshold else "rejected"

    def dict(self) -> dict:
        return {"similarity": round(self.similarity, 4), "matched": self.matched,
                "threshold": self.threshold, "status": self.status,
                "yaw": round(self.face.yaw, 1), "pitch": round(self.face.pitch, 1),
                "roll": round(self.face.roll, 1), "tilted": self.face.tilted,
                "face_px": self.face.width, "pose_class": self.face.pose_class,
                "low_confidence": self.low_confidence,
                "source_yaw": None if self.source_yaw is None else round(self.source_yaw, 1),
                "pose_delta": None if self.pose_delta is None else round(self.pose_delta, 1),
                "pose_mismatch": self.pose_mismatch,
                "faces_in_frame": self.faces_in_frame,
                "diagnosis": self.diagnosis,
                "reason": self.reason}


def _wrap(f) -> Face:
    # insightface pose is [pitch, yaw, roll].
    return Face(vector=f.normed_embedding, pitch=float(f.pose[0]),
                yaw=float(f.pose[1]), roll=float(f.pose[2]),
                width=int(f.bbox[2] - f.bbox[0]))


def _detect(path: str | Path):
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"could not read image: {path}")
    faces = _get_app().get(img)
    if not faces:
        raise NoFaceFound(f"no face detected in {Path(path).name}")
    return faces


def analyze(path: str | Path) -> Face:
    """Embed the largest face. Largest is right for a REFERENCE: a curated
    reference is her, alone. For a generated image use `analyze_all` + the
    gallery — see `check`, where largest is exactly the wrong rule."""
    faces = _detect(path)
    return _wrap(max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1])))


def analyze_all(path: str | Path) -> list[Face]:
    """Every face in the image, largest first."""
    faces = _detect(path)
    faces.sort(key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]),
               reverse=True)
    return [_wrap(f) for f in faces]


def face_box(path: str | Path) -> tuple[int, int, int, int] | None:
    """Bounding box (x1, y1, x2, y2) of the largest face, or None if there is
    none. Used to crop the head off a wardrobe turnaround so the outfit reference
    carries no competing identity."""
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"could not read image: {path}")
    faces = _get_app().get(img)
    if not faces:
        return None
    f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    return tuple(int(v) for v in f.bbox)  # type: ignore[return-value]


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def load_gallery() -> dict[str, np.ndarray]:
    if not GALLERY_PATH.exists():
        return {}
    with np.load(GALLERY_PATH) as z:
        return {k: z[k] for k in z.files}


def load_meta() -> dict[str, dict]:
    """Per-entry yaw/face_px/source. Without the yaw we cannot tell whether a
    comparison is fair, and an unfair comparison reported as a verdict is the
    failure this whole module exists to prevent."""
    return json.loads(GALLERY_META.read_text()) if GALLERY_META.exists() else {}


def add_to_gallery(path: str | Path, name: str) -> Face:
    """Only ever call this on a REFERENCE a human chose — never on generated
    output.

    The gallery is the yardstick. Admit a generated image and the yardstick
    starts drifting along with the thing it measures, which makes drift
    undefinable rather than undetected. The previous project's namesake sheet
    ended up disagreeing with ten of its own descendants at 0.739 exactly this
    way. Enforced at the API layer, documented here.
    """
    face = analyze(path)
    g = load_gallery()
    g[name] = face.vector
    GALLERY_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez(GALLERY_PATH, **g)

    meta = load_meta()
    meta[name] = {"yaw": round(face.yaw, 2), "pitch": round(face.pitch, 2),
                  "face_px": face.width, "pose_class": face.pose_class,
                  "source": str(Path(path).name)}
    GALLERY_META.write_text(json.dumps(meta, indent=2) + "\n")
    return face


def remove_from_gallery(name: str) -> bool:
    """Drop ONE entry from the gallery (npz + meta) so a bad seed can be pulled
    without wiping the whole fingerprint. Returns False if the entry is absent.
    Only ever removes — never re-admits generated output."""
    g = load_gallery()
    meta = load_meta()
    if name not in g and name not in meta:
        return False
    g.pop(name, None)
    if g:
        np.savez(GALLERY_PATH, **g)
    else:
        Path(GALLERY_PATH).unlink(missing_ok=True)
    meta.pop(name, None)
    GALLERY_META.write_text(json.dumps(meta, indent=2) + "\n")
    return True


def load_threshold() -> float:
    if THRESHOLD_PATH.exists():
        return json.loads(THRESHOLD_PATH.read_text())["threshold"]
    return DEFAULT_THRESHOLD


def check(path: str | Path, threshold: float | None = None) -> Verdict:
    """Score against the POSE-MATCHED entry in the source of truth.

    ## Why nearest-by-pose and not nearest-by-similarity

    The obvious implementation picks the highest-scoring gallery entry. That is
    wrong twice over: it picks whichever reference flatters the candidate, and
    because similarity tracks head angle (corr(|yaw|,sim) = -0.761) the winner
    tends to be whichever entry happens to share the candidate's pose *by
    accident* — or, worse, a mismatched one that scored high anyway.

    Measured here: a shot at yaw +27.0 scored highest against the FRONT entry
    (-1.1) and was therefore judged 28 degrees out of pose and abstained — while
    a three_quarter_right entry sat at +25.6, a 1.4 degree delta and a perfectly
    fair comparison, unused. The multi-angle gallery exists precisely so that
    shot can be judged; choosing by similarity threw that away.

    So: choose the entry closest in yaw, then report what it scores. Fairness
    first, verdict second. If even the closest entry is too far, `Verdict`
    abstains — we genuinely cannot judge that pose and should say so rather than
    return a confident number about head angle.

    ## Which FACE, when there is more than one

    `analyze` takes the largest, which is right for a reference and wrong here.
    The moment anyone else is in shot — a friend, a passer-by, a face on a poster
    — the largest face is whoever stood closest to the lens, and scoring THEM
    against her gallery reports a stranger's 0.3 as her drift. So the subject is
    the face that best matches the gallery: "which of these is most likely her"
    is the question actually being asked. `faces_in_frame` is recorded because
    taking a max over several candidates flatters the score a little, and a
    number whose selection rule you can't see is the kind this module exists to
    prevent.
    """
    g = load_gallery()
    if not g:
        raise FileNotFoundError("gallery is empty — import an identity reference "
                                "and seed it from data/refs")
    meta = load_meta()
    posed = {n: meta[n]["yaw"] for n in g if n in meta and "yaw" in meta[n]}

    def score(face: Face) -> tuple[float, str, float | None]:
        """This face's fair score: pose-matched entry first, then similarity."""
        if posed:
            name = min(posed, key=lambda n: abs(posed[n] - face.yaw))
            return similarity(face.vector, g[name]), name, posed[name]
        # No recorded yaws (a hand-seeded gallery). Fall back to similarity and
        # report no source yaw, so the verdict cannot claim a fairness it has
        # not checked.
        name = max(g, key=lambda n: similarity(face.vector, g[n]))
        return similarity(face.vector, g[name]), name, None

    faces = analyze_all(path)
    face = max(faces, key=lambda f: score(f)[0]) if len(faces) > 1 else faces[0]
    sim, name, src_yaw = score(face)

    thr = threshold if threshold is not None else load_threshold()
    return Verdict(sim, name, thr, face, source_yaw=src_yaw,
                   faces_in_frame=len(faces))


def reset_gallery() -> None:
    """Wipe the gallery + meta so a calibration run can seed a fresh fingerprint.

    Used only at the START of a deliberate re-calibration — never mid-flight."""
    GALLERY_PATH.unlink(missing_ok=True)
    GALLERY_META.unlink(missing_ok=True)


def calibrate_from_gallery(sigma: float = 2.0) -> dict:
    """Derive the threshold from the CURRENT gallery's own vectors.

    The gallery, after a calibration pass, is the human-curated set of faces that
    ARE her on this pipeline. Their pairwise similarity is the same-person
    distribution; two sigma below its mean is the stranger floor. Same maths as
    calibrate(), but reads the stored vectors instead of re-analysing files.
    """
    g = load_gallery()
    vecs = list(g.values())
    if len(vecs) < 3:
        raise ValueError(f"need >=3 gallery faces to calibrate, have {len(vecs)}")
    sims = [similarity(a, b) for a, b in itertools.combinations(vecs, 2)]
    mean, std = float(np.mean(sims)), float(np.std(sims))
    result = {"threshold": round(max(0.0, mean - sigma * std), 3),
              "mean": round(mean, 3), "std": round(std, 3),
              "min": round(float(np.min(sims)), 3),
              "n_faces": len(vecs), "n_pairs": len(sims), "sigma": sigma,
              "warning": "Stranger floor, not a quality bar."}
    THRESHOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLD_PATH.write_text(json.dumps(result, indent=2) + "\n")
    return result


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
