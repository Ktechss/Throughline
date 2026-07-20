"""FastAPI app behind the React UI.

    .venv-win\\Scripts\\python.exe -m uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import json
from pathlib import Path

import shutil

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import describe, gate, generate, prompt as promptlib, prompter, skeleton
from .config import (BODIES, BODIES_META, GOLD, IMAGES, PARTS_PATH, POSE_REFS,
                     POSES, REFS, ROOT, SCENE_EDIT, STATE, WARDROBE)

app = FastAPI(title="eve1")

# Vite dev server. Same-origin in production; this is for `npm run dev`.
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


# ---------------------------------------------------------------- parts

def _load_parts() -> list[promptlib.Part]:
    if PARTS_PATH.exists():
        return [promptlib.Part(**d) for d in json.loads(PARTS_PATH.read_text())]
    parts = promptlib.default_parts()
    _save_parts(parts)
    return parts


def _save_parts(parts: list[promptlib.Part]) -> None:
    PARTS_PATH.write_text(json.dumps([p.dict() for p in parts], indent=2) + "\n")


@app.get("/api/parts")
def get_parts():
    parts = _load_parts()
    return {"parts": [p.dict() for p in parts], "sections": promptlib.SECTIONS}


@app.put("/api/parts")
def put_parts(payload: dict = Body(...)):
    parts = [promptlib.Part(**d) for d in payload["parts"]]
    _save_parts(parts)
    return {"parts": [p.dict() for p in parts]}


@app.post("/api/parts/reset")
def reset_parts():
    parts = promptlib.default_parts()
    _save_parts(parts)
    return {"parts": [p.dict() for p in parts]}


# ---------------------------------------------------------------- compose

class ComposeReq(BaseModel):
    has_reference: bool = False
    pose_name: str | None = None


@app.post("/api/compose")
def compose(req: ComposeReq):
    """The final whole-body prompt, exactly as it will be sent."""
    parts = _load_parts()
    pose_note = ""
    if req.pose_name:
        p = _load_pose(req.pose_name)
        pose_note = skeleton.describe(p)
    text = promptlib.compose(parts, has_reference=req.has_reference,
                             pose_note=pose_note)
    return {
        "prompt": text,
        "system": promptlib.SYSTEM,
        "lint": promptlib.lint(parts, has_reference=req.has_reference),
        "chars": len(text),
        "dropped": [p.id for p in parts
                    if p.enabled and p.identity and req.has_reference],
    }


# ---------------------------------------------------------------- poses

def _pose_path(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in "-_")
    if not safe:
        raise HTTPException(400, "bad pose name")
    return POSES / f"{safe}.json"


def _load_pose(name: str) -> skeleton.Pose:
    p = _pose_path(name)
    if not p.exists():
        return skeleton.default_pose(name)
    return skeleton.Pose.from_json(json.loads(p.read_text()))


@app.get("/api/poses")
def list_poses():
    return {"poses": sorted(p.stem for p in POSES.glob("*.json"))}


@app.get("/api/poses/{name}")
def get_pose(name: str):
    return _load_pose(name).to_json()


@app.put("/api/poses/{name}")
def put_pose(name: str, payload: dict = Body(...)):
    pose = skeleton.Pose.from_json(payload)
    pose.name = name
    _pose_path(name).write_text(json.dumps(pose.to_json(), indent=2) + "\n")
    return pose.to_json()


@app.delete("/api/poses/{name}")
def delete_pose(name: str):
    _pose_path(name).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/poses/{name}/preview.png")
def pose_preview(name: str):
    """The exact image handed to the model — not an approximation of it."""
    return Response(content=skeleton.render_bytes(_load_pose(name)),
                    media_type="image/png")


@app.get("/api/skeleton/default")
def skeleton_default():
    return {"pose": skeleton.default_pose().to_json(),
            "names": skeleton.NAMES,
            "limbs": [[a, b, list(c)] for a, b, c in skeleton.LIMBS]}


# ---------------------------------------------------------------- generate

class GenReq(BaseModel):
    aspect: str = "4:5"
    seed: int | None = None
    pose_name: str | None = None
    use_pose_image: bool = False
    refs: list[str] = []          # filenames under data/images, or absolute
    note: str = ""


def _resolve_ref(name: str) -> Path:
    """A reference may be an imported identity ref or a previous generation."""
    p = Path(name)
    if p.is_absolute() and p.exists():
        return p
    for base in (REFS, IMAGES):
        q = base / Path(name).name
        if q.exists():
            return q
    raise HTTPException(400, f"no such reference: {name}")


@app.post("/api/generate")
def do_generate(req: GenReq):
    parts = _load_parts()
    refs = [_resolve_ref(r) for r in req.refs]
    has_ref = bool(refs)
    # One trigger, one session — even though this endpoint makes a single image
    # today. When it fans out (a re-roll loop, a model bakeoff), the grouping is
    # already correct rather than needing to be retrofitted.
    session = generate.new_session(
        req.note or ", ".join(Path(r).stem for r in req.refs) or "no reference")

    pose_file = None
    pose_note = ""
    if req.pose_name:
        pose = _load_pose(req.pose_name)
        pose_note = skeleton.describe(pose)
        if req.use_pose_image:
            pose_file = POSES / f"{pose.name}.png"
            skeleton.save(pose, pose_file)
            # Costs a reference slot. See FINDINGS: three refs scored 0.547 vs
            # 0.811 for one. Verify by reading back yaw, not similarity.
            refs.append(pose_file)

    text = promptlib.compose(parts, has_reference=has_ref, pose_note=pose_note)
    try:
        row = generate.generate(
            prompt=text, system=promptlib.SYSTEM, refs=refs,
            aspect=req.aspect, seed=req.seed, pose_file=pose_file,
            session=session,
            meta={"note": req.note, "pose": req.pose_name,
                  "pose_as_image": req.use_pose_image},
        )
    except Exception as exc:  # noqa: BLE001 — surface it in the UI, don't 500
        raise HTTPException(500, str(exc)[:300]) from exc
    return row


# ---------------------------------------------------------------- runs

@app.get("/api/runs")
def runs():
    return {"runs": generate.all_runs()}


class MarkReq(BaseModel):
    decision: str | None = None   # "approve" | "reject" | null


@app.post("/api/runs/{run_id}/mark")
def mark(run_id: str, req: MarkReq):
    try:
        return generate.mark(run_id, req.decision)
    except KeyError:
        raise HTTPException(404, run_id) from None


@app.get("/api/images/{name}")
def image(name: str):
    p = IMAGES / Path(name).name
    if not p.exists():
        raise HTTPException(404, name)
    return FileResponse(p)


# Generated images are 3584x4800 / ~20 MB each. A grid rendering the full files
# downloads hundreds of MB and decodes each to a ~69 MB bitmap in the browser —
# the archive would sink the UI as it grows. Grids request this cached ~512px
# JPEG thumbnail instead; the full image is only fetched in the detail view.
THUMBS = IMAGES / ".thumbs"


@app.get("/api/images/{name}/thumb")
def image_thumb(name: str):
    src = IMAGES / Path(name).name
    if not src.exists():
        raise HTTPException(404, name)
    THUMBS.mkdir(exist_ok=True)
    cache = THUMBS / f"{Path(name).stem}.jpg"
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        from PIL import Image
        im = Image.open(src).convert("RGB")
        im.thumbnail((512, 512))
        im.save(cache, "JPEG", quality=80)
    return FileResponse(cache)


# ---------------------------------------------------------------- gallery

@app.get("/api/gallery")
def get_gallery():
    g = gate.load_gallery()
    meta = gate.load_meta()
    out = {"entries": sorted(g), "threshold": gate.load_threshold(),
           "meta": meta, "pose_delta_max": gate.POSE_DELTA_MAX}
    if len(g) > 1:
        import itertools
        out["pairwise"] = [
            {"a": a, "b": b, "similarity": round(gate.similarity(g[a], g[b]), 3)}
            for a, b in itertools.combinations(sorted(g), 2)
        ]
    return out


# NOTE: /api/gallery/from-ref seeds ONLY from data/refs. The one place a
# GENERATED image enters the gallery is the CALIBRATION engine below, and only
# via explicit human selection — see the warning on /api/calibrate/gallery/add.


# ---------------------------------------------------------------- calibration
# Rebuild the identity/fingerprint natively on the primary generator (nano-pro).
# Generate canonical headshot angles -> the user SELECTS the on-model ones ->
# they seed a fresh gallery -> recalibrate the threshold from their self-agreement.
# The essential angle set is from the user's Character Calibration Rules.

IDENTITY_LOCK_LINE = (
    "Preserve the exact same facial identity, facial proportions, skin texture, "
    "beauty marks, eye shape, nose, lips, hairline, hair colour and body "
    "proportions. No identity drift.")

# (angle key, prompt fragment) — ordered by importance; front/3q/profile give the
# pose-matched gallery its coverage, the rest add same-person variety.
CALIB_FACES = [
    ("front", "a straight front headshot, facing the camera directly, eyes to camera"),
    ("tq-left", "a three-quarter headshot, face turned to the left, eyes toward camera"),
    ("tq-right", "a three-quarter headshot, face turned to the right, eyes toward camera"),
    ("profile-left", "a left side-profile headshot"),
    ("profile-right", "a right side-profile headshot"),
    ("over-shoulder", "looking back over one shoulder toward the camera"),
    ("chin-up", "a headshot, chin slightly raised, confident expression"),
    ("smile", "a headshot with a natural warm smile"),
    ("editorial", "a neutral editorial headshot expression"),
    ("tilt-left", "a headshot, head tilted slightly to the left"),
    ("tilt-right", "a headshot, head tilted slightly to the right"),
    ("soft", "a headshot, chin slightly lowered, soft eye contact"),
]


class CalibFacesReq(BaseModel):
    count: int = 5


@app.post("/api/calibrate/faces")
def calibrate_faces(req: CalibFacesReq):
    """Generate `count` canonical headshots (identity-locked) on the primary model."""
    face = REFS / _bio_ref()
    if not face.exists():
        raise HTTPException(400, "no BIO face reference set")
    n = max(1, min(req.count, len(CALIB_FACES)))
    jobs = []
    for angle, desc in CALIB_FACES[:n]:
        prompt = (f"Headshot portrait of @image1 — {desc}. Plain neutral studio "
                  f"background, soft even lighting, head and shoulders framing. "
                  f"{IDENTITY_LOCK_LINE} Photorealistic, real skin texture, sharp "
                  f"focus on the face.")

        def run(job: dict, prompt=prompt, angle=angle) -> dict:
            return generate.generate(
                prompt=prompt, system="", refs=[face], aspect="3:4",
                session=generate.new_session(f"calib face: {angle}"), progress=job,
                meta={"calibrate": "face", "angle": angle})

        jobs.append({"angle": angle, "job": generate.start_job(f"calib {angle}", run)})
    return {"jobs": jobs}


@app.get("/api/calibrate/candidates")
def calibrate_candidates():
    """Generated calibration faces awaiting selection, newest first."""
    out = []
    for r in generate.all_runs():
        if r.get("meta", {}).get("calibrate") == "face":
            out.append({"id": r["id"], "file": r["file"],
                        "angle": r.get("meta", {}).get("angle"),
                        "verdict": r.get("verdict", {})})
    return {"candidates": out[:60]}


class CalibAddReq(BaseModel):
    run_id: str
    view: str | None = None


@app.post("/api/calibrate/gallery/add")
def calibrate_gallery_add(req: CalibAddReq):
    """Add a SELECTED, human-approved calibration face to the gallery.

    ⚠ This is the ONE place a generated image enters the gallery — deliberately,
    because the calibration set defines the character natively on the primary
    model. Two safeguards keep it honest: it is gated by human selection (the
    user picked this exact face), and it is used to seed a FROZEN fingerprint,
    never fed continuously. Do not automate this. See gate.py's drift warning.
    """
    row = next((r for r in generate.all_runs() if r["id"] == req.run_id), None)
    if not row:
        raise HTTPException(404, req.run_id)
    name = req.view or row.get("meta", {}).get("angle") or req.run_id
    try:
        face = gate.add_to_gallery(IMAGES / row["file"], name)
    except gate.NoFaceFound as exc:
        raise HTTPException(400, str(exc)) from None
    return {"view": name, "yaw": round(face.yaw, 1), "face_px": face.width,
            "pose_class": face.pose_class}


@app.post("/api/calibrate/recalibrate")
def calibrate_recalibrate():
    """Set the threshold from the seeded fingerprint's own self-agreement."""
    try:
        return gate.calibrate_from_gallery()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.post("/api/calibrate/reset")
