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
from .config import IMAGES, PARTS_PATH, POSES, REFS, ROOT

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


@app.get("/api/health")
def health():
    return {"ok": True, "root": str(ROOT)}
