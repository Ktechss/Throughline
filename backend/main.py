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

from . import gate, generate, prompt as promptlib, skeleton
from .config import (IMAGES, PARTS_PATH, POSE_REFS, POSES, REFS, ROOT, STATE,
                     WARDROBE)

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


# NOTE: there is deliberately no endpoint to promote a GENERATED image into the
# gallery. The gallery is the source of truth and is seeded only from
# data/refs (see /api/gallery/from-ref). Admitting our own output would let the
# yardstick drift with the thing it measures — the previous project's namesake
# sheet ended up disagreeing with ten of its own descendants that way. If you
# want a generated image to become a reference, import it deliberately as a ref
# first; that way it is a decision with a filename, not a side effect.


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
    """Changing this changes who Kiara is for every future generation."""
    if not (REFS / Path(req.reference).name).exists():
        raise HTTPException(400, f"no such reference: {req.reference}")
    BIO_REF_PATH.write_text(json.dumps({"reference": Path(req.reference).name},
                                       indent=2) + "\n")
    return {"reference": Path(req.reference).name}


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


class OutfitCreateReq(BaseModel):
    name: str
    outfit: str          # free text: "white crop top, baggy jeans, strappy heels"


@app.post("/api/wardrobe/create")
def wardrobe_create(req: OutfitCreateReq):
    """Generate the outfit ONTO her as a clean white-studio reference.

    This is the ai-influencer technique for good wardrobe: instead of uploading
    an arbitrary outfit photo (which drags in a stranger's face, a scene, and a
    conflicting framing), we generate HER wearing the outfit on plain white — a
    clean swatch. Used later as @image2, it injects only the clothing, because
    that is all that varies from her own references.

    Identity comes from her face + body references; the prompt changes only the
    outfit and pins the background to white so nothing else leaks.
    """
    face = REFS / _bio_ref()
    if not face.exists():
        raise HTTPException(400, "no BIO reference set")
    refs = [face]
    body = REFS / _bio_cfg()["body_reference"]
    if body.exists():
        refs.append(body)

    safe = "".join(c for c in req.name if c.isalnum() or c in "-_ ").strip() or "outfit"
    prompt = (
        f"Full-body studio photograph of @image1 standing and facing the camera "
        f"on a plain white seamless studio background, soft even lighting, her "
        f"whole outfit visible head to toe. She is wearing: {req.outfit}. Change "
        f"ONLY her clothing to this outfit; keep her face, body, proportions, "
        f"skin and hair exactly as in the references. Photorealistic, real skin "
        f"texture, no retouching.")

    def run(job: dict) -> dict:
        row = generate.generate(prompt=prompt, system="", refs=refs, aspect="3:4",
                                session=generate.new_session(f"create outfit: {safe}"),
                                progress=job, meta={"outfit_create": req.outfit})
        # Save the generated image as a clean wardrobe reference.
        shutil.copy2(IMAGES / row["file"], WARDROBE / f"{safe}.png")
        row["wardrobe_saved"] = safe
        return row

    jid = generate.start_job(f"create outfit: {safe}", run)
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
    pose_name: str | None = None
    use_pose_image: bool = False
    aspect: str = "3:4"
    seed: int | None = None
    wardrobe_id: str | None = None   # attach this saved outfit as @image2
    pose_id: str | None = None       # a pose from the text library
    pose_ref_id: str | None = None   # a pose REFERENCE image, attached as @image3
    shot_type: str = "candid"


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
        refs.append(w)          # @image2 = outfit
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

    pose_text = promptlib.POSES_LIBRARY.get(req.pose_id or "", "")
    text, sanitised = promptlib.compose_tagged(
        req.brief, pose_text=pose_text, has_wardrobe=has_wardrobe,
        pose_ref_tag=pose_ref_tag, shot_type=req.shot_type)
    label = req.brief.strip()[:60] or "untitled shot"
    session = generate.new_session(label)

    def run(job: dict) -> dict:
        return generate.generate(
            prompt=text, system="", refs=refs, aspect=req.aspect,
            seed=req.seed, session=session, progress=job,
            meta={"brief": req.brief, "bio_references": [p.name for p in refs],
                  "wardrobe": req.wardrobe_id, "pose_id": req.pose_id,
                  "pose_ref": req.pose_ref_id, "sanitised": sanitised},
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
        shot_type=req.shot_type)
    tags = ["@image1 = face"]
    if req.wardrobe_id:
        tags.append(f"@image2 = outfit ({req.wardrobe_id})")
    else:
        tags.append("@image2 = body/build")
    return {"prompt": text, "chars": len(text), "reference": _bio_ref(),
            "image_tags": tags, "sanitised": sanitised}


@app.get("/api/health")
def health():
    return {"ok": True, "root": str(ROOT)}