def calibrate_reset():
    """Wipe the gallery to start a fresh calibration."""
    gate.reset_gallery()
    return {"ok": True}


# ---------------------------------------------------------------- references

def _ref_info(p: Path) -> dict:
    """A reference is only useful if ArcFace can see a face in it — report that
    up front rather than letting a faceless reference fail silently at
    generation time."""
    row = {"name": p.name, "bytes": p.stat().st_size}
    try:
        f = gate.analyze(p)
        row |= {"face_px": f.width, "yaw": round(f.yaw, 1),
                "pose_class": f.pose_class, "usable": True}
    except (gate.NoFaceFound, ValueError) as exc:
        row |= {"usable": False, "reason": str(exc)[:100]}
    return row


@app.get("/api/refs")
def list_refs():
    return {"refs": [_ref_info(p) for p in sorted(REFS.iterdir())
                     if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]}


class ImportReq(BaseModel):
    path: str


@app.post("/api/refs/import")
def import_ref(req: ImportReq):
    """Copy a local image in as an identity reference.

    Copied, not linked: a reference that can move or be deleted out from under
    the pipeline is a reference that will silently change who she is.
    """
    src = Path(req.path)
    if not src.exists() or not src.is_file():
        raise HTTPException(400, f"no such file: {req.path}")
    dest = REFS / src.name
    shutil.copy2(src, dest)
    info = _ref_info(dest)
    if not info["usable"]:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"no face detected in {src.name} — not a usable "
                                 f"identity reference")
    return info


