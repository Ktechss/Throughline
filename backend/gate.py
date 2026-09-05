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

import io
import threading

from . import config
from .config import GALLERY_META, GALLERY_PATH, THRESHOLD_PATH

_app: FaceAnalysis | None = None
# insightface's FaceAnalysis is built lazily and _parallel runs four generation
# threads: two can both see `None`, both construct it, and on a cold machine
# both DOWNLOAD buffalo_l into the same path, which can leave a corrupt archive.
_APP_LOCK = threading.Lock()

# The gallery is read-modify-written by add/remove, and `def` endpoints run in
# Starlette's threadpool, so two concurrent /api/gallery/add genuinely race and
# one entry is simply lost. One lock covers both files as a unit.
_GALLERY_LOCK = threading.RLock()


def _write_gallery(g: dict) -> None:
    """np.savez, atomically. It truncates the target before writing, and this
    file is the yardstick with no backup — see config.write_atomic."""
    buf = io.BytesIO()
    np.savez(buf, **g)
    config.write_atomic(GALLERY_PATH, buf.getvalue())


def _write_meta(meta: dict) -> None:
    config.write_json_atomic(GALLERY_META, meta)

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
    if _app is None:                       # fast path, no lock once built
        with _APP_LOCK:
            if _app is None:               # re-check: another thread may have won
                app = FaceAnalysis(
                    name="buffalo_l",
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
                app.prepare(ctx_id=0, det_size=(640, 640))
                _app = app                 # publish only once fully prepared
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
    def confounds(self) -> list[str]:
        """EVERY known confound present, worst first — not just the first one.

        A low score has two very different meanings — "the model drew someone
        else" and "you gave the gate a face it cannot read" — and they call for
        opposite actions (re-roll vs reframe). Each entry below is measured, so
        which are present is derivable from `face_px`, `yaw` and `roll` rather
        than argued about per image.

        Reporting only the first is how the compounding gets hidden, and the
        compounding is the whole point: FINDINGS' stadium result is four
        confounds stacking to cost 0.267, which is larger than the gap between
        any two generators tested. A shot at 301px AND 34 off-frontal AND rolled
        12 has three things wrong with it and needs three fixes; being told
        "small-face" and stopping sends you to fix one and re-roll into the same
        number.
        """
        if self.status != "rejected":
            return []
        out = []
        if self.face.width < FACE_PLATEAU_PX:
            out.append("small-face")
        if self.face.pose_class != "frontal":
            out.append("off-frontal")
        if self.face.tilted:
            out.append("tilted")
        return out or ["drift"]

    @property
    def crowd(self) -> bool:
        """More than one face in frame, so the score is a MAX over candidates.

        Not a confound — a confound depresses a score and this inflates one,
        which is why it needs saying separately and why it must be said on a
        KEPT shot too. `confounds` deliberately returns nothing unless the
        verdict is rejected, so until now the dangerous case was the silent one:
        measured over 613 runs, 26 were scored out of a crowd and **7 of those
        were kept with an empty diagnosis** — 0.6435 chosen from four faces,
        0.635 from six. Nothing in the row said the number was a maximum.
        """
        return self.faces_in_frame > 1

    @property
    def diagnosis(self) -> str:
        """Everything needed to read this number, as one tag.

        "crowd+small-face", "off-frontal+tilted", "drift" when nothing explains
        the score but her, or "crowd" alone on a kept shot picked out of several
        faces. The crowd tag leads because it changes what the number MEANS
        rather than merely why it is low.
        """
        tags = (["crowd"] if self.crowd else []) + self.confounds
        return "+".join(tags)

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
        # A rejection with confounds in it is a framing note, not a verdict on
        # her. Say which — ALL of them — and what to do about each. Stacking is
        # the thing worth seeing: three of these together is a different problem
        # from any one of them, and a different amount of score to win back.
        say = {
            "small-face": (f"face is {self.face.width}px, under the "
                           f"{FACE_PLATEAU_PX}px plateau — identity falls off with "
                           f"framing below this (measured: 0.55 at 250-400px vs "
                           f"0.61 at 400-600px), so reframe closer"),
            "off-frontal": (f"head is {abs(self.face.yaw):.0f} off-frontal "
                            f"({self.face.pose_class.replace('_', '-')}) against a "
                            f"flat threshold — corr(|yaw|, sim) = -0.761, so the "
                            f"number is partly measuring angle"),
            "tilted": (f"head is rolled {self.face.roll:+.0f}, past the "
                       f"{ROLL_LEVEL_MAX:.0f} level mark — measured here at a mean "
                       f"0.521 tilted vs 0.608 level, about 0.09 on its own"),
            "drift": (f"face is {self.face.width}px and near-frontal "
                      f"({self.face.yaw:+.1f}) with a level head — no framing "
                      f"confound explains this. The model drew someone else; "
                      f"re-roll or fix the prompt"),
        }
        found = self.confounds
        if not found:
            return ""
        parts = [say[c] for c in found if c in say]
        if len(parts) == 1:
            return parts[0][0].upper() + parts[0][1:] + "."
        # Plural: lead with the count, because "three things are wrong" is the
        # actionable fact and any one of them read alone understates the fix.
        head = (f"{len(parts)} confounds stacked, which compound — FINDINGS "
                f"measured four of them costing 0.267 together. ")
        return head + "; ".join(parts) + "."

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
                "faces_in_frame": self.faces_in_frame, "crowd": self.crowd,
                "diagnosis": self.diagnosis, "confounds": self.confounds,
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


# Every loader below takes an optional character. Without one they resolve
# through CharPath to whoever is ACTIVE, which is right for a single-subject
# shot and impossible for a photograph with two people in it — scoring the second
# woman means reading a gallery that is not the active one. Same shape as
# db.runs_all(character_id=...) and the wardrobe helpers.
def _state(name: str, cid: str | None):
    from . import config
    return config.char_base(cid) / "state" / name if cid else None


def load_gallery(cid: str | None = None) -> dict[str, np.ndarray]:
    path = _state("gallery.npz", cid) or GALLERY_PATH
    if not path.exists():
        return {}
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def load_meta(cid: str | None = None) -> dict[str, dict]:
    """Per-entry yaw/face_px/source. Without the yaw we cannot tell whether a
    comparison is fair, and an unfair comparison reported as a verdict is the
    failure this whole module exists to prevent."""
    path = _state("gallery.json", cid) or GALLERY_META
    return json.loads(path.read_text()) if path.exists() else {}


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
    with _GALLERY_LOCK:
        g = load_gallery()
        g[name] = face.vector
        meta = load_meta()
        meta[name] = {"yaw": round(face.yaw, 2), "pitch": round(face.pitch, 2),
                      "face_px": face.width, "pose_class": face.pose_class,
                      "source": str(Path(path).name)}
        # META FIRST, then the vectors. The pair is two files and cannot be made
        # one transaction, so order it by which half-state is survivable: meta
        # naming an entry the npz lacks is invisible (nothing iterates meta), a
        # vector whose yaw is unknown is not — it silently demotes _scorer to
        # nearest-by-similarity and the verdicts keep looking confident.
        _write_meta(meta)
        _write_gallery(g)
    return face


def remove_from_gallery(name: str) -> bool:
    """Drop ONE entry from the gallery (npz + meta) so a bad seed can be pulled
    without wiping the whole fingerprint. Returns False if the entry is absent.
    Only ever removes — never re-admits generated output."""
    with _GALLERY_LOCK:
        g = load_gallery()
        meta = load_meta()
        if name not in g and name not in meta:
            return False
        g.pop(name, None)
        meta.pop(name, None)
        # Vectors first on the way OUT, for the same reason meta goes first on
        # the way in: the survivable half-state is always "meta knows about an
        # entry the npz does not".
        if g:
            _write_gallery(g)
        else:
            Path(GALLERY_PATH).unlink(missing_ok=True)
        _write_meta(meta)
    return True


def load_threshold(cid: str | None = None) -> float:
    path = _state("threshold.json", cid) or THRESHOLD_PATH
    if path.exists():
        return json.loads(path.read_text())["threshold"]
    return DEFAULT_THRESHOLD


@dataclass
class CastMember:
    """One person's verdict inside a group photograph."""
    character: str
    verdict: Verdict | None          # None when she was not found at all

    @property
    def found(self) -> bool:
        return self.verdict is not None


@dataclass
class CastVerdict:
    """"Is this still her?" asked of a photograph with more than one person in it.

    Per-person similarity is necessary and NOT sufficient. Two face references in
    one prompt routinely produce two women who resemble each other, or the same
    woman twice — and in both cases each face can score perfectly well against
    its own gallery. What catches it is how the two faces score against EACH
    OTHER.

    That number needs no new constant. Measured on this data:

        same person, different angles        0.657 - 0.710
        stranger floor (own, calibrated)     0.540 - 0.580
        DIFFERENT characters, face to face   0.250 - 0.404

    So `blended` is simply: the two faces score against each other at or above a
    stranger floor — the point at which this very gate would call them the same
    person. min() of the floors, because reporting is cheap and a missed blend is
    not.

    ⚠ The separation is real but NARROWER than it looks from a stranger photo.
    An unrelated face scores about -0.06 here, and it is tempting to reason from
    that. Two of THIS project's characters do not: they are written from one bio
    template and generated by one model, so kiara-vs-alexa sits at 0.404 against
    a 0.564 floor — a margin of 0.16, not 0.6. Two characters written to resemble
    each other (sisters, say) could close it and read as blended when they are
    merely alike. If that happens the answer is a per-pair floor measured from
    their own references, not a hand-tuned constant.
    """
    members: list[CastMember]
    distinctness: float | None       # highest face-to-face similarity in frame
    blend_floor: float | None        # the floor it was judged against
    faces_in_frame: int

    @property
    def blended(self) -> bool:
        return (self.distinctness is not None and self.blend_floor is not None
                and self.distinctness >= self.blend_floor)

    @property
    def missing(self) -> list[str]:
        return [m.character for m in self.members if not m.found]

    @property
    def status(self) -> str:
        """Reported, never blocking — the same contract as the framing confounds.

        A collaboration is `kept` when every member was found and cleared her own
        threshold. Blending and a missing member are named in `confounds` so they
        sit beside the number rather than replacing it.
        """
        if self.missing:
            return "rejected"
        states = [m.verdict.status for m in self.members if m.verdict]
        if any(s == "abstain" for s in states):
            return "abstain"
        return "kept" if all(s == "kept" for s in states) else "rejected"

    @property
    def confounds(self) -> list[str]:
        out = []
        if self.blended:
            out.append("blended")
        for m in self.members:
            if not m.found:
                out.append(f"missing:{m.character}")
            elif m.verdict.status == "rejected":
                out += [f"{m.character}:{c}" for c in m.verdict.confounds]
        return out

    def dict(self) -> dict:
        return {
            "status": self.status,
            "cast": [{"character": m.character,
                      **(m.verdict.dict() if m.verdict else {"status": "missing"})}
                     for m in self.members],
            "distinctness": None if self.distinctness is None else round(self.distinctness, 4),
            "blend_floor": self.blend_floor,
            "blended": self.blended,
            "faces_in_frame": self.faces_in_frame,
            "confounds": self.confounds,
            "diagnosis": "+".join(self.confounds),
            "reason": self._reason(),
        }

    def _reason(self) -> str:
        bits = []
        if self.blended:
            bits.append(
                f"the two faces score {self.distinctness:.3f} against EACH OTHER, "
                f"at or above the {self.blend_floor} stranger floor — this gate "
                f"would call them the same person, so they have blended")
        for m in self.members:
            if not m.found:
                bits.append(f"{m.character} is not in the frame at all")
        for m in self.members:
            if m.found and m.verdict.status == "rejected":
                bits.append(f"{m.character}: {m.verdict.reason}")
        return " ".join(bits)


def check_cast(path: str | Path, cast: list[str]) -> CastVerdict:
    """Score a photograph containing several named characters.

    Each face is scored against every character's OWN gallery, by the same
    pose-matched rule a solo shot uses, and then assigned one-to-one: the best
    total assignment wins, so a face cannot be claimed by two characters and a
    character cannot claim two faces. With two people this is a comparison of two
    pairings; it is written generally so a third needs no rewrite.
    """
    import itertools

    faces = analyze_all(path)
    scorers = {cid: _scorer(cid) for cid in cast}
    floors = [load_threshold(cid) for cid in cast if scorers[cid][0]]
    blend_floor = min(floors) if floors else None

    # score[cid][i] — how well face i matches that character
    table: dict[str, list[tuple[float, str, float | None]]] = {}
    for cid, (g, score) in scorers.items():
        table[cid] = [score(f) if g else (-1.0, "", None) for f in faces]

    # Best one-to-one assignment. Only characters that CAN be placed are placed;
    # with fewer faces than characters somebody is genuinely missing.
    best, best_total = None, None
    k = min(len(cast), len(faces))
    for picks in itertools.permutations(range(len(faces)), k):
        total = sum(table[cast[j]][i][0] for j, i in enumerate(picks))
        if best_total is None or total > best_total:
            best, best_total = picks, total

    members: list[CastMember] = []
    # A LIST, not a dict keyed by character: the same character can legitimately
    # be named twice (that is the blend fixture — one woman, two slots), and a
    # dict silently collapses her to one entry, leaving no pair to compare and a
    # blend that reports as clean.
    assigned: list[Face] = []
    for j, cid in enumerate(cast):
        if best is None or j >= len(best) or not scorers[cid][0]:
            members.append(CastMember(cid, None))
            continue
        f = faces[best[j]]
        sim, name, src_yaw = table[cid][best[j]]
        members.append(CastMember(cid, Verdict(
            sim, name, load_threshold(cid), f, source_yaw=src_yaw,
            faces_in_frame=len(faces))))
        assigned.append(f)

    # Distinctness: the WORST (highest) face-to-face similarity among the people
    # we placed. Two of her is the failure; two of anyone is the failure.
    pairs = list(itertools.combinations(assigned, 2))
    distinctness = max((similarity(a.vector, b.vector) for a, b in pairs),
                       default=None)
    return CastVerdict(members, distinctness, blend_floor, len(faces))


def _scorer(cid: str | None):
    """(gallery, score_fn) for one character.

    Split out of check() so check_cast() scores every face by the SAME rule.
    That rule is load-bearing: nearest gallery entry BY YAW, then report what it
    scores — never the highest-scoring entry, which picks whichever reference
    flatters the candidate. corr(|yaw|, sim) = -0.761, so choosing by similarity
    quietly measures head angle. A second implementation of this would drift from
    the first and nobody would notice until a number lied.
    """
    g = load_gallery(cid)
    meta = load_meta(cid)
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

    return g, score


def check(path: str | Path, threshold: float | None = None,
          character: str | None = None) -> Verdict:
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
    # `character` is not decoration. Both the gallery and the threshold are
    # CharPath proxies resolving through get_active(), and generate() runs in a
    # background thread that does NOT inherit the request's character scope
    # (config.py:52). Left as None, a shot that takes 70-220s to render is
    # scored against whichever character happens to be active when it FINISHES
    # — so switching tabs mid-render writes a stranger's-gallery verdict onto
    # her row, with nothing to flag it. Every number in FINDINGS.md is drawn
    # from this corpus, so a silent mis-scoring is the worst kind of bug here.
    g, scorer = _scorer(character)
    if not g:
        raise FileNotFoundError("gallery is empty — import an identity reference "
                                "and seed it from data/refs")
    score = scorer

    faces = analyze_all(path)
    face = max(faces, key=lambda f: score(f)[0]) if len(faces) > 1 else faces[0]
    sim, name, src_yaw = score(face)

    thr = threshold if threshold is not None else load_threshold(character)
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
    if len(g) < 3:
        raise ValueError(f"need >=3 gallery faces to calibrate, have {len(g)}")

    # POSE-MATCHED PAIRS ONLY, and this was wrong for as long as the function
    # existed. check() chooses the gallery entry CLOSEST IN YAW and scores
    # against that one — it never compares a frontal shot to a profile. So
    # calibrating over every pair measures a distribution the checker does not
    # sample, and cross-pose pairs are inherently low, which inflates the
    # variance and drags the floor down.
    #
    # Measured on Kiara's 13-entry gallery, 2026-08-25:
    #
    #     all pairs      n=78  mean 0.673  std 0.098  ->  2 sigma floor 0.476
    #     pose-matched   n=26  mean 0.754  std 0.036  ->  2 sigma floor 0.682
    #
    # The spread collapses by a factor of three once like is compared with like.
    # The old number would have kept 76% of every run ever made; it was not a
    # stranger floor, it was noise about head angle.
    meta = load_meta()
    names = list(g)
    yaws = {n: (meta.get(n) or {}).get("yaw") for n in names}
    sims, cross = [], 0
    for a, b in itertools.combinations(names, 2):
        ya, yb = yaws.get(a), yaws.get(b)
        if ya is None or yb is None:
            continue
        if abs(ya - yb) > POSE_DELTA_MAX:
            cross += 1
            continue
        sims.append(similarity(g[a], g[b]))
    if len(sims) < 3:
        raise ValueError(
            f"only {len(sims)} pose-matched pairs in a {len(g)}-entry gallery — "
            f"add entries at similar yaw before calibrating")

    mean, std = float(np.mean(sims)), float(np.std(sims))
    lo = float(np.min(sims))
    result = {"threshold": round(max(0.0, mean - sigma * std), 3),
              "mean": round(mean, 3), "std": round(std, 3),
              "min": round(lo, 3),
              "n_faces": len(g), "n_pairs": len(sims),
              "n_cross_pose_skipped": cross,
              "pose_delta_max": POSE_DELTA_MAX, "sigma": sigma,
              "warning": "Stranger floor, not a quality bar."}
    # A floor ABOVE the lowest genuine pair would reject two images that are
    # both, by construction, her. At small n the normal assumption behind sigma
    # is the thing that breaks first, so say so rather than ship a floor the
    # gallery itself fails.
    if result["threshold"] > lo:
        result["warning"] += (f" ⚠ floor {result['threshold']} sits ABOVE the "
                              f"lowest genuine pair {round(lo, 3)} — at n={len(sims)} "
                              f"the tail is not normal; consider a larger sigma.")
    THRESHOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.write_json_atomic(THRESHOLD_PATH, result)
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
    config.write_json_atomic(THRESHOLD_PATH, result)
    return result