@app.post("/api/refs/upload")
async def upload_ref(file: UploadFile = File(...)):
    dest = REFS / Path(file.filename).name
    dest.write_bytes(await file.read())
    info = _ref_info(dest)
    if not info["usable"]:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"no face detected in {file.filename}")
    return info


@app.delete("/api/refs/{name}")
def delete_ref(name: str):
    (REFS / Path(name).name).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/refs/{name}/file")
def ref_file(name: str):
    p = REFS / Path(name).name
    if not p.exists():
        raise HTTPException(404, name)
    return FileResponse(p)


class GalleryFromRefReq(BaseModel):
    name: str            # file in data/refs
    view: str = "front"  # gallery entry name


@app.post("/api/gallery/from-ref")
def gallery_from_ref(req: GalleryFromRefReq):
    """Make an identity reference the thing we MEASURE against.

    The generation reference and the gallery are different jobs: one tells the
    model who to draw, the other tells us whether it obeyed. Using the same
    image for both is how you find out.
    """
    p = REFS / Path(req.name).name
    if not p.exists():
        raise HTTPException(404, req.name)
    try:
        face = gate.add_to_gallery(p, req.view)
    except gate.NoFaceFound as exc:
        raise HTTPException(400, str(exc)) from None
    return {"view": req.view, "yaw": round(face.yaw, 1),
            "face_px": face.width, "pose_class": face.pose_class}


# ---------------------------------------------------------------- bio

BIO_REF_PATH = STATE / "bio.json"

# The BIO's references. Every generation attaches them — the whole point of a
# locked BIO is that you cannot forget who she is. The first run of this project
# had no reference attached and invented a stranger; that failure should not be
# reachable from the UI.
#
# TWO references, doing two jobs:
#   face — her identity. Words cannot specify a person; measured 0.860 with a
#          reference against 0.531 with a description.
#   body — her build. Same argument, applied to proportions: "38DD, 30in waist"
#          is a description, and the generator resolves descriptions into its
#          own defaults (corseted waist, spherical bust). An image is not a
#          description.
#
# ⚠ They must come from the SAME generation or they disagree about her before
# the model starts. Measured on nano-banana: mismatched body+face refs scored
# 0.562, a matched pair 0.588. cd-body/cd-face are both cropped from
# 'Close and Distance shot.png' — one pass, one commitment to her.
DEFAULT_BIO_REF = "Kiara.png"
DEFAULT_BODY_REF = "cd-body.png"


def _bio_cfg() -> dict:
    cfg = json.loads(BIO_REF_PATH.read_text()) if BIO_REF_PATH.exists() else {}
    return {"reference": cfg.get("reference", DEFAULT_BIO_REF),
            "body_reference": cfg.get("body_reference", DEFAULT_BODY_REF)}


def _bio_ref() -> str:
    return _bio_cfg()["reference"]


def _bio_refs() -> list[Path]:
    """Face first, body second. Order is not arbitrary — the first reference
    dominates, and identity matters more than proportion."""
    cfg = _bio_cfg()
    out = []
    for key in ("reference", "body_reference"):
        p = REFS / Path(cfg[key]).name
        if p.exists():
            out.append(p)
    return out


@app.get("/api/bio")
def get_bio():
    """Who Kiara is. Locked, and attached to every shot."""
    parts = _load_parts()
    cfg = _bio_cfg()
    ref_path = REFS / cfg["reference"]
    body_path = REFS / cfg["body_reference"]
    out = promptlib.bio_summary(parts, has_reference=ref_path.exists())
    out["reference"] = cfg["reference"] if ref_path.exists() else None
    out["body_reference"] = cfg["body_reference"] if body_path.exists() else None
    if ref_path.exists():
        try:
            f = gate.analyze(ref_path)
            out["reference_face"] = {"face_px": f.width, "yaw": round(f.yaw, 1),
                                     "pose_class": f.pose_class}
        except (gate.NoFaceFound, ValueError):
            out["reference_face"] = None
    g = gate.load_gallery()
    out["gallery"] = {"entries": sorted(g), "meta": gate.load_meta(),
                      "threshold": gate.load_threshold()}
    return out


class BioRefReq(BaseModel):
    reference: str


@app.put("/api/bio/reference")
def set_bio_ref(req: BioRefReq):
    """Changing this changes who Kiara is for every future generation.

    Merge, don't overwrite: writing only {"reference": ...} used to drop a
    custom body_reference back to its default. Preserve the rest of the config.
    """
    name = Path(req.reference).name
    if not (REFS / name).exists():
        raise HTTPException(400, f"no such reference: {name}")
    cfg = _bio_cfg()
    cfg["reference"] = name
    BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    return {"reference": name}


@app.post("/api/bio/reference/from-run")
def bio_reference_from_run(payload: dict = Body(...)):
    """Promote a generated face (a calibration face) to the BIO identity (@image1).

    After calibration the identity anchor should be a NANO-NATIVE face, not the
    original uploaded base — so every generation is seeded from the same model
    that built the fingerprint. That is what keeps @image1 and the gallery in
    the same 'look'.
    """
    run_id = payload["run_id"]
    name = payload.get("name") or f"identity-{run_id}"
    row = next((r for r in generate.all_runs() if r["id"] == run_id), None)
    if not row:
        raise HTTPException(404, run_id)
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or run_id
    dest = REFS / f"{safe}.png"
    shutil.copy2(IMAGES / row["file"], dest)
    try:
        gate.analyze(dest)   # must contain a detectable face
    except (gate.NoFaceFound, ValueError):
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "no face detected in that image") from None
    cfg = _bio_cfg()
    cfg["reference"] = dest.name
    BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    return {"reference": dest.name}


class BodyRefCreateReq(BaseModel):
    shape: str | None = None   # optional shape override; else uses the body parts


@app.post("/api/bio/body-ref/create")
def body_ref_create(req: BodyRefCreateReq):
    """Generate a canonical BODY image from the face + body-shape text ONLY.

    No competing body image is attached, so the TEXT drives the proportions
    (the ChatGPT text-to-image mode) — this is how you actually set an exact or
    large figure, which an edit anchored to an existing body cannot. Review the
    preview, then save it as the body reference; every shot and outfit then
    inherits that image's proportions exactly.
    """
    face = REFS / _bio_ref()
    if not face.exists():
        raise HTTPException(400, "no BIO face reference set")
    shape = (req.shape or "").strip() or promptlib.build_clause(_load_parts())
    shape_clean, _ = promptlib.sanitise(shape)   # size passes now; nudity still guarded
    prompt = (
        "Full-body studio photograph of @image1 on a plain white seamless "
        "background, lit flat and even. She stands straight and relaxed facing "
        "the camera, arms at her sides, neutral expression, wearing simple "
        "fitted plain activewear (a fitted tank top and leggings) so her figure "
        f"and proportions are clearly visible. {shape_clean} Her face and "
        "identity exactly match @image1. Photorealistic, real skin texture, "
        "natural anatomy.")

    def run(job: dict) -> dict:
        return generate.generate(
            prompt=prompt, system="", refs=[face], aspect="3:4",
            session=generate.new_session("body reference"), progress=job,
            meta={"body_ref_create": True, "shape": shape_clean},
            fallback_endpoint=SCENE_EDIT)

    return {"job": generate.start_job("body reference", run)}


@app.post("/api/bio/body-ref/save")
def body_ref_save(payload: dict = Body(...)):
    """Lock a generated body image in as the BODY reference (@image2 everywhere)."""
    run_id = payload["run_id"]
    row = next((r for r in generate.all_runs() if r["id"] == run_id), None)
    if not row:
        raise HTTPException(404, run_id)
    dest = REFS / "body-canonical.png"
    shutil.copy2(IMAGES / row["file"], dest)
    cfg = _bio_cfg()
    cfg["body_reference"] = "body-canonical.png"
    BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    return {"body_reference": "body-canonical.png"}


# ---------------------------------------------------------------- body types
# A library of saved BODY types (figure references), like the wardrobe. Each is
# an image + the bust/build text it was made with, so selecting one restores BOTH
# the reference image AND the matching text — that pairing is what keeps a figure
# consistent (the drift the user hit came from image and text disagreeing).

def _bodies() -> dict:
    if BODIES_META.exists():
        return json.loads(BODIES_META.read_text())
    return {"active": None, "bodies": []}


def _save_bodies(data: dict) -> None:
    BODIES_META.write_text(json.dumps(data, indent=2) + "\n")


def _bust_text() -> str:
    p = next((q for q in _load_parts() if q.id == "body.bust"), None)
    return p.text if p else ""


@app.get("/api/bodies")
def list_bodies():
    data = _bodies()
    active = data.get("active")
    out = []
    for b in data.get("bodies", []):
        f = _find_by_id(BODIES, b["id"])
        if f:
            out.append({"id": b["id"], "file": f.name, "build": b.get("build", ""),
                        "active": b["id"] == active, "created": b.get("created")})
    return {"bodies": out, "active": active}


@app.post("/api/bodies/save")
def body_save(payload: dict = Body(...)):
    """Save a generated body image as a named body type (image + current build)."""
    run_id, name = payload["run_id"], payload["name"]
    row = next((r for r in generate.all_runs() if r["id"] == run_id), None)
    if not row:
        raise HTTPException(404, run_id)
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ").strip() or run_id
    shutil.copy2(IMAGES / row["file"], BODIES / f"{safe}.png")
    data = _bodies()
    data["bodies"] = [b for b in data["bodies"] if b["id"] != safe]
    data["bodies"].append({"id": safe, "build": _bust_text(),
                           "created": row.get("created")})
    _save_bodies(data)
    return {"id": safe}


class BodySelectReq(BaseModel):
    id: str


@app.post("/api/bodies/select")
def body_select(req: BodySelectReq):
    """Make a body type active: its image becomes @image2 everywhere, and its
    saved bust text is restored so the image and text agree (no drift)."""
    data = _bodies()
    b = next((x for x in data["bodies"] if x["id"] == req.id), None)
    src = _find_by_id(BODIES, req.id)
    if not b or not src:
        raise HTTPException(404, req.id)
    shutil.copy2(src, REFS / "body-canonical.png")   # the active body reference
    cfg = _bio_cfg()
    cfg["body_reference"] = "body-canonical.png"
    BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    # restore the matching bust text so the figure stays consistent
    if b.get("build"):
        parts = _load_parts()
        for p in parts:
            if p.id == "body.bust":
                p.text = b["build"]
        _save_parts(parts)
    data["active"] = req.id
    _save_bodies(data)
    return {"active": req.id, "build": b.get("build", "")}


@app.get("/api/bodies/{name}/file")
def body_file(name: str):
    p = BODIES / Path(name).name
    if not p.exists():
        raise HTTPException(404, name)
    return FileResponse(p)


@app.delete("/api/bodies/{name}")
def body_delete(name: str):
    (BODIES / f"{Path(name).stem}.png").unlink(missing_ok=True)
    data = _bodies()
    data["bodies"] = [b for b in data["bodies"] if b["id"] != Path(name).stem]
    if data.get("active") == Path(name).stem:
        data["active"] = None
    _save_bodies(data)
    return {"ok": True}


# ---------------------------------------------------------------- wardrobe

def level_ref_head(path: Path) -> float:
    """Rotate a reference image in place so the head is level. Returns degrees.

    A reference leaks its head tilt into every output (that is the whole
    mechanism). The face and body references were already leveled; an outfit
    reference is just another leak source. Expand + fill (no crop) so the full
    garment survives — this is a reference the model reads, not a delivered
    image, so filled corners are harmless.
    """
    from PIL import Image
    try:
        f = gate.analyze(path)
    except (gate.NoFaceFound, ValueError):
        return 0.0
    if abs(f.roll) < 1.0:
        return 0.0
    im = Image.open(path).convert("RGB")
    im.rotate(f.roll, resample=Image.BICUBIC, expand=True,
              fillcolor=(245, 245, 245)).save(path)
    return round(f.roll, 1)


def _find_by_id(directory: Path, ident: str) -> Path | None:
    """Resolve a saved reference by its id (stem) across ANY image extension.

    Uploads keep their original extension (.jpg, .webp, …); saves-from-run are
    .png. Assuming .png at lookup time was a bug — a .jpg outfit selected fine in
    the UI but 404'd on generate.
    """
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = directory / f"{ident}{ext}"
        if p.exists():
            return p
    return None


def _wardrobe() -> list[dict]:
    out = []
    for p in sorted(WARDROBE.iterdir()) if WARDROBE.exists() else []:
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            out.append({"id": p.stem, "file": p.name})
    return out


# The wardrobe turnaround is a photo of HER wearing the outfit, so it carries a
# competing face — measured to drag a headshot's identity ~0.85 -> ~0.64 even
# with the "clothing only" directive. Crop the head off so @image2 is the garment
# alone and identity comes solely from @image1 — the project's own "crop faces
# off references" rule, applied to the wardrobe. Cached in a hidden subdir so the
# crops never appear as wardrobe items themselves.
OUTFIT_CROPS = WARDROBE / ".outfitcrops"


def _outfit_ref(path: Path) -> Path:
    """Clothing-only version of a wardrobe image: head cropped off. Falls back to
    the original if no face is found or the face already fills the frame."""
    from PIL import Image
    OUTFIT_CROPS.mkdir(exist_ok=True)
    cache = OUTFIT_CROPS / f"{path.stem}.png"
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return cache
    try:
        box = gate.face_box(path)
    except ValueError:
        box = None
    if box is None:
        return path
    im = Image.open(path).convert("RGB")
    W, H = im.size
    _, fy1, _, fy2 = box
    # Crop from just below the chin down — removes eyes/nose/mouth (the identity),
    # keeps the neckline, shoulders and the whole outfit.
    top = fy2 + int((fy2 - fy1) * 0.10)
    if top >= H - 40:
        return path   # face fills the frame (already a close crop) — nothing to gain
    im.crop((0, top, W, H)).save(cache)
    return cache


@app.get("/api/wardrobe")
def list_wardrobe():
    return {"wardrobe": _wardrobe()}


@app.post("/api/wardrobe/upload")
async def wardrobe_upload(file: UploadFile = File(...)):
    """An outfit is saved as a reference image. It becomes @image2 on any shot
    that selects it, with a 'reproduce exactly' directive — the fix for the
    wardrobe leak, since the outfit now comes from its own reference rather than
    losing a text tug-of-war with the identity photo."""
    dest = WARDROBE / Path(file.filename).name
    dest.write_bytes(await file.read())
    return {"id": dest.stem, "file": dest.name}   # saved as-is, never rotated


@app.post("/api/wardrobe/describe")
async def wardrobe_describe(file: UploadFile = File(...)):
    """Describe an uploaded reference outfit image with Claude vision.

    Step one of the two-step create flow: upload an outfit photo from the
    internet, get back a clean garment-only description. The user reviews/edits
    it, then it feeds /api/wardrobe/create as the `outfit` text. Nothing is
    saved here — this is a read of the image, not an import of it.
    """
    data = await file.read()
    media = describe.media_type(file.filename or "", file.content_type)
    try:
        out = describe.describe_outfit(data, media)
    except describe.DescribeError as exc:
        raise HTTPException(400, str(exc)) from exc
    # outfit = the garment prose; details = the small fields (empty ones the UI
    # highlights for the user to fill: shoes, nail colours, lipstick, etc.).
    return {"outfit": out["description"], "details": out["details"]}


class OutfitCreateReq(BaseModel):
    outfit: str          # free text: "white crop top, baggy jeans, strappy heels"
    name: str | None = None   # optional label only; the outfit is SAVED later via
                              # /api/wardrobe/from-run once the user likes the preview


def _clean_outfit_text(text: str) -> str:
    """Strip ChatGPT chat-wrapper noise from a pasted outfit description.

    Users paste from a chat that adds a preamble ("Here's a polished Full Look
    Description suitable for..."), markdown headings (### ...), and dividers
    (---). None of that is the outfit; some of it ("suitable for an AI character
    model") can even confuse the image model. Keep only the descriptive prose.
    """
    import re
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#") or set(s) <= {"-", "*", "_", " "}:   # heading / rule
            continue
        low = s.lower()
        # A leading meta sentence: "Here's a ...:" / "... description:" with no
        # real content after the colon on the same line.
        if (low.startswith(("here's", "here is", "sure", "certainly"))
                or low.rstrip(":").endswith(("description", "full look",
                                             "look description"))) and s.endswith(":"):
            continue
        lines.append(re.sub(r"\*\*|\*|`", "", s))   # drop bold/italic marks
    return " ".join(lines).strip() or text.strip()


@app.post("/api/wardrobe/create")
def wardrobe_create(req: OutfitCreateReq):
    """Generate the outfit ONTO her as a clean white-studio reference — PREVIEW only.

    This is the ai-influencer technique for good wardrobe: instead of uploading
    an arbitrary outfit photo (which drags in a stranger's face, a scene, and a
    conflicting framing), we generate HER wearing the outfit on plain white — a
    clean swatch. Used later as @image2, it injects only the clothing, because
    that is all that varies from her own references.

    Generate-then-preview: this only produces the turnaround (a normal run). It
    does NOT save to the wardrobe — the user reviews the preview and, if they
    like it, saves it with a name via /api/wardrobe/from-run (or discards it).
    Identity comes from her face + body references; the prompt changes only the
    outfit and pins the background to white so nothing else leaks.
    """
    face = REFS / _bio_ref()
    if not face.exists():
        raise HTTPException(400, "no BIO reference set")
    refs = [face]
    body = REFS / _bio_cfg()["body_reference"]
    has_body = body.exists()
    if has_body:
        refs.append(body)

    # Face and body are two references doing two jobs — and now that @image1 is a
    # HEADSHOT, the turnaround must be told to take proportions from @image2 (the
    # body), not @image1. Without a body ref, @image1 carries both.
    identity_clause = (
        "Her face and identity are @image1; her body build, height, frame and "
        "proportions are @image2. Replicate her face, bone structure, skin and "
        "hair exactly from @image1, and her exact body proportions and build from "
        "@image2, in every panel — unmistakably the same person."
        if has_body else
        "The woman is @image1 — replicate her face, bone structure, skin, hair "
        "and body proportions exactly in every panel; unmistakably the same person.")

    # Same body-shape tuning as shots — so the turnaround is built with the bust/
    # waist/hips you set, and a wardrobe (used as @image2 later) doesn't fight the
    # shot's build clause. Sanitised here because this prompt path isn't otherwise.
    build_clean, _ = promptlib.sanitise(promptlib.build_clause(_load_parts()))

    outfit = _clean_outfit_text(req.outfit)   # strip pasted chat/markdown noise
    label = ("".join(c for c in (req.name or outfit) if c.isalnum() or c in "-_ ")
             .strip())[:50] or "outfit"
    # A 4-panel turnaround SHEET, ported from ai-influencer's buildWardrobePrompt.
    # The outfit is shown from front/side/back/3q, so the reference knows the
    # garment from every angle — essential when she is turned in a scene.
    prompt = (
        "Professional full-body character turnaround sheet. Pure white seamless "
        "background throughout. Soft neutral studio lighting, perfectly flat and "
        "even across all four panels, no shadows, no colour cast.\n\n"
        "A single row of FOUR equally sized full-body panels, each with a small "
        "label in clean sans-serif capitals above the figure: "
        '"FRONT VIEW" | "SIDE VIEW" | "BACK VIEW" | "THREE-QUARTER VIEW". '
        "Panel 1 front-facing, panel 2 exact side profile, panel 3 facing "
        "directly away, panel 4 at a 45-degree three-quarter angle.\n\n"
        f"{identity_clause} {build_clean} Identical outfit, proportions, stance and lighting "
        f"across all four panels.\n\nShe is wearing: {outfit}. Change ONLY the clothing "
        "to this outfit.\n\nPhotorealistic RAW photograph quality, real skin "
        "texture, ultra-sharp detail.")

    def run(job: dict) -> dict:
        # Generate only — no save. The image lands in data/images like any run;
        # the user saves it into the wardrobe via /api/wardrobe/from-run after
        # they see and approve the preview.
        return generate.generate(prompt=prompt, system="", refs=refs, aspect="16:9",
                                 session=generate.new_session(f"create outfit: {label}"),
                                 progress=job,
                                 meta={"outfit_create": req.outfit, "body": _bodies().get("active")},
                                 # A revealing outfit turnaround can trip gpt-image-2's
                                 # moderation; render it on the scene model instead of
                                 # dead-spinning to a failure.
                                 fallback_endpoint=SCENE_EDIT,
                                 # Wide canvas so four full-body panels fit side by side.
                                 extra={"image_size": {"width": 1536, "height": 1024}})

    jid = generate.start_job(f"create outfit: {label}", run)
    return {"job": jid}


@app.post("/api/wardrobe/from-run")
def wardrobe_from_run(payload: dict = Body(...)):
    """Promote a generated image to a saved outfit — its wardrobe becomes
    reusable. (The image's identity is irrelevant here; only the clothing is
    used, via @image2.)"""
    run_id, name = payload["run_id"], payload["name"]
    row = next((r for r in generate.all_runs() if r["id"] == run_id), None)
    if not row:
        raise HTTPException(404, run_id)
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or run_id
    dest = WARDROBE / f"{safe}.png"
    shutil.copy2(IMAGES / row["file"], dest)
    return {"id": dest.stem, "file": dest.name}   # saved as-is, never rotated


@app.get("/api/wardrobe/{name}/file")
def wardrobe_file(name: str):
    p = WARDROBE / Path(name).name
    if not p.exists():
        raise HTTPException(404, name)
    return FileResponse(p)


@app.delete("/api/wardrobe/{name}")
def wardrobe_delete(name: str):
    (WARDROBE / Path(name).name).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/pose-library")
def list_pose_library():
    return {"poses": [{"id": k, "text": v} for k, v in promptlib.POSES_LIBRARY.items()]}


# --------------- pose REFERENCE library (images of her, keyword-selected) -----
# Validated: a straight-head pose reference dropped a shot from roll -8.5 to
# -2.1 (level) AND raised identity 0.757 -> 0.845, because the reference is her.
# Steers pose at the source instead of rotating the output. Must be HER — a
# stranger's pose photo would blend into her face.

def _pose_refs() -> list[dict]:
    out = []
    for p in sorted(POSE_REFS.iterdir()) if POSE_REFS.exists() else []:
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            out.append({"id": p.stem, "file": p.name})
    return out


@app.get("/api/pose-refs")
def list_pose_refs():
    return {"pose_refs": _pose_refs()}


@app.post("/api/pose-refs/upload")
async def pose_ref_upload(file: UploadFile = File(...)):
    dest = POSE_REFS / Path(file.filename).name
    dest.write_bytes(await file.read())
    # Verify it's her with a detectable face; a poseref with no face is useless
    # and one of a stranger would corrupt identity.
    try:
        gate.analyze(dest)
    except (gate.NoFaceFound, ValueError):
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "no face in the pose reference — it must show her") from None
    return {"id": dest.stem, "file": dest.name}   # saved as-is, never rotated


@app.post("/api/pose-refs/from-run")
def pose_ref_from_run(payload: dict = Body(...)):
    run_id, name = payload["run_id"], payload["name"]
    row = next((r for r in generate.all_runs() if r["id"] == run_id), None)
    if not row:
        raise HTTPException(404, run_id)
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or run_id
    dest = POSE_REFS / f"{safe}.png"
    shutil.copy2(IMAGES / row["file"], dest)
    return {"id": dest.stem, "file": dest.name}   # saved as-is, never rotated


@app.get("/api/pose-refs/{name}/file")
def pose_ref_file(name: str):
    p = POSE_REFS / Path(name).name
    if not p.exists():
        raise HTTPException(404, name)
    return FileResponse(p)


@app.delete("/api/pose-refs/{name}")
def pose_ref_delete(name: str):
    (POSE_REFS / Path(name).name).unlink(missing_ok=True)
    return {"ok": True}


class ShotReq(BaseModel):
    brief: str = ""              # the ONLY thing the user writes
    prompt: str | None = None    # AI-written (Claude) prompt, edited by the user;
                                 # used VERBATIM when present instead of the template
    pose_name: str | None = None
    use_pose_image: bool = False
    aspect: str = "3:4"
    seed: int | None = None
    wardrobe_id: str | None = None   # attach this saved outfit as @image2
    pose_id: str | None = None       # a pose from the text library
    pose_ref_id: str | None = None   # a pose REFERENCE image, attached as @image3
    shot_type: str = "candid"
    resolution: str | None = None    # "1K" | "2K" | "4K" (nano). None -> config default


class AiPromptReq(BaseModel):
    brief: str = ""
    wardrobe_id: str | None = None
    pose_id: str | None = None
    pose_ref_id: str | None = None
    shot_type: str = "candid"


@app.post("/api/shot/ai-prompt")
def ai_prompt(req: AiPromptReq):
    """Claude rewrites the brief into a full fal prompt. Reviewable before use.

    Claude expands the SCENE from the brief but is forbidden to describe her —
    identity stays with @image1, per the measured 0.86->0.53 finding. The result
    runs through the same moderation sanitiser and is returned for the user to
    edit; it is not sent to fal until they generate.
    """
    pose_text = promptlib.POSES_LIBRARY.get(req.pose_id or "", "")
    pose_ref_tag = "@image3" if req.pose_ref_id else ""
    try:
        raw = prompter.rewrite(
            req.brief, shot_type=req.shot_type,
            has_wardrobe=bool(req.wardrobe_id), pose_ref_tag=pose_ref_tag,
            pose_text=pose_text)
    except prompter.PrompterError as exc:
        raise HTTPException(400, str(exc)) from exc
    clean, sanitised = promptlib.sanitise(raw)
    return {"prompt": clean, "sanitised": sanitised}


@app.post("/api/shot")
def shot(req: ShotReq):
    """Start one shot in the background; return a job id to poll.

    Async on purpose: fal is a ~70s blocking call (local ~5 min). A synchronous
    endpoint leaves the UI with no signal that anything is happening — the exact
    complaint this replaces. The work runs in a thread reporting stages into
    JOBS; the client polls /api/jobs/{id}.

    The BIO's reference is attached unconditionally — a shot with no identity
    reference is a photo of a stranger, and that should not be one forgotten
    checkbox away.
    """
    # Reference order defines the @image tags: @image1 = face (always).
    face = REFS / _bio_ref()
    if not face.exists():
        raise HTTPException(400, "no BIO reference set — import one on the face tab")
    refs = [face]

    has_wardrobe = False
    if req.wardrobe_id:
        w = _find_by_id(WARDROBE, req.wardrobe_id)
        if not w:
            raise HTTPException(400, f"no such wardrobe: {req.wardrobe_id}")
        refs.append(_outfit_ref(w))   # @image2 = outfit, head cropped off (no competing face)
        has_wardrobe = True
    else:
        # No outfit chosen: fall back to the body reference for build (@image2).
        cfg = _bio_cfg()
        body = REFS / cfg["body_reference"]
        if body.exists():
            refs.append(body)

    # @image3 = pose reference (her, in the desired pose/head orientation).
    pose_ref_tag = ""
    if req.pose_ref_id:
        pr = _find_by_id(POSE_REFS, req.pose_ref_id)
        if not pr:
            raise HTTPException(400, f"no such pose reference: {req.pose_ref_id}")
        refs.append(pr)
        pose_ref_tag = "@image3"

    # Body-shape tuning from the editable body parts — folded into BOTH paths so
    # bust/waist/hips edits actually change the output. The AI prompter is barred
    # from describing her body, so it's appended after Claude's scene prompt.
    build_text = promptlib.build_clause(_load_parts())
    if req.prompt and req.prompt.strip():
        # AI-written (and user-edited) prompt: use it verbatim, only running the
        # moderation sanitiser so a trigger can't slip through. The reference
        # tags (@image1/2/3) are the user's/Claude's responsibility here.
        base = req.prompt.strip()
        if build_text:
            base = f"{base} {build_text}"
        text, sanitised = promptlib.sanitise(base)
    else:
        pose_text = promptlib.POSES_LIBRARY.get(req.pose_id or "", "")
        text, sanitised = promptlib.compose_tagged(
            req.brief, pose_text=pose_text, has_wardrobe=has_wardrobe,
            pose_ref_tag=pose_ref_tag, build_text=build_text, shot_type=req.shot_type)
    label = req.brief.strip()[:60] or "untitled shot"
    session = generate.new_session(label)

    def run(job: dict) -> dict:
        return generate.generate(
            prompt=text, system="", refs=refs, aspect=req.aspect,
            seed=req.seed, session=session, progress=job,
            # If gpt-image-2 refuses a revealing outfit on content_policy, render
            # it on the scene model instead (weaker identity, recorded) rather
            # than dead-spinning to a failure.
            fallback_endpoint=SCENE_EDIT,
            resolution=req.resolution,
            meta={"brief": req.brief, "bio_references": [p.name for p in refs],
                  "wardrobe": req.wardrobe_id, "pose_id": req.pose_id,
                  "pose_ref": req.pose_ref_id, "sanitised": sanitised,
                  "ai_prompt": bool(req.prompt and req.prompt.strip())},
        )

    jid = generate.start_job(label, run)
    return {"job": jid, "sanitised": sanitised}


@app.get("/api/jobs/{jid}")
def job(jid: str):
    st = generate.job_status(jid)
    if st is None:
        raise HTTPException(404, jid)
    return st


class ShotPreviewReq(BaseModel):
    brief: str = ""
    wardrobe_id: str | None = None
    pose_id: str | None = None
    shot_type: str = "candid"


@app.post("/api/shot/preview")
def shot_preview(req: ShotPreviewReq):
    pose_text = promptlib.POSES_LIBRARY.get(req.pose_id or "", "")
    text, sanitised = promptlib.compose_tagged(
        req.brief, pose_text=pose_text, has_wardrobe=bool(req.wardrobe_id),
        build_text=promptlib.build_clause(_load_parts()), shot_type=req.shot_type)
    tags = ["@image1 = face"]
    if req.wardrobe_id:
        tags.append(f"@image2 = outfit ({req.wardrobe_id})")
    else:
        tags.append("@image2 = body/build")
    return {"prompt": text, "chars": len(text), "reference": _bio_ref(),
            "image_tags": tags, "sanitised": sanitised}


# ------------------------------------------------------ learning from approvals
# Human approvals drive LEARNING — but never the gallery. Feeding approved output
# back into the yardstick drifts it toward the generator (the number climbs while
# the identity walks away; see gate.py). So approvals do two SAFE things instead:
#   1. Analytics — keep-rate by pose/outfit, so you learn which recipes work.
#   2. A gold set — the curated dataset a future LoRA trains on, kept apart from
#      the frozen gate.

def _shots() -> list[dict]:
    """Runs that are actual shots (have a brief) — not calibration/body/outfit gen."""
    return [r for r in generate.all_runs() if "brief" in (r.get("meta") or {})]


@app.get("/api/stats")
def stats():
    rows = _shots()
    total = len(rows)

    def rate(sub, key):
        n = len(sub)
        return round(sum(1 for r in sub if (r.get(key[0]) or {}).get(key[1]) == key[2]) / n, 3) if n else 0.0

    def bucket(keyfn):
        b: dict[str, dict] = {}
        for r in rows:
            k = keyfn(r) or "—"
            e = b.setdefault(k, {"key": k, "n": 0, "kept": 0, "approved": 0})
            e["n"] += 1
            if (r.get("verdict") or {}).get("status") == "kept":
                e["kept"] += 1
            if r.get("mark") == "approve":
                e["approved"] += 1
        out = []
        for e in b.values():
            e["keep_rate"] = round(e["kept"] / e["n"], 2)
            e["approve_rate"] = round(e["approved"] / e["n"], 2)
            out.append(e)
        return sorted(out, key=lambda e: (-e["n"], e["key"]))

    kept = sum(1 for r in rows if (r.get("verdict") or {}).get("status") == "kept")
    approved = sum(1 for r in rows if r.get("mark") == "approve")
    rejected = sum(1 for r in rows if r.get("mark") == "reject")
    return {
        "total": total,
        "gate": {"kept": kept, "keep_rate": round(kept / total, 2) if total else 0},
        "marks": {"approved": approved, "rejected": rejected,
                  "unmarked": total - approved - rejected},
        "gold_set": approved,
        "gold_on_disk": len(list(GOLD.glob("*.png"))),
        "by_pose": bucket(lambda r: (r.get("meta") or {}).get("pose_id")),
        "by_outfit": bucket(lambda r: (r.get("meta") or {}).get("wardrobe")),
    }


@app.post("/api/gold/export")
def gold_export():
    """Copy every human-APPROVED shot into data/gold/ — the curated LoRA dataset.

    Approvals accumulate here, NEVER in the gallery: the gallery is the frozen
    yardstick, and feeding generated output back into it drifts the measure. The
    gold set is a separate artifact — the training data for a future Flux LoRA.
    """
    GOLD.mkdir(exist_ok=True)
    n = 0
    for r in _shots():
        if r.get("mark") == "approve":
            src = IMAGES / r["file"]
            if src.exists():
                shutil.copy2(src, GOLD / r["file"])
                n += 1
    return {"exported": n, "gold_on_disk": len(list(GOLD.glob("*.png"))),
            "path": str(GOLD)}


@app.post("/api/runs/purge-rejected")
def purge_rejected():
    """Delete every human-REJECTED shot — image, thumbnail and ledger row. At
    ~20 MB apiece the rejects pile up fast; this reclaims the disk in one go."""
    ids = {r["id"] for r in generate.all_runs() if r.get("mark") == "reject"}
    removed = generate.delete_runs(ids)
    freed = 0
    for r in removed:
        p = IMAGES / r["file"]
        if p.exists():
            freed += p.stat().st_size
            p.unlink(missing_ok=True)
        (THUMBS / f"{Path(r['file']).stem}.jpg").unlink(missing_ok=True)
    return {"deleted": len(removed), "freed_mb": round(freed / 1e6, 1)}


@app.get("/api/health")
def health():
    return {"ok": True, "root": str(ROOT)}
