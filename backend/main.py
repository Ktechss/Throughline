"""FastAPI app behind the React UI.

    # Linux / WSL
    .venv/bin/python -m uvicorn backend.main:app --reload --port 8000
    # Windows
    .venv-win\\Scripts\\python.exe -m uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import shutil

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import (config, db, describe, gate, generate, prompt as promptlib, prompter,
               skeleton, timeline)
from .config import (ARCHIVE_FORMAT, ARCHIVE_QUALITY, BODIES, BODIES_META,
                     CHARACTERS, CharPath, GOLD, HOME_PATH,
                     IMAGES, NAILS, NAILS_META, PARTS_PATH, PLACES, POSE_REFS,
                     POSES, REF_BUDGET, REFS, ROOT, SCENE_EDIT, SCENE_TEXT2IMG,
                     STATE, TIMELINE_PATH, WARDROBE)

app = FastAPI(title="Throughline")

# Create tables + import the JSON ledgers once (idempotent — only imports while a
# table is still empty). Runs, videos and wardrobe meta now live in eve1.db; the
# JSON files stay on disk as a cold backup. See backend/db.py.
db.init_db()

# Vite dev server. Same-origin in production; this is for `npm run dev`.
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


# ------------------------------------------------------------ characters
# Phase 4: Throughline is a multi-character studio. The landing page lists these; each
# has its own folder, gallery (identity), bio, wardrobe and generations. All the
# path constants above follow whichever character is ACTIVE (see config.CharPath).

def _slug(name: str) -> str:
    s = "".join(c if (c.isalnum() or c in " -_") else "" for c in name).strip()
    s = "-".join(s.lower().split())
    return s or "character"


def _unique_char_id(name: str) -> str:
    base = _slug(name)
    existing = {c["id"] for c in db.chars_all()}
    cid, n = base, 2
    while cid in existing or (CHARACTERS / cid).exists():
        cid, n = f"{base}-{n}", n + 1
    return cid


def _char_avatar_src(cid: str) -> Path | None:
    """Best image to represent a character on its card: its BIO face if set, else
    any reference, else its newest generated shot. None while still un-calibrated."""
    base = config.char_base(cid)
    bio = base / "state" / "bio.json"
    if bio.exists():
        try:
            ref = json.loads(bio.read_text()).get("reference")
            p = base / "refs" / Path(ref).name if ref else None
            if p and p.exists():
                return p
        except Exception:  # noqa: BLE001
            pass
    for sub in ("refs", "images"):
        d = base / sub
        if d.exists():
            imgs = [x for x in sorted(d.iterdir())
                    if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
                    and not x.name.startswith(".")]
            if imgs:
                return imgs[-1] if sub == "images" else imgs[0]
    return None


def _char_has_identity(cid: str) -> bool:
    return (config.char_base(cid) / "state" / "gallery.npz").exists()


def _char_view(c: dict) -> dict:
    return {**c, "has_identity": _char_has_identity(c["id"]),
            "has_avatar": _char_avatar_src(c["id"]) is not None,
            "active": c["id"] == config.get_active()}


@app.get("/api/characters")
def list_characters():
    return {"active": config.get_active(),
            "characters": [_char_view(c) for c in db.chars_all()]}


@app.get("/api/characters/active")
def get_active_character():
    return {"id": config.get_active()}


class ActiveReq(BaseModel):
    id: str


@app.put("/api/characters/active")
def set_active_character(req: ActiveReq):
    if not db.chars_get(req.id):
        raise HTTPException(404, req.id)
    config.ensure_char_dirs(req.id)
    config.set_active(req.id)
    return {"id": req.id}


class CharacterReq(BaseModel):
    name: str


@app.post("/api/characters")
def create_character(req: CharacterReq):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    cid = _unique_char_id(name)
    config.ensure_char_dirs(cid)          # blank folder skeleton
    row = db.chars_create(cid, name)
    config.set_active(cid)                # drop the user straight into the new one
    return _char_view(row)


@app.put("/api/characters/{cid}")
def rename_character(cid: str, req: CharacterReq):
    """Rename a character (display name only — the id/folder are stable)."""
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    if not db.chars_update(cid, name):
        raise HTTPException(404, cid)
    row = db.chars_get(cid)
    return _char_view(row)


# The standard face shapes the picker offers. "" = let Claude decide from the
# description (the diverse default).
FACE_SHAPES = ["oval", "round", "square", "heart", "diamond", "oblong"]

# Body builds the picker offers. The EXPLICIT figure text drives the body-ref
# generation (a clothed solo figure on the permissive model, so strong shape
# wording is safe there and renders the build faithfully — text alone in the bio
# regresses to slim). The FRAME text is the tasteful version stored in the bio and
# attached to every shot.
BUILDS = ["slim", "athletic", "curvy", "voluptuous", "full-figured"]
_BUILD_FIGURE = {
    "slim": "a slim, slender build with a narrow frame and a modest bust",
    "athletic": "a toned, athletic build — lean and fit with subtle muscle definition",
    "curvy": "a curvy hourglass figure: a full rounded bust, a clearly defined narrow waist, and full rounded hips",
    "voluptuous": "a dramatically curvy, voluptuous hourglass: a very full, heavy bust, a deeply cinched narrow waist, and wide, full, rounded hips; distinctly full-figured, not slim",
    "full-figured": "a full-figured, plus-size build: a full bust, a soft rounded midsection, and wide, full hips",
}
_BUILD_FRAME = {
    "slim": "slim, slender build",
    "athletic": "toned athletic build",
    "curvy": "curvy hourglass",
    "voluptuous": "pronounced curvy, full-figured hourglass",
    "full-figured": "soft, full-figured build",
}


def _height_text(cm: int) -> str:
    total_in = round(cm / 2.54)
    return f"{cm}cm ({total_in // 12}'{total_in % 12}\")"


@app.post("/api/characters/guided")
async def create_character_guided(
    name: str = Form(...),
    description: str = Form(""),
    face_shape: str = Form(""),
    build: str = Form(""),
    height_cm: str = Form(""),
    home_style: str = Form(""),
    home_surroundings: str = Form(""),
    reference: UploadFile | None = File(None),
):
    """Create a character from her three defining pieces — BIO, BODY and HOME.

    Those three are what a character IS here, and the flow is built to say so:
    everything else (wardrobe, poses, nails) is per-shoot dressing that can be
    thrown away and remade, while these are the things that, if lost, mean you
    no longer have her. So creation writes her bio, generates her first face and
    a body reference matching the chosen build, sets the face as the calibration
    seed, and then builds her flat — one image per corner, from one shared house
    style, so her home is a real place from the first shot rather than a room
    invented afresh every time a brief mentions a kitchen.

    Returns a job id; the slow work runs in the background (poll /api/jobs/{id}).
    """
    name = name.strip()
    if not name:
        raise HTTPException(400, "name required")
    shape = face_shape.strip().lower()
    if shape and shape not in FACE_SHAPES:
        shape = ""
    build = build.strip().lower()
    if build and build not in BUILDS:
        build = ""
    try:
        height = int(float(height_cm))
        if not (120 <= height <= 210):
            height = 0
    except (ValueError, TypeError):
        height = 0

    cid = _unique_char_id(name)
    config.ensure_char_dirs(cid)
    char = db.chars_create(cid, name)
    config.set_active(cid)                # the build job runs on the now-active char

    seed_upload: Path | None = None
    if reference is not None:
        data = await reference.read()
        if data:
            ext = Path(reference.filename or "seed.png").suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                ext = ".png"
            seed_upload = _unique_ref_path(f"seed-upload{ext}")
            seed_upload.write_bytes(data)

    def run(job: dict) -> dict:
        # 1) Claude writes her identity fields; the explicit pickers OVERRIDE
        job["stage"] = "writing bio"
        parts = _load_parts()
        writable = [p for p in parts
                    if p.section in ("subject", "face", "hair", "skin", "body")
                    and p.id != "subject.energy"]
        fields = [{"id": p.id, "label": p.label, "hint": p.text} for p in writable]
        desc = description
        if shape:
            desc += f"\nHer face shape is {shape}."
        if build:
            desc += f"\nHer body build is {build}."
        if height:
            desc += f"\nHer height is {_height_text(height)}."
        try:
            updates = prompter.write_bio(name, desc, fields)
        except prompter.PrompterError as exc:
            updates = {}
            job["note"] = f"bio auto-write skipped ({exc}); used defaults"
        # the pickers are authoritative — apply them ON TOP of the AI's text
        if shape:
            cur = updates.get("face.shape", "")
            if shape not in cur.lower():
                updates["face.shape"] = f"a {shape} face" + (f", {cur}" if cur else "")
        if build:
            updates["body.frame"] = _BUILD_FRAME[build]
        if height:
            updates["body.height"] = _height_text(height)
        if updates:
            parts = [promptlib.Part(**{**p.dict(), "text": updates.get(p.id, p.text)})
                     for p in parts]
            _save_parts(parts)

        # 2) generate her first face
        job["stage"] = "generating face"
        if seed_upload and seed_upload.exists():
            # Base her on the reference's LIKENESS, but always render a REAL,
            # photorealistic human — so a stylised/anime/drawn reference becomes a
            # believable real person, never reproduced as art. (A strict identity
            # copy here made an anime upload come back as anime — wrong for the
            # realistic pipeline and the ArcFace gate.)
            prompt = (
                "A photorealistic portrait headshot of a REAL human woman whose "
                "face is based on @image1. Take her facial features, structure, "
                "hairstyle and overall likeness from @image1, but render her as a "
                "real, photorealistic human being with natural skin and true human "
                "anatomy. If @image1 is a drawing, anime or stylised art, "
                "reinterpret it faithfully as a believable real person with those "
                "same features. Head-and-shoulders framing, plain neutral studio "
                "background, soft even lighting, looking into the lens, natural "
                "relaxed expression. Photorealistic RAW photo, real skin texture "
                "and pores, sharp focus on the face — never illustrated, cartoon "
                "or CGI.")
            row = generate.generate(
                prompt=prompt, refs=[seed_upload], aspect="3:4",
                session=generate.new_session(f"seed face: {name}"), progress=job,
                meta={"guided_seed": True, "from_upload": True})
        else:
            portrait = promptlib.compose(
                parts, has_reference=False,
                pose_note="a clean, well-lit frontal headshot — head and shoulders, "
                          "plain neutral studio background, looking straight into "
                          "the lens, natural relaxed expression")
            row = generate.generate(
                prompt=portrait, refs=None, aspect="3:4",
                session=generate.new_session(f"seed face: {name}"), progress=job,
                meta={"guided_seed": True})

        # 3) set the generated face as the CALIBRATION SEED
        src = IMAGES / row["file"]
        seed_ref = None
        if src.exists():
            seed_ref = _promote(src, _unique_ref_path("seed-face.png"))
            cfg = _bio_cfg_raw()
            cfg["calib_seed"] = seed_ref.name
            BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
            row.setdefault("meta", {})["seed_ref"] = seed_ref.name

        # 4) generate a BODY reference matching the chosen build — the strong lever
        #    for proportions. Explicit figure text renders the build faithfully;
        #    best-effort, so a body failure never breaks the character.
        if seed_ref and seed_ref.exists():
            job["stage"] = "generating body"
            figure = _BUILD_FIGURE.get(build) or promptlib.build_clause(parts)
            body_prompt = (
                "Full-body studio photograph of @image1 on a plain white seamless "
                "background, lit flat and even. She stands straight and relaxed "
                "facing the camera, arms at her sides, neutral expression, wearing "
                "simple fitted plain activewear (a fitted tank top and leggings) so "
                "her figure is clearly visible. Her FIGURE is the whole point of "
                "this image: render her exact build faithfully and prominently, "
                f"never substituting a generic slim fashion-model physique. Her "
                f"build: {figure}. Her face and identity exactly match @image1. "
                "Photorealistic, real skin texture, natural anatomy.")
            try:
                body_row = generate.generate(
                    prompt=body_prompt, refs=[seed_ref], aspect="3:4",
                    session=generate.new_session(f"body: {name}"), progress=job,
                    meta={"body_ref_create": True, "guided": True},
                    fallback_endpoint=SCENE_EDIT)
                bsrc = IMAGES / body_row["file"]
                if bsrc.exists():
                    bdst = _promote(bsrc, REFS / "body-canonical.png")
                    cfg = _bio_cfg_raw()
                    cfg["body_reference"] = bdst.name
                    BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
                    row.setdefault("meta", {})["body_ref"] = bdst.name
            except Exception as exc:  # noqa: BLE001 — body is a bonus, not required
                job["note"] = f"body generation skipped ({exc})"

        # 5) HOME — the third of her three defining pieces. Ten corners from one
        #    shared house style, so "her kitchen" means one specific kitchen from
        #    the first shot onward.
        #
        #    Gated on the style text being present: with nothing to describe the
        #    house, ten generations buy ten unrelated generic rooms — real spend
        #    for something the Home tab can do better later, once she has a home
        #    worth describing. Silence here is a deliberate skip, and it is said
        #    out loud in the job note rather than left to be discovered.
        style = home_style.strip()
        if style or home_surroundings.strip():
            HOME_PATH.write_text(json.dumps(
                {"style": style, "surroundings": home_surroundings.strip()},
                indent=2) + "\n")
        if style:
            done, failed = 0, []
            for i, corner in enumerate(HOME_CORNERS, 1):
                job["step"] = f"{corner['label']} ({i}/{len(HOME_CORNERS)})"
                try:
                    _render_corner(corner["key"], job)
                    done += 1
                except Exception as exc:  # noqa: BLE001 — one bad room is not a bad character
                    failed.append(f"{corner['key']} ({exc})")
            job["step"] = None
            row.setdefault("meta", {})["home_corners"] = done
            if failed:
                job["note"] = f"home corners skipped: {', '.join(failed)}"
        else:
            job["note"] = ("home skipped — no house style given; "
                           "generate corners from the Home tab")
        return row

    jid = generate.start_job(f"create {name}", run)
    return {"character": _char_view(char), "job": jid}


@app.get("/api/characters/{cid}/avatar")
def character_avatar(cid: str):
    src = _char_avatar_src(cid)
    if not src:
        raise HTTPException(404, "no avatar yet")
    cache = config.char_base(cid) / "state" / ".avatar.jpg"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        from PIL import Image
        im = Image.open(src).convert("RGB")
        im.thumbnail((512, 512))
        im.save(cache, "JPEG", quality=82)
    return FileResponse(cache)


@app.delete("/api/characters/{cid}")
def delete_character(cid: str):
    if not db.chars_get(cid):
        raise HTTPException(404, cid)
    if cid == config.get_active():
        raise HTTPException(400, "switch to another character before deleting this one")
    if len(db.chars_all()) <= 1:
        raise HTTPException(400, "cannot delete the last character")
    db.chars_delete(cid)
    folder = CHARACTERS / cid
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True, "deleted": cid}


# ---------------------------------------------------------------- parts

def _load_parts() -> list[promptlib.Part]:
    if PARTS_PATH.exists():
        stored = [promptlib.Part(**d) for d in json.loads(PARTS_PATH.read_text())]
        # Backfill: append any NEW default parts (e.g. grooming/accessories added
        # after this character was saved) without touching the user's edits.
        have = {p.id for p in stored}
        added = [p for p in promptlib.default_parts() if p.id not in have]
        if added:
            stored += added
            _save_parts(stored)
        return stored
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


# Generated images and wardrobe turnarounds are 3584x4800 / ~18-20 MB each. A grid
# rendering the full files downloads hundreds of MB (the wardrobe strip alone was
# ~433 MB) and decodes each to a huge bitmap in the browser — it sinks the UI.
# Grids request this cached ~512px JPEG thumbnail instead; the full image is only
# fetched in a detail view.
def _serve_thumb(src_dir: Path, name: str, box: tuple[int, int] = (512, 512)):
    src = src_dir / Path(name).name
    if not src.exists():
        raise HTTPException(404, name)
    cache_dir = src_dir / ".thumbs"
    cache_dir.mkdir(exist_ok=True)
    cache = cache_dir / f"{Path(name).stem}.jpg"
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        from PIL import Image
        im = Image.open(src).convert("RGB")
        im.thumbnail(box)
        im.save(cache, "JPEG", quality=80)
    return FileResponse(cache)


@app.get("/api/images/{name}/thumb")
def image_thumb(name: str):
    return _serve_thumb(IMAGES, name)


@app.get("/api/wardrobe/{name}/thumb")
def wardrobe_thumb(name: str):
    return _serve_thumb(WARDROBE, name, (256, 384))


@app.get("/api/pose-refs/{name}/thumb")
def pose_ref_thumb(name: str):
    return _serve_thumb(POSE_REFS, name, (256, 384))


@app.get("/api/refs/{name}/thumb")
def ref_thumb(name: str):
    return _serve_thumb(REFS, name, (256, 384))


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


class GalleryRemoveReq(BaseModel):
    name: str


@app.post("/api/gallery/remove")
def gallery_remove(req: GalleryRemoveReq):
    """Remove ONE entry from the identity gallery (e.g. a bad seed) without wiping
    the whole fingerprint, then re-derive the threshold from what remains."""
    if not gate.remove_from_gallery(req.name):
        raise HTTPException(404, req.name)
    recalibrated = False
    try:
        gate.calibrate_from_gallery()
        recalibrated = True
    except Exception:  # noqa: BLE001 — too few entries left to calibrate is fine
        pass
    return {"ok": True, "removed": req.name, "recalibrated": recalibrated,
            "remaining": sorted(gate.load_gallery())}


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
    """Generate `count` canonical headshots (identity-locked) on the primary model.

    Faces are generated from the calibration SEED, not the BIO reference — so the
    uploaded seed drives calibration without ever becoming the default identity.
    """
    cfg = _bio_cfg()
    seed_name = cfg.get("calib_seed") or cfg.get("reference")
    face = REFS / Path(seed_name).name if seed_name else None
    if not face or not face.exists():
        raise HTTPException(400, "no calibration seed — upload a base image first (Step 1)")
    n = max(1, min(req.count, len(CALIB_FACES)))
    jobs = []
    for angle, desc in CALIB_FACES[:n]:
        prompt = (f"Headshot portrait of @image1 — {desc}. Plain neutral studio "
                  f"background, soft even lighting, head and shoulders framing. "
                  f"{IDENTITY_LOCK_LINE} Photorealistic, real skin texture, sharp "
                  f"focus on the face.")

        def run(job: dict, prompt=prompt, angle=angle) -> dict:
            row = generate.generate(
                prompt=prompt, system="", refs=[face], aspect="3:4",
                session=generate.new_session(f"calib face: {angle}"), progress=job,
                meta={"calibrate": "face", "angle": angle})
            # Keep EVERY generated calibration face in the reference library
            # (advanced · face) so nothing is ever lost — the candidate copy in
            # data/images can be purged, but this ref persists. The user curates
            # and deletes by hand; we never drop one automatically. No-clobber
            # naming means repeated calibrations accumulate (calib-front-1, …).
            try:
                src = IMAGES / row["file"]
                if src.exists():
                    dst = _unique_ref_path(f"calib-{angle}.png")
                    shutil.copy2(src, dst)
                    row.setdefault("meta", {})["calib_ref"] = dst.name
            except Exception:  # noqa: BLE001 — a failed copy must not fail the gen
                pass
            return row

        jobs.append({"angle": angle, "job": generate.start_job(f"calib {angle}", run)})
    return {"jobs": jobs}


@app.get("/api/calibrate/candidates")
def calibrate_candidates():
    """Generated calibration faces awaiting selection, newest first.

    Skip any whose image file is gone — a deleted image must not resurface as an
    empty ghost card. The ledger row is the record; the file is the picture.
    """
    out = []
    for r in generate.all_runs():
        if r.get("meta", {}).get("calibrate") == "face" and (IMAGES / r["file"]).exists():
            out.append({"id": r["id"], "file": r["file"],
                        "angle": r.get("meta", {}).get("angle"),
                        "verdict": r.get("verdict", {})})
    return {"candidates": out[:60]}


class CalibSeedReq(BaseModel):
    reference: str


@app.post("/api/calibrate/seed")
def set_calib_seed(req: CalibSeedReq):
    """Set the calibration seed — the image faces are generated FROM.

    Deliberately NOT `PUT /api/bio/reference`: an uploaded calibration image must
    never silently become the default BIO identity. That only happens when the
    user promotes a generated face (⭐ identity → /api/bio/reference/from-run).
    """
    name = Path(req.reference).name
    if not (REFS / name).exists():
        raise HTTPException(400, f"no such reference: {name}")
    cfg = _bio_cfg_raw()
    cfg["calib_seed"] = name
    BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    return {"calib_seed": name}


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


def _unique_ref_path(filename: str) -> Path:
    """Never clobber an existing reference. Overwriting a ref in place rewrites
    history: every past run records the ref's *filename*, so if that name later
    points at different bytes, the run's provenance silently lies (and old
    origin panels show the wrong face). If the name is taken, suffix it
    (-1, -2, …) so a changed identity becomes a NEW file and old runs keep
    resolving to the exact image they used.
    """
    p = REFS / Path(filename or "reference.png").name
    if not p.exists():
        return p
    stem, suf = p.stem, p.suffix
    n = 1
    while (REFS / f"{stem}-{n}{suf}").exists():
        n += 1
    return REFS / f"{stem}-{n}{suf}"


@app.post("/api/refs/import")
def import_ref(req: ImportReq):
    """Copy a local image in as an identity reference.

    Copied, not linked: a reference that can move or be deleted out from under
    the pipeline is a reference that will silently change who she is.
    """
    src = Path(req.path)
    if not src.exists() or not src.is_file():
        raise HTTPException(400, f"no such file: {req.path}")
    dest = _unique_ref_path(src.name)
    shutil.copy2(src, dest)
    info = _ref_info(dest)
    if not info["usable"]:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"no face detected in {src.name} — not a usable "
                                 f"identity reference")
    return info


@app.post("/api/refs/upload")
async def upload_ref(file: UploadFile = File(...)):
    dest = _unique_ref_path(file.filename)
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

BIO_REF_PATH = CharPath("state", "bio.json")   # per-character (follows the active one)

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
            "body_reference": cfg.get("body_reference", DEFAULT_BODY_REF),
            # The calibration SEED is the image faces are generated FROM during
            # calibration. It is deliberately SEPARATE from `reference` (the
            # default BIO identity attached to every shot): uploading a seed must
            # never silently become the default identity. The BIO identity is set
            # only by promoting a generated nano-native face (⭐ identity).
            "calib_seed": cfg.get("calib_seed")}


def _bio_cfg_raw() -> dict:
    """The bio.json as stored, WITHOUT injecting the Kiara.png / cd-body.png
    defaults. Use this for read-modify-WRITE: writing _bio_cfg() would bake the
    original character's reference into every new character's bio.json (the
    reference/body stay unset until calibration promotes a real face)."""
    return json.loads(BIO_REF_PATH.read_text()) if BIO_REF_PATH.exists() else {}


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


# ArcFace analysis of a reference costs ~1s. The reference is stable, so cache the
# metrics by (path, mtime, size) — this is what made switching characters feel slow
# (get_bio re-embedded the face on every switch). Different characters have
# different reference paths, so each gets its own entry; editing a ref busts it.
_FACE_CACHE: dict = {}


def _face_metrics(path: Path) -> dict:
    p = Path(path)
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key not in _FACE_CACHE:
        f = gate.analyze(p)   # may raise NoFaceFound / ValueError
        _FACE_CACHE[key] = {"face_px": f.width, "yaw": round(f.yaw, 1),
                            "pose_class": f.pose_class}
    return _FACE_CACHE[key]


@app.get("/api/bio")
def get_bio():
    """Who the active character is. Locked, and attached to every shot."""
    parts = _load_parts()
    cfg = _bio_cfg()
    ref_path = REFS / cfg["reference"]
    body_path = REFS / cfg["body_reference"]
    out = promptlib.bio_summary(parts, has_reference=ref_path.exists())
    out["reference"] = cfg["reference"] if ref_path.exists() else None
    out["body_reference"] = cfg["body_reference"] if body_path.exists() else None
    if ref_path.exists():
        try:
            out["reference_face"] = _face_metrics(ref_path)
        except (gate.NoFaceFound, ValueError):
            out["reference_face"] = None
    # calibration seed — the image faces are generated from (NOT the default BIO)
    seed = cfg.get("calib_seed")
    seed_path = REFS / Path(seed).name if seed else None
    out["calib_seed"] = seed if (seed_path and seed_path.exists()) else None
    if out["calib_seed"]:
        try:
            out["calib_seed_face"] = _face_metrics(seed_path)
        except (gate.NoFaceFound, ValueError):
            out["calib_seed_face"] = None
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
    cfg = _bio_cfg_raw()
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
    row = next((r for r in generate.all_runs() if r["id"] == run_id), None)
    if not row:
        raise HTTPException(404, run_id)
    # Name the identity per-character (e.g. robin-identity.png). A shared name
    # ('kiara-identity.png' for everyone) made the thumbnail URL identical across
    # profiles, so the browser served a CACHED face from another character even
    # though the file on disk was correct. Per-character names keep URLs distinct.
    cid = config.get_active()
    dest = _promote(IMAGES / row["file"], REFS / f"{cid}-identity.png")
    try:
        gate.analyze(dest)   # must contain a detectable face
    except (gate.NoFaceFound, ValueError):
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "no face detected in that image") from None
    cfg = _bio_cfg_raw()
    cfg["reference"] = dest.name
    BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    return {"reference": dest.name}


class BodyRefCreateReq(BaseModel):
    shape: str | None = None       # optional shape override; else uses the body parts
    shape_ref: str | None = None   # optional body-SHAPE reference image (filename in refs)
    turnaround: bool = False       # full-body 4-view sheet (front/side/back/¾) like wardrobe


@app.post("/api/bio/shape-ref/upload")
async def upload_shape_ref(file: UploadFile = File(...)):
    """Upload a body-SHAPE reference — a figure whose proportions to match.

    No face required (a shape ref is often a headless/faceless body), so this
    skips the face check that /api/refs/upload enforces. Identity never comes
    from here — only the silhouette/proportions do.
    """
    dest = _unique_ref_path(file.filename or "shape-ref.png")
    dest.write_bytes(await file.read())
    return {"name": dest.name}


@app.post("/api/bio/body-ref/create")
def body_ref_create(req: BodyRefCreateReq):
    """Generate a canonical BODY image from the face + body-shape text, and
    OPTIONALLY a body-shape reference image (@image2) to hit an exact figure.

    Text alone specifies a *type* and the model regresses toward slim; a shape
    reference pins the exact silhouette. Identity always stays with @image1 —
    only the proportions come from the shape ref. Review the preview, then save
    it as the body reference; every shot then inherits those proportions.
    """
    face = REFS / _bio_ref()
    if not face.exists():
        raise HTTPException(400, "no BIO face reference set")
    shape = (req.shape or "").strip() or promptlib.build_clause(_load_parts())
    shape_clean, _ = promptlib.sanitise(shape)   # size passes now; nudity still guarded

    refs = [face]
    shape_ref_clause = ""
    if req.shape_ref:
        sp = REFS / Path(req.shape_ref).name
        if not sp.exists():
            raise HTTPException(400, f"no such shape reference: {req.shape_ref}")
        refs.append(sp)
        # Same exclusion shape as the wardrobe/pose directives: take ONLY the
        # figure from @image2, never the face — an angled/other face there costs
        # identity (measured this session; see the angle-body-ref finding).
        shape_ref_clause = (
            " Match her body proportions, figure and silhouette to @image2 — the "
            "same build, the same bust-to-waist-to-hip ratio and curves. Take ONLY "
            "the body shape and proportions from @image2; her face, identity, skin, "
            "hair and features come only from @image1, never from @image2.")

    if req.turnaround:
        # Full-body 4-view sheet — same format as the wardrobe turnaround, so the
        # body ref anchors her figure from every angle (front/side/back/¾).
        prompt = (
            "Professional full-body character turnaround sheet. Pure white "
            "seamless background throughout. Soft neutral studio lighting, "
            "perfectly flat and even across all four panels, no shadows.\n\n"
            "A single row of FOUR equally sized FULL-BODY panels — head to toe, "
            "feet visible in every panel — each with a small label in clean "
            'sans-serif capitals above the figure: "FRONT VIEW" | "SIDE VIEW" | '
            '"BACK VIEW" | "THREE-QUARTER VIEW". Panel 1 front-facing, panel 2 '
            "exact side profile, panel 3 facing directly away, panel 4 at a "
            "45-degree three-quarter angle.\n\n"
            "The woman is @image1 — replicate her face, bone structure, skin and "
            "hair exactly in every panel. Her FIGURE is the whole point of this "
            "sheet: render her exact build faithfully and prominently as "
            "specified below, never substituting a generic slim fashion-model "
            f"physique. {shape_clean}{shape_ref_clause} She "
            "wears simple fitted plain activewear (a fitted tank top and "
            "leggings) so her figure and proportions are clearly visible. "
            "Identical figure, proportions, stance and lighting across all four "
            "panels.\n\nPhotorealistic RAW photograph quality, real skin texture, "
            "ultra-sharp detail.")
        aspect, extra = "16:9", {"image_size": {"width": 1536, "height": 1024}}
    else:
        prompt = (
            "Full-body studio photograph of @image1 on a plain white seamless "
            "background, lit flat and even. She stands straight and relaxed "
            "facing the camera, arms at her sides, neutral expression, wearing "
            "simple fitted plain activewear (a fitted tank top and leggings) so "
            "her figure and proportions are clearly visible. Her FIGURE is the "
            "whole point of this image: render her exact build faithfully and "
            "prominently as specified, never substituting a generic slim "
            f"fashion-model physique. {shape_clean}{shape_ref_clause} Her face "
            "and identity exactly match @image1. Photorealistic, real skin "
            "texture, natural anatomy.")
        aspect, extra = "3:4", None

    def run(job: dict) -> dict:
        return generate.generate(
            prompt=prompt, system="", refs=refs, aspect=aspect,
            session=generate.new_session("body reference"), progress=job,
            meta={"body_ref_create": True, "shape": shape_clean,
                  "shape_ref": req.shape_ref, "turnaround": req.turnaround},
            fallback_endpoint=SCENE_EDIT, extra=extra)

    return {"job": generate.start_job("body reference", run)}


@app.post("/api/bio/body-ref/save")
def body_ref_save(payload: dict = Body(...)):
    """Lock a generated body image in as the BODY reference (@image2 everywhere)."""
    run_id = payload["run_id"]
    row = next((r for r in generate.all_runs() if r["id"] == run_id), None)
    if not row:
        raise HTTPException(404, run_id)
    dest = _promote(IMAGES / row["file"], REFS / "body-canonical.png")
    cfg = _bio_cfg_raw()
    cfg["body_reference"] = dest.name
    BIO_REF_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    return {"body_reference": dest.name}


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
    _promote(IMAGES / row["file"], BODIES / f"{safe}.png")
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
    dest = _promote(src, REFS / "body-canonical.png")   # the active body reference
    cfg = _bio_cfg_raw()
    cfg["body_reference"] = dest.name
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


class BodyRenameReq(BaseModel):
    name: str


@app.put("/api/bodies/{name}")
def body_rename(name: str, req: BodyRenameReq):
    """Rename a body type (moves its image + updates the id and active pointer)."""
    old = Path(name).stem
    new = "".join(c for c in req.name if c.isalnum() or c in "-_ ").strip()
    if not new:
        raise HTTPException(400, "name required")
    data = _bodies()
    b = next((x for x in data["bodies"] if x["id"] == old), None)
    if not b:
        raise HTTPException(404, name)
    if new != old:
        if any(x["id"] == new for x in data["bodies"]):
            raise HTTPException(400, f"a body named '{new}' already exists")
        (BODIES / f"{old}.png").replace(BODIES / f"{new}.png")
        b["id"] = new
        if data.get("active") == old:
            data["active"] = new
        _save_bodies(data)
    return {"id": new}


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


_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _promote(src: Path, dest: Path) -> Path:
    """Copy a generated image into a saved slot, KEEPING the source's format.

    Generated output is archived as WebP (config.ARCHIVE_*), so a destination
    spelled `.png` would write a WebP file wearing a PNG extension — readable,
    because PIL sniffs content, but a lie on disk and to anything that trusts the
    name. Callers name the slot they want; the real suffix is decided here, and
    callers that persist a filename persist the returned one.

    Safe to point at a fixed slot: any same-stem image already there is removed
    first, so switching body-canonical from .png to .webp cannot leave two files
    with one of them stale and both resolvable by `_find_by_id`.
    """
    dest = dest.with_suffix(src.suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    for stale in dest.parent.glob(f"{dest.stem}.*"):
        if stale != dest and stale.suffix.lower() in _IMAGE_EXT:
            stale.unlink(missing_ok=True)
    shutil.copy2(src, dest)
    return dest


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


def _wardrobe_meta() -> dict:
    return db.wardrobe_meta()


def _save_wardrobe_meta(d: dict) -> None:
    db.wardrobe_save_all(d)


def _wardrobe() -> list[dict]:
    meta = _wardrobe_meta()
    out = []
    for p in sorted(WARDROBE.iterdir()) if WARDROBE.exists() else []:
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            m = meta.get(p.stem, {})
            out.append({"id": p.stem, "file": p.name,
                        "description": m.get("description"),
                        "category": m.get("category") or "",
                        "created": m.get("created")})
    return out


def _unique_wardrobe_path(name: str) -> Path:
    """No-clobber outfit filename: never overwrite an existing outfit (that is how
    an image and a different outfit's description desync). Suffixes -2, -3, … ."""
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ").strip() or "outfit"
    safe = "-".join(safe.split())
    if not (WARDROBE / f"{safe}.png").exists():
        return WARDROBE / f"{safe}.png"
    n = 2
    while (WARDROBE / f"{safe}-{n}.png").exists():
        n += 1
    return WARDROBE / f"{safe}-{n}.png"


def _canon_category(category: str) -> str:
    """Canonical category / name-prefix: alnum only, first letter upper (e.g.
    'day out' -> 'Dayout', 'night' -> 'Night')."""
    c = "".join(ch for ch in (category or "") if ch.isalnum())
    return (c[0].upper() + c[1:]) if c else "Outfit"


def _next_wardrobe_name(category: str) -> str:
    """Auto-name an outfit as <Category><next number> — the number continues that
    category's existing sequence (Dayout1..9 -> Dayout10)."""
    import re
    cat = _canon_category(category)
    mx = 0
    for p in (WARDROBE.iterdir() if WARDROBE.exists() else []):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        m = re.match(rf"^{re.escape(cat)}(\d+)$", p.stem, re.IGNORECASE)
        if m:
            mx = max(mx, int(m.group(1)))
        elif p.stem.lower() == cat.lower():
            mx = max(mx, 1)   # an unnumbered existing outfit counts as #1
    return f"{cat}{mx + 1}"


# The wardrobe turnaround is a photo of HER wearing the outfit, so it carries a
# competing face — measured to drag a headshot's identity ~0.85 -> ~0.64 even
# with the "clothing only" directive. Crop the head off so @image2 is the garment
# alone and identity comes solely from @image1 — the project's own "crop faces
# off references" rule, applied to the wardrobe. Cached in a hidden subdir so the
# crops never appear as wardrobe items themselves.
OUTFIT_CROPS = CharPath("wardrobe", ".outfitcrops")   # per-character crop cache


def _outfit_ref(path: Path) -> Path:
    """Clothing-only version of a wardrobe image: head cropped off. Falls back to
    the original if no face is found or the face already fills the frame."""
    from PIL import Image
    OUTFIT_CROPS.mkdir(exist_ok=True)
    # Archive format, not PNG: these are crops of 4K turnarounds, and as PNG the
    # cache grew to 1.4 GB — larger than the wardrobe it was derived from, for
    # files that are rebuilt on demand and never shown to anyone.
    cache = OUTFIT_CROPS / f"{path.stem}.{ARCHIVE_FORMAT}"
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return cache
    (OUTFIT_CROPS / f"{path.stem}.png").unlink(missing_ok=True)   # pre-WebP crop
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
    im.crop((0, top, W, H)).save(cache, ARCHIVE_FORMAT.upper(),
                                 quality=ARCHIVE_QUALITY or 95, method=4)
    return cache


@app.get("/api/wardrobe")
def list_wardrobe():
    return {"wardrobe": _wardrobe()}


@app.post("/api/wardrobe/upload")
async def wardrobe_upload(file: UploadFile = File(...), category: str = Form("")):
    """An outfit is saved as a reference image. It becomes @image2 on any shot
    that selects it, with a 'reproduce exactly' directive — the fix for the
    wardrobe leak, since the outfit now comes from its own reference rather than
    losing a text tug-of-war with the identity photo. No-clobber name so an
    upload can't overwrite an existing outfit."""
    cat = _canon_category(category) if (category or "").strip() else ""
    name = _next_wardrobe_name(cat) if cat else Path(file.filename or "outfit").stem
    dest = _unique_wardrobe_path(name)
    dest.write_bytes(await file.read())
    if cat:
        meta = _wardrobe_meta()
        meta[dest.stem] = {"description": None, "category": cat, "created": None}
        _save_wardrobe_meta(meta)
    return {"id": dest.stem, "file": dest.name, "category": cat}


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


class OutfitEnrichReq(BaseModel):
    base: str = ""       # existing description (e.g. from a described image) to enrich
    idea: str = ""
    occasion: str = ""
    style: str = ""
    fabric: str = ""
    silhouette: str = ""
    formality: str = ""
    season: str = ""


@app.post("/api/wardrobe/enrich")
def wardrobe_enrich(req: OutfitEnrichReq):
    """ENRICH an outfit description with Claude. Primary flow: the user uploads an
    outfit photo, describe reads it into `base`, and this rewrites it far richer
    and more precise (same garments) with the picks as optional adaptations. With
    no base it writes a fresh outfit from idea + picks. Stateless — the result
    fills the editable outfit box; the user then generates via /api/wardrobe/create.
    """
    try:
        outfit = prompter.write_outfit(
            req.base, req.idea, occasion=req.occasion, style=req.style,
            fabric=req.fabric, silhouette=req.silhouette,
            formality=req.formality, season=req.season)
    except prompter.PrompterError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"outfit": _clean_outfit_text(outfit)}


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
                                 # A turnaround is a garment swatch, not a photo of
                                 # her — /api/wardrobe/from-run uses only its clothing.
                                 # Gating it scores whichever of its four panels
                                 # renders the biggest face, at ~200px: 116 of 118 were
                                 # rejected for face size alone. Not a measurement.
                                 gated=False,
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
    run_id = payload["run_id"]
    category = _canon_category(payload.get("category") or payload.get("name") or "")
    if not (payload.get("category") or payload.get("name")):
        raise HTTPException(400, "category required")
    row = next((r for r in generate.all_runs() if r["id"] == run_id), None)
    if not row:
        raise HTTPException(404, run_id)
    # Auto-name <Category><next#>; no-clobber as a final safety net.
    dest = _promote(IMAGES / row["file"], _unique_wardrobe_path(_next_wardrobe_name(category)))
    # Persist the description it was made with + its category, keyed to THIS file's
    # stem, so image and description can never belong to different outfits.
    meta = _wardrobe_meta()
    meta[dest.stem] = {"description": row.get("meta", {}).get("outfit_create"),
                       "category": category, "created": row.get("created")}
    _save_wardrobe_meta(meta)
    return {"id": dest.stem, "file": dest.name, "category": category}


@app.get("/api/wardrobe/{name}/file")
def wardrobe_file(name: str):
    p = WARDROBE / Path(name).name
    if not p.exists():
        raise HTTPException(404, name)
    return FileResponse(p)


class WardrobeEditReq(BaseModel):
    category: str | None = None
    description: str | None = None


@app.put("/api/wardrobe/{name}")
def wardrobe_update(name: str, req: WardrobeEditReq):
    """Edit an outfit's category and/or description. The id/file are unchanged so
    every @image2 reference stays stable (no rename)."""
    stem = Path(name).stem
    meta = _wardrobe_meta()
    if stem not in meta:
        raise HTTPException(404, name)
    if req.category is not None and req.category.strip():
        meta[stem]["category"] = req.category.strip()
    if req.description is not None:
        meta[stem]["description"] = req.description
    _save_wardrobe_meta(meta)
    return {"id": stem, **meta[stem]}


@app.delete("/api/wardrobe/{name}")
def wardrobe_delete(name: str):
    stem = Path(name).stem
    (WARDROBE / Path(name).name).unlink(missing_ok=True)
    meta = _wardrobe_meta()
    if stem in meta:
        del meta[stem]
        _save_wardrobe_meta(meta)
    return {"ok": True}


@app.get("/api/pose-library")
def list_pose_library():
    poses = [{"id": pid, "text": text, "category": cat}
             for cat, group in promptlib.POSE_GROUPS.items()
             for pid, text in group.items()]
    return {"poses": poses, "categories": list(promptlib.POSE_GROUPS)}


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
    dest = _promote(IMAGES / row["file"], POSE_REFS / f"{safe}.png")
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


# ---------------------------------------------------------------- nail styles
# A per-character library of manicure reference images. A shot can attach one as
# an extra @image reference (exact nail match) — it costs a reference slot, which
# measurably lowers identity, a trade the user opts into per shot.

def _nails_meta() -> dict:
    if NAILS_META.exists():
        try:
            return json.loads(NAILS_META.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_nails_meta(d: dict) -> None:
    NAILS_META.write_text(json.dumps(d, indent=2) + "\n")


def _nails() -> list[dict]:
    meta = _nails_meta()
    out = []
    for p in sorted(NAILS.iterdir()) if NAILS.exists() else []:
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            m = meta.get(p.stem, {}) or {}
            out.append({"id": p.stem, "file": p.name,
                        "name": m.get("name") or p.stem,
                        "category": m.get("category") or "Uncategorized",
                        "description": m.get("description", "")})
    return out


@app.get("/api/nails")
def list_nails():
    return {"nails": _nails()}


def _next_nail_name(color: str) -> str:
    """<color><n> — n is one past the highest existing index for that colour."""
    color = (color or "other").strip().lower() or "other"
    nums = []
    for m in _nails_meta().values():
        if (m.get("category") or "").strip().lower() == color:
            nm = (m.get("name") or "").strip().lower()
            if nm.startswith(color) and nm[len(color):].isdigit():
                nums.append(int(nm[len(color):]))
    return f"{color}{max(nums) + 1 if nums else 1}"


@app.post("/api/nails/upload")
async def nails_upload(file: UploadFile = File(...), color: str = Form("")):
    """Save a manicure reference image. Colour is the category; the name is
    auto-assigned as <colour><n>. Image-only — no description/Claude call (the
    image is used directly as the reference)."""
    data = await file.read()
    Path(NAILS).mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"
    i = 1
    while _find_by_id(NAILS, f"nail{i}"):
        i += 1
    dest = NAILS / f"nail{i}{ext}"
    dest.write_bytes(data)
    color = (color.strip().lower() or "other")
    name = _next_nail_name(color)
    meta = _nails_meta()
    meta[dest.stem] = {"name": name, "category": color, "description": ""}
    _save_nails_meta(meta)
    return {"id": dest.stem, "file": dest.name, "name": name, "category": color, "description": ""}


class NailDescReq(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None


@app.put("/api/nails/{name}")
def nails_update(name: str, req: NailDescReq):
    stem = Path(name).stem
    meta = _nails_meta()
    cur = meta.get(stem, {}) or {}
    if req.name is not None:
        cur["name"] = req.name.strip() or stem
    if req.category is not None:
        cur["category"] = req.category.strip() or "Uncategorized"
    if req.description is not None:
        cur["description"] = req.description
    meta[stem] = cur
    _save_nails_meta(meta)
    return {"id": stem, **cur}


@app.get("/api/nails/{name}/file")
def nails_file(name: str):
    p = NAILS / Path(name).name
    if not p.exists():
        raise HTTPException(404, name)
    return FileResponse(p)


@app.get("/api/nails/{name}/thumb")
def nails_thumb(name: str):
    return _serve_thumb(NAILS, name, (256, 256))


@app.delete("/api/nails/{name}")
def nails_delete(name: str):
    stem = Path(name).stem
    (NAILS / Path(name).name).unlink(missing_ok=True)
    meta = _nails_meta()
    if stem in meta:
        del meta[stem]
        _save_nails_meta(meta)
    return {"ok": True}


# ---------------------------------------------------------------- home (BIO)
# Her home is part of her BIO: a fixed set of house corners, each with one image
# (uploaded OR generated from a shared house style). A shot whose brief names a room
# auto-attaches that corner's image as the environment reference, so her home stays
# the same house across shots. Corner images live in places/<key>.*; style in home.json.

HOME_CORNERS = [
    {"key": "bedroom", "label": "Bedroom", "keywords": ["bedroom", "in bed", "her bed"],
     "gen": "a cosy bedroom — a made bed with layered linens, a nightstand, a soft rug, warm ambient light"},
    {"key": "living_room", "label": "Living room", "keywords": ["living room", "couch", "sofa", "lounge"],
     "gen": "a living room — a comfortable sofa, coffee table, shelving, plants, large windows"},
    {"key": "kitchen", "label": "Kitchen", "keywords": ["kitchen", "cooking", "at the counter"],
     "gen": "a kitchen — counters, cabinets, an island with stools, tasteful appliances"},
    {"key": "dining", "label": "Dining area", "keywords": ["dining", "dining table", "dinner table"],
     "gen": "a dining area — a dining table with chairs, a pendant light overhead"},
    {"key": "bathroom", "label": "Bathroom / vanity", "keywords": ["bathroom", "vanity", "at the mirror", "washroom"],
     "gen": "a clean modern bathroom — a vanity with a large mirror, sink, soft lighting"},
    {"key": "office", "label": "Home office / desk", "keywords": ["office", "study", "at her desk", "working from home", "desk"],
     "gen": "a home office — a desk with a laptop, an ergonomic chair, shelves, a pinboard"},
    {"key": "balcony", "label": "Balcony", "keywords": ["balcony"],
     "gen": "a balcony — a railing, potted plants, a small chair, an open view beyond"},
    {"key": "entryway", "label": "Entryway / hallway", "keywords": ["entryway", "hallway", "foyer", "entrance", "doorway"],
     "gen": "an entryway/hallway — a console table, a mirror, hooks, a runner rug"},
    {"key": "closet", "label": "Walk-in closet", "keywords": ["closet", "wardrobe", "dressing room", "getting dressed"],
     "gen": "a walk-in closet — racks of hanging clothes, shelves of shoes, a full-length mirror, soft lighting"},
    {"key": "terrace", "label": "Rooftop / terrace / garden", "keywords": ["terrace", "rooftop", "garden", "patio", "backyard"],
     "gen": "a rooftop terrace / garden — plants, comfortable outdoor seating, string lights, an open sky"},
]
# The places OUTSIDE the flat that she returns to.
#
# A real life happens in a small number of repeated places. Someone's year of
# photos is mostly the same gym, the same café, the same desk, the same platform
# — not a hundred locations visited once each, which is what a brief-driven
# pipeline produces by default and which reads as a travel brochure rather than a
# person. These use the same storage, upload and generate machinery as the home
# corners; the only difference is that they are hers-but-public, so an "away"
# brief SHOULD match one, where it must never match her bathroom.
REGULAR_PLACES = [
    {"key": "reg_gym", "label": "Her gym", "keywords": ["gym", "workout", "weights", "treadmill"],
     "gen": "a mid-size city gym floor — racks and machines, rubber flooring, wall mirrors, "
            "strip lighting, a water station"},
    {"key": "reg_cafe", "label": "Her café", "keywords": ["cafe", "café", "coffee shop", "espresso"],
     "gen": "a small neighbourhood café — a counter with a espresso machine, mismatched wooden "
            "tables, plants, menu board, big street-facing windows"},
    {"key": "reg_desk", "label": "Her work desk", "keywords": ["at work", "the office", "her desk at work", "workplace"],
     "gen": "one desk in an open-plan office — a monitor, a laptop on a stand, a mug, a lanyard, "
            "low partitions and other desks behind"},
    {"key": "reg_commute", "label": "Her metro station", "keywords": ["metro", "station", "platform", "commute", "train"],
     "gen": "an elevated urban metro platform — tiled floor, yellow safety line, overhead signage, "
            "a train approaching, city buildings beyond"},
    {"key": "reg_street", "label": "Her street", "keywords": ["her street", "outside her building", "her block", "downstairs"],
     "gen": "a residential city street outside an apartment block — parked two-wheelers, a "
            "compound wall, shop shutters, overhead cables, trees"},
]

# Merged so upload / generate / file / thumb / delete work by key for both kinds.
_CORNER = {c["key"]: c for c in [*HOME_CORNERS, *REGULAR_PLACES]}
_REGULAR_KEYS = {c["key"] for c in REGULAR_PLACES}
# Only these rooms open to the outside — the balcony/window VIEW (buildings, street,
# skyline) belongs here and NOWHERE else. Every other corner is a fully interior room.
_VIEW_ROOMS = {"balcony", "terrace", "living_room"}


def _home() -> dict:
    if HOME_PATH.exists():
        try:
            d = json.loads(HOME_PATH.read_text())
            return {"style": (d.get("style") or "").strip(),
                    "surroundings": (d.get("surroundings") or "").strip()}
        except Exception:  # noqa: BLE001
            pass
    return {"style": "", "surroundings": ""}


def _corner_file(key: str) -> Path | None:
    """The stored image for a corner, whatever its extension."""
    return _find_by_id(PLACES, key)


@app.get("/api/home")
def get_home():
    h = _home()
    corners = []
    for c in HOME_CORNERS:
        f = _corner_file(c["key"])
        corners.append({"key": c["key"], "label": c["label"], "view": c["key"] in _VIEW_ROOMS,
                        "has_image": bool(f), "file": f.name if f else None})
    # Her regulars ride the same storage and the same /api/home/{key} endpoints —
    # listed separately only because the UI groups "her flat" and "places she
    # goes" differently, and because an away brief treats them oppositely.
    regulars = []
    for c in REGULAR_PLACES:
        f = _corner_file(c["key"])
        regulars.append({"key": c["key"], "label": c["label"], "view": False,
                         "has_image": bool(f), "file": f.name if f else None})
    return {"style": h["style"], "surroundings": h["surroundings"],
            "corners": corners, "regulars": regulars}


class HomeStyleReq(BaseModel):
    style: str = ""
    surroundings: str = ""


@app.put("/api/home")
def set_home_style(req: HomeStyleReq):
    data = {"style": req.style.strip(), "surroundings": req.surroundings.strip()}
    HOME_PATH.write_text(json.dumps(data, indent=2) + "\n")
    return data


@app.post("/api/home/{key}/upload")
async def home_upload(key: str, file: UploadFile = File(...)):
    if key not in _CORNER:
        raise HTTPException(400, f"unknown corner: {key}")
    data = await file.read()
    Path(PLACES).mkdir(parents=True, exist_ok=True)
    old = _corner_file(key)      # replace any existing image for this corner
    if old:
        old.unlink(missing_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"
    dest = PLACES / f"{key}{ext}"
    dest.write_bytes(data)
    return {"key": key, "file": dest.name}


def _corner_prompt(key: str) -> str:
    """The scene prompt for one corner, from the shared house style + corner type.

    Split out of the endpoint so guided character creation builds her whole flat
    through exactly the same wording the Home tab uses — one house, one prompt,
    whichever door you came in by.
    """
    corner = _CORNER[key]
    h = _home()
    style, surroundings = h["style"], h["surroundings"]

    # The house is ONE coherent space. The outside view belongs only to rooms that
    # open outward (balcony/terrace/living room); every other corner is a fully
    # interior room and must NOT show the city/buildings/street — that leak is the
    # bug this scoping fixes.
    if key in _REGULAR_KEYS:
        # Not her home — a public place she returns to. The house style and the
        # interior-only scoping both belong to the flat and would actively fight
        # a gym or a metro platform, so neither applies here.
        base = (f"A photorealistic photograph of {corner['gen']}. One specific, "
                f"real, slightly worn everyday place — the same one every time, "
                f"not a showroom version of it.")
    elif key in _VIEW_ROOMS:
        base = (f"A photorealistic photograph of {corner['gen']}, part of one real home."
                + (f" Home style and materials: {style}." if style else "")
                + (f" The outside view visible from here: {surroundings}." if surroundings else ""))
    else:
        base = (f"A photorealistic INTERIOR photograph of {corner['gen']} — one enclosed "
                f"interior room inside one real home."
                + (f" Overall home style and materials: {style}." if style else "")
                + " This is an INTERIOR room, fully indoors: do NOT show any city "
                "skyline, buildings, streets, flyover/overbridge or any outdoor/exterior "
                "view of the city. If a window appears it shows only soft, blurred "
                "daylight or plain sky — never identifiable buildings or a cityscape. "
                "Show ONLY this room, not other rooms.")
    prompt, _ = promptlib.sanitise(
        base + " Cohesive, lived-in, real home — NOT a showroom or staged catalogue. "
        "Natural available light, realistic materials. NO people, no text or logos. "
        "Shot on a phone, wide 24mm-equivalent lens, natural.")
    return prompt


def _render_corner(key: str, job: dict) -> dict:
    """Generate one corner and drop it into its slot. Shared by the Home tab and
    guided character creation."""
    corner = _CORNER[key]
    Path(PLACES).mkdir(parents=True, exist_ok=True)
    row = generate.generate(
        prompt=_corner_prompt(key), system="", refs=None, aspect="4:3",
        endpoint=SCENE_TEXT2IMG, session=generate.new_session(f"home: {corner['label']}"),
        # An empty room has no face in it by design ("NO people" above), so
        # gating one only ever records no_face — a failure that isn't one.
        gated=False,
        progress=job, meta={"home_create": key})
    src = IMAGES / row["file"]
    if src.exists():
        _promote(src, PLACES / f"{key}.png")
    return row


@app.post("/api/home/{key}/generate")
def home_generate(key: str):
    """Generate this corner from the shared house style + the corner type, and save
    it to the corner slot. Async — returns a job to poll. No people in the shot."""
    if key not in _CORNER:
        raise HTTPException(400, f"unknown corner: {key}")
    corner = _CORNER[key]
    jid = generate.start_job(f"home: {corner['label']}",
                             lambda job: _render_corner(key, job))
    return {"job": jid}


@app.get("/api/home/{key}/file")
def home_file(key: str):
    f = _corner_file(key)
    if not f:
        raise HTTPException(404, key)
    return FileResponse(f)


@app.get("/api/home/{key}/thumb")
def home_thumb(key: str):
    f = _corner_file(key)
    if not f:
        raise HTTPException(404, key)
    return _serve_thumb(PLACES, f.name, (320, 240))


@app.delete("/api/home/{key}")
def home_delete(key: str):
    f = _corner_file(key)
    if f:
        f.unlink(missing_ok=True)
    return {"ok": True}


# Places that are emphatically NOT her flat. A home corner is a literal, forceful
# instruction — "the location is exactly the room shown in @imageN … do not invent
# or substitute a different room" — attached to a real photo of her home. So an
# ambiguous room noun is dangerous: "washroom", "at the mirror", "desk" and "bar"
# all exist outside the house too. Measured in the wild: "during the interval she
# went to the washroom" at a CINEMA matched the bathroom corner and rendered her
# home bathroom, reference photo and all. When the brief puts her somewhere else,
# infer nothing and let the brief describe the place.
_AWAY_MARKERS = (
    "cinema", "movie", "theatre", "theater", "multiplex", "mall", "restaurant",
    "cafe", "café", "coffee shop", "hotel", "airport", "terminal", "station",
    "metro", "train", "flight", "museum", "gallery", "stadium", "concert",
    "gym", "salon", "spa", "clinic", "hospital", "temple", "church", "market",
    "shop", "store", "supermarket", "beach", "park", "street", "road",
    "college", "university", "school", "campus", "wedding", "party", "club",
    "pub", "rooftop bar", "workplace", "went out", "out for", "outside",
    "on the way", "public",
)


def _infer_place(brief: str) -> tuple[Path | None, str]:
    """The place image this brief should be anchored to, and which kind it is.

    Her REGULARS are tried first and are never suppressed: they are places she
    goes precisely when she is out, so "at the gym" should pin her gym.

    Home corners are only inferred when nothing marks her as away — see
    `_AWAY_MARKERS`. Silently anchoring a shot to her flat because a word like
    "washroom" appeared is worse than not anchoring it at all: the caller asked
    for a cinema and got her bathroom, with no visible reason why.
    """
    b = (brief or "").lower()
    for c in REGULAR_PLACES:
        if any(k in b for k in c["keywords"]):
            f = _corner_file(c["key"])
            if f:
                return f, "regular"
    if any(m in b for m in _AWAY_MARKERS):
        return None, ""
    for c in HOME_CORNERS:
        if any(k in b for k in c["keywords"]):
            f = _corner_file(c["key"])
            if f:
                return f, "home"
    return None, ""


# ----------------------------------------------------------------- her timeline
# The eras a year of shots is drawn against. Deliberately thin: an era is a date
# she changed visibly, and what changed. Everything else about a date (season,
# manicure wear) is derived, so there is nothing here to keep in sync.
@app.get("/api/shot/options")
def shot_options():
    """The axes a shot can be varied along, for the UI to render as pickers.

    `face` on a camera holder is the expected face size it produces — the same
    axis `gate.FACE_PLATEAU_PX` is about, surfaced at the point of choosing so the
    identity cost of a wide shot is visible before it is paid rather than after.
    """
    return {
        "shot_types": [{"id": k, "label": v} for k, v in promptlib.SHOT_TYPES.items()],
        "camera_holders": [{"id": k, **v} for k, v in promptlib.CAMERA_HOLDERS.items()],
        "flaws": [{"id": k, **v} for k, v in promptlib.SNAPSHOT_FLAWS.items()],
    }


@app.get("/api/timeline")
def get_timeline():
    tl = timeline.load(TIMELINE_PATH)
    today = date.today()
    clause, facts = timeline.clause(today, tl, sorted(_nails_meta()))
    return {"eras": tl.get("eras") or [], "today": facts, "preview": clause}


@app.put("/api/timeline")
def put_timeline(payload: dict = Body(...)):
    """Replace the era list. Each entry: {from: YYYY-MM-DD, name?, hair?, note?}."""
    eras = payload.get("eras")
    if not isinstance(eras, list):
        raise HTTPException(400, "eras must be a list")
    for e in eras:
        if not isinstance(e, dict):
            raise HTTPException(400, "each era must be an object")
        try:
            date.fromisoformat(str(e.get("from", "")))
        except ValueError:
            raise HTTPException(400, f"era needs a valid 'from' date: {e!r}") from None
    TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TIMELINE_PATH.write_text(json.dumps({"eras": eras}, indent=2) + "\n")
    return {"eras": eras}


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
    pose_text: str | None = None     # raw pose text, overrides the library lookup —
                                     # lets a past shot's pose be reused even after the
                                     # library is regenerated and its id is orphaned
    pose_ref_id: str | None = None   # a pose REFERENCE image, attached as @image3
    nail_id: str | None = None       # a manicure reference image, attached as @imageN
    shot_type: str = "candid"
    resolution: str | None = None    # "1K" | "2K" | "4K" (nano). None -> config default
    face_accessories: bool = True    # render face-worn items (sunglasses/hats) from the
                                     # outfit; off = keep her face clear (better identity)
    pov: bool = False                # faceless first-person POV product/lifestyle shot —
                                     # the face ref anchors skin tone but stays out of frame;
                                     # nails/setting/outfit are the anchors, gate is N/A
    ref_budget: bool = False         # OFF by default, deliberately. Holding a shot to
                                     # REF_BUDGET buys ~0.04 of similarity and costs the
                                     # nail/pose/place REFERENCE IMAGES, which is a bad
                                     # trade: a demoted nail becomes its description, and
                                     # most nails have none — picking nail15 sent the
                                     # model the words "yellow nails" and dropped the
                                     # manicure entirely. Opt in per shot when identity
                                     # matters more than the extras.
    date: str | None = None          # ISO date this shot happens on. None = today
    use_timeline: bool = False       # OFF by default: appending season/manicure text to
                                     # every shot changes output nobody asked to change.
                                     # Set true (with a date) when you WANT the year to
                                     # show — monsoon light, a manicure at its end
    camera_holder: str = ""          # who took it: selfie/mirror/friend/stranger/timer.
                                     # Also a face-size lever — see CAMERA_HOLDERS
    flaws: str = ""                  # "" | subtle | snapshot. Deliberate imperfection;
                                     # "snapshot" is expected to score low, by design


class AiPromptReq(BaseModel):
    brief: str = ""
    wardrobe_id: str | None = None
    pose_id: str | None = None
    pose_text: str | None = None     # raw pose text override (reused orphaned pose)
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
    pose_text = req.pose_text or promptlib.POSES_LIBRARY.get(req.pose_id or "", "")
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

    # ------------------------------------------------------------------ the date
    # When this shot happens. Season, hair era and the manicure cycle all fall out
    # of it, which is what makes a year of images a year rather than a catalogue.
    # A nail choice from the calendar is a DEFAULT: an explicit pick always wins,
    # so the cycle never overrides a deliberate one.
    try:
        when = (date.fromisoformat(req.date) if req.date else date.today())
    except ValueError as exc:
        raise HTTPException(400, f"bad date {req.date!r}: expected YYYY-MM-DD") from exc
    tl_clause, tl_facts = timeline.clause(
        when, timeline.load(TIMELINE_PATH), sorted(_nails_meta()))
    if not req.use_timeline:
        # Recorded but not applied: the date still lands in meta so a set can be
        # ordered later, while the prompt stays exactly what the caller asked for.
        tl_clause = ""
        tl_facts = {"date": when.isoformat(), "applied": False}
    # The calendar only ever supplies a manicure when the timeline is in use; an
    # explicit pick always wins either way.
    nail_id = req.nail_id or (tl_facts.get("nail_id") if not req.pov else None)

    # ---------------------------------------------------------- reference budget
    # Every reference past the second measurably costs identity. Measured on this
    # project's own runs (2026-08-02), comparing only shots at a matched face size
    # of 400-600px so framing can't explain it: 2 refs scored 0.622 (n=54), 3 refs
    # 0.579 (n=23). Barely 0.006 of that gap is the yaw difference between the
    # groups. FINDINGS saw the same shape harder still — three face crops scored
    # 0.547 against one crop's 0.811 — and gives the reason: more references don't
    # give the model more identity, they give it more to BLEND.
    #
    # So slots are spent, not accumulated. @image1 (face) and @image2 (outfit or
    # build) are the two that earn their place; everything after competes with
    # them. An extra is DEMOTED to its text form where it has one — text costs no
    # slot — and only dropped when it has none. Never silently: whatever gets
    # demoted is recorded in meta and returned to the caller, and `ref_budget=false`
    # turns the whole thing off for a shot that genuinely needs the image.
    budget_left = max(0, REF_BUDGET - len(refs)) if req.ref_budget else 99
    demoted: list[str] = []

    # An AI prompt is used VERBATIM and was written against the tags that existed
    # when Claude wrote it — /api/shot/ai-prompt hands it "@image3" for a pose ref.
    # Demoting that ref afterwards would leave the prompt pointing at an image the
    # model never receives, which is worse than spending the slot. So a tag the
    # prompt already names is not up for demotion.
    verbatim = (req.prompt or "").strip() if not req.pov else ""

    # @image3 = pose reference (her, in the desired pose/head orientation). Its text
    # form is the pose library entry — but only if the user actually picked one, so
    # a pose ref used ALONE is kept rather than silently losing the pose entirely.
    pose_ref_tag = ""
    if req.pose_ref_id:
        pr = _find_by_id(POSE_REFS, req.pose_ref_id)
        if not pr:
            raise HTTPException(400, f"no such pose reference: {req.pose_ref_id}")
        has_pose_text = bool(req.pose_text or promptlib.POSES_LIBRARY.get(req.pose_id or ""))
        if budget_left > 0 or not has_pose_text or "@image3" in verbatim:
            refs.append(pr)
            pose_ref_tag = f"@image{len(refs)}"
            budget_left -= 1
        else:
            demoted.append("pose-ref (using the pose text instead)")

    # @imageN = manicure reference (her nail design). Cheapest thing to demote: the
    # saved nail description carries shape, colour and finish as words.
    nail_tag = ""
    nail_desc = ""
    if nail_id:
        nail = _find_by_id(NAILS, nail_id)
        if not nail:
            raise HTTPException(400, f"no such nail style: {nail_id}")
        nm = _nails_meta().get(nail_id, {}) or {}
        nail_desc = (nm.get("description") or "").strip()
        if not nail_desc:
            # No written description; the category is at least the colour family,
            # which is enough to keep a calendar-picked manicure out of a ref slot.
            cat = (nm.get("category") or "").strip()
            nail_desc = f"{cat} nails" if cat else ""
        # An image slot is only ever spent on a manicure the USER asked for. The
        # calendar picks one for every shot, and letting that buy a reference
        # would quietly put every shot over budget — which is the exact cost this
        # section exists to stop.
        explicit = bool(req.nail_id)
        if budget_left > 0 or (explicit and not nail_desc):
            # The tag is positional, so compute it before appending.
            nail_tag = f"@image{len(refs) + 1}"
            refs.append(nail)
            budget_left -= 1
        elif explicit:
            demoted.append("nail-ref (using its description instead)")

    # @imageN = home corner, inferred from the brief. If the brief names a room she
    # has an image for, anchor the setting to HER home so it stays the same house.
    # Inferred, never asked for — so it yields first when the budget is tight, and
    # it has no text form to fall back to.
    place_tag = ""
    home_corner, place_kind = _infer_place(req.brief)
    if home_corner:
        if budget_left > 0:
            place_tag = f"@image{len(refs) + 1}"
            refs.append(home_corner)
            budget_left -= 1
        else:
            home_corner, place_kind = None, ""
            demoted.append("place-ref (setting comes from the brief instead)")

    # Body-shape tuning from the editable body parts — folded into BOTH paths so
    # bust/waist/hips edits actually change the output. The AI prompter is barred
    # from describing her body, so it's appended after Claude's scene prompt.
    _parts = _load_parts()
    build_text = promptlib.build_clause(_parts)
    # Standing grooming/accessories — the objects that recur across her whole
    # year. A specific manicure (chosen or from the calendar) already speaks for
    # her nails, so the generic nails part stands down rather than contradicting it.
    carry_text = promptlib.carry_clause(
        _parts, skip={"grooming.nails"} if nail_id else set())
    # POV is a specific faceless first-person framing that a generic AI prompt (which
    # references @image1 and describes her posing) would fight — so POV always uses
    # the template's POV branch and ignores any AI prompt.
    if req.prompt and req.prompt.strip() and not req.pov:
        # AI-written (and user-edited) prompt: use it verbatim, only running the
        # moderation sanitiser so a trigger can't slip through. The reference
        # tags (@image1/2/3) are the user's/Claude's responsibility here.
        base = req.prompt.strip()
        if build_text:
            base = f"{base} {build_text}"
        if carry_text:
            base = f"{base} {carry_text}"
        # Same treatment as the build clause: appended rather than handed to
        # Claude. Who held the camera and how imperfect the frame is are
        # photographic facts, and an AI prompt written before they were chosen
        # would otherwise contradict them.
        holder = (promptlib.CAMERA_HOLDERS.get(req.camera_holder) or {}).get("text", "")
        if holder:
            base = f"{base} {holder}"
        # A pose picked alongside an AI prompt must still take effect — otherwise a
        # multi-pose batch reuses the one pose already frozen into the AI prompt and
        # every image comes back in the same stance. Append the chosen pose as an
        # explicit override so the picker wins over whatever pose the prompt describes.
        pose_text = req.pose_text or promptlib.POSES_LIBRARY.get(req.pose_id or "", "")
        if pose_text:
            base = (f"{base} For THIS shot her body pose is: {pose_text} "
                    "Use exactly this pose, overriding any other stance, gesture or "
                    "body position described above; keep the same scene, framing, "
                    "outfit, lighting and identity.")
        # Flaws last, for the same reason as in compose_tagged: they qualify the
        # sharpness the prompt above asks for, and the later line wins.
        flaw = (promptlib.SNAPSHOT_FLAWS.get(req.flaws) or {}).get("text", "")
        if flaw:
            base = f"{base} {flaw}"
        text, sanitised = promptlib.sanitise(base)
    else:
        pose_text = req.pose_text or promptlib.POSES_LIBRARY.get(req.pose_id or "", "")
        text, sanitised = promptlib.compose_tagged(
            req.brief, pose_text=pose_text, has_wardrobe=has_wardrobe,
            pose_ref_tag=pose_ref_tag, build_text=build_text, shot_type=req.shot_type,
            camera_holder=req.camera_holder, flaws=req.flaws,
            carry_text=carry_text, pov=req.pov)

    # Carry the outfit's FULL styling into the shot. The turnaround (@image2) has
    # her head cropped and may not show every accessory, so the saved outfit
    # description supplies the lip colour, nail colours, jewellery, bag and
    # accessories the image alone would drop. These are STYLING, not identity —
    # her face still comes only from @image1.
    if has_wardrobe:
        desc = (_wardrobe_meta().get(req.wardrobe_id, {}) or {}).get("description")
        if desc and desc.strip():
            if req.face_accessories:
                styling, _ = promptlib.sanitise(
                    "She is WEARING this complete look in the shot — show every "
                    "element on her, not only the clothing: reproduce the garments "
                    "from @image2, and also render her hairstyle and hair colour, "
                    "lip colour, nail colours, jewellery, bag, belt, watch, and any "
                    "eyewear/sunglasses, hat or hair accessory from the "
                    "description (if a hairstyle/colour is given, style her hair "
                    "that way for this look). If the look includes "
                    "sunglasses or glasses she is wearing them over her eyes; a hat "
                    "or hair piece she wears on her head — render these worn items "
                    "clearly and do NOT omit them. Her facial identity, bone "
                    "structure and features stay exactly hers from @image1 — she "
                    f"is simply shown wearing these items: {desc.strip()}")
            else:
                # Face clear — apply everything EXCEPT items that cover the face,
                # so identity stays fully readable (the gate can score it).
                styling, _ = promptlib.sanitise(
                    "She is wearing this look — reproduce the garments from @image2 "
                    "and apply its hairstyle and hair colour, lip colour, nail "
                    "colours, jewellery, bag, belt and watch. But do NOT add any "
                    "sunglasses, glasses, eyewear, "
                    "hat or anything covering or obscuring her face — keep her face "
                    "fully clear, uncovered and visible, even if the description "
                    "mentions such items. Her facial identity comes only from "
                    f"@image1: {desc.strip()}")
            text = f"{text} {styling}"

    # Manicure reference: match her nails to the chosen nail image. Nails only —
    # face/identity stay with @image1, outfit unchanged.
    if nail_tag:
        nail_line, _ = promptlib.sanitise(
            f"NAILS — highest priority: her nails ALWAYS match the manicure shown in "
            f"{nail_tag} — the same nail shape, length, base colour, finish and any "
            "nail art on BOTH her fingernails and her toenails (a matching manicure "
            "and pedicure, by default)"
            + (f": {nail_desc.strip()}" if nail_desc.strip() else "")
            + f". Apply it to every fingernail and every toenail. Do not force her "
            "feet into the frame, but any hand or foot that appears has nails "
            f"following {nail_tag} exactly. IGNORE and OVERRIDE any other fingernail "
            f"or toenail colour stated anywhere else in this prompt — her nails follow "
            f"{nail_tag} only. Keep her hands and nails clearly in focus. This changes "
            "only her nails; her facial identity comes only from @image1 and her "
            "outfit is otherwise unchanged.")
        text = f"{text} {nail_line}"

    # Home reference: the brief named one of her rooms — put her in HER home, the
    # exact space shown in the corner image, so the house stays consistent.
    if place_tag:
        where = ("a place she goes regularly" if place_kind == "regular"
                 else "her own home")
        thing = "space" if place_kind == "regular" else "room"
        place_line, _ = promptlib.sanitise(
            f"SETTING — {where}: the location and background of this photo is "
            f"exactly the {thing} shown in {place_tag} — reproduce that same place (the "
            f"furniture, walls, layout, décor and overall setting) faithfully and keep "
            f"it consistent. Do not invent or substitute a different {thing}. She is "
            f"naturally within this space doing what the brief describes; her identity "
            f"still comes only from @image1.")
        text = f"{text} {place_line}"

    # The date, last: season, hair era and manicure wear. Appended rather than
    # handed to the prompter for the same reason the build clause is — Claude is
    # barred from describing her, and hair and nails sit right on that line.
    # POV shots are faceless and hairless in frame, so only the season applies.
    if tl_clause:
        when_line, _ = promptlib.sanitise(
            timeline.clause(when, {}, [])[0] if req.pov else tl_clause)
        if when_line:
            text = f"{text} {when_line}"

    label = req.brief.strip()[:60] or "untitled shot"
    session = generate.new_session(label)

    # Store the pose's actual TEXT alongside its id. The pose library can be
    # regenerated (ids change), which orphans a past shot's pose_id — so the
    # text is what lets "use this pose" survive a library rebuild.
    pose_text_used = req.pose_text or promptlib.POSES_LIBRARY.get(req.pose_id or "", "")

    # POV framing is phone-portrait; use 4:5 unless the caller set a non-default aspect.
    # No face to gate, so the 4K-for-face-pixels rationale (config) doesn't apply — 2K is fine.
    aspect = ("4:5" if req.pov and req.aspect in (None, "", "3:4") else req.aspect)

    def run(job: dict) -> dict:
        return generate.generate(
            prompt=text, system="", refs=refs, aspect=aspect,
            seed=req.seed, session=session, progress=job,
            # If gpt-image-2 refuses a revealing outfit on content_policy, render
            # it on the scene model instead (weaker identity, recorded) rather
            # than dead-spinning to a failure.
            fallback_endpoint=SCENE_EDIT,
            resolution=req.resolution,
            meta={"brief": req.brief, "bio_references": [p.name for p in refs],
                  "wardrobe": req.wardrobe_id, "pose_id": req.pose_id,
                  "pose_text": pose_text_used,
                  "pose_ref": req.pose_ref_id, "nail_id": nail_id,
                  "home_corner": home_corner.stem if home_corner else None,
                  "sanitised": sanitised, "pov": req.pov,
                  "ref_demoted": demoted, "when": tl_facts,
                  "camera_holder": req.camera_holder, "flaws": req.flaws,
                  # A deliberately imperfect frame is EXPECTED to score low —
                  # motion blur and a half-caught expression degrade the very
                  # geometry ArcFace reads. Recording it here is what keeps that
                  # low number from being counted as drift later.
                  "expected_low": bool((promptlib.SNAPSHOT_FLAWS.get(req.flaws)
                                        or {}).get("expected_low")),
                  "ai_prompt": bool(req.prompt and req.prompt.strip())},
        )

    jid = generate.start_job(label, run)
    return {"job": jid, "sanitised": sanitised, "ref_demoted": demoted}


@app.get("/api/jobs")
def jobs():
    """Every in-memory job, newest last — makes a stuck generation visible."""
    return {"jobs": generate.all_jobs()}


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
        (IMAGES / ".thumbs" / f"{Path(r['file']).stem}.jpg").unlink(missing_ok=True)
    return {"deleted": len(removed), "freed_mb": round(freed / 1e6, 1)}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    """Delete a single generated shot — image, thumbnail and ledger row."""
    removed = generate.delete_runs({run_id})
    if not removed:
        raise HTTPException(404, run_id)
    for r in removed:
        (IMAGES / r["file"]).unlink(missing_ok=True)
        (IMAGES / ".thumbs" / f"{Path(r['file']).stem}.jpg").unlink(missing_ok=True)
    return {"ok": True, "deleted": len(removed)}


class BulkIdsReq(BaseModel):
    ids: list[str] = []


class BulkMarkReq(BaseModel):
    ids: list[str] = []
    decision: str | None = None   # "approve" | "reject" | null (clear)


@app.post("/api/runs/delete")
def delete_runs_bulk(req: BulkIdsReq):
    """Delete many shots at once — images, thumbnails and ledger rows. Same body
    as the single delete, over a set (db.runs_delete is transactional)."""
    removed = generate.delete_runs(set(req.ids))
    freed = 0
    for r in removed:
        p = IMAGES / r["file"]
        if p.exists():
            freed += p.stat().st_size
        p.unlink(missing_ok=True)
        (IMAGES / ".thumbs" / f"{Path(r['file']).stem}.jpg").unlink(missing_ok=True)
    return {"deleted": len(removed), "freed_mb": round(freed / 1e6, 1)}


@app.post("/api/runs/mark-bulk")
def mark_bulk(req: BulkMarkReq):
    """Apply one verdict (approve / reject / clear) to many shots at once."""
    n = 0
    for rid in req.ids:
        try:
            generate.mark(rid, req.decision)
            n += 1
        except KeyError:
            pass   # a since-deleted id shouldn't fail the whole batch
    return {"marked": n, "decision": req.decision}


def _is_intermediate(r: dict) -> bool:
    """An outfit / body / calibration generation — never a review-grid shot. Its
    useful output is copied out on save (into wardrobe/, bodies/, refs/) or embedded
    in the gallery, so the data/images copy is redundant once made (pure waste if
    the preview was discarded)."""
    m = r.get("meta") or {}
    return bool(m.get("outfit_create") or m.get("body_ref_create") or m.get("calibrate") or m.get("home_create"))


@app.post("/api/images/cleanup")
def images_cleanup():
    """Reclaim disk from images that are no longer needed for the ACTIVE character:

      1. ORPHANS — files in data/images with no ledger row at all (left by a crash,
         or a row deleted without its file).
      2. SPENT INTERMEDIATES — outfit/body/calibration images whose result was
         already copied out or embedded; drop the image AND its now-dangling row.
      3. STALE THUMBS — thumbnails whose source image is gone.

    Real shots (everything in the review grid) are never touched. Run this when no
    generation is mid-flow: an outfit/body PREVIEW still awaiting save counts as a
    spent intermediate and will be reclaimed.
    """
    runs = generate.all_runs()
    keep = {r["file"] for r in runs if not _is_intermediate(r)}
    intermediate = {r["id"]: r["file"] for r in runs if _is_intermediate(r)}
    inter_files = set(intermediate.values())
    thumbs = IMAGES / ".thumbs"
    freed = 0
    counts = {"orphans": 0, "intermediates": 0, "stale_thumbs": 0}

    def _rm(name: str) -> None:
        nonlocal freed
        p = IMAGES / name
        if p.exists():
            try:
                freed += p.stat().st_size
            except OSError:
                pass
            p.unlink(missing_ok=True)
        (thumbs / f"{Path(name).stem}.jpg").unlink(missing_ok=True)

    exts = (".png", ".jpg", ".jpeg", ".webp")
    on_disk = [p for p in IMAGES.iterdir()
               if p.is_file() and p.suffix.lower() in exts] if IMAGES.exists() else []
    for p in on_disk:
        if p.name in inter_files:
            _rm(p.name); counts["intermediates"] += 1
        elif p.name not in keep:
            _rm(p.name); counts["orphans"] += 1

    # Drop the reclaimed intermediates' ledger rows — their file is gone now.
    if intermediate:
        generate.delete_runs(set(intermediate))

    # Stale thumbnails whose source image no longer exists.
    if thumbs.exists():
        live = {p.stem for p in IMAGES.iterdir()
                if p.is_file() and p.suffix.lower() in exts}
        for t in thumbs.glob("*.jpg"):
            if t.stem not in live:
                t.unlink(missing_ok=True); counts["stale_thumbs"] += 1

    return {**counts, "freed_mb": round(freed / 1e6, 1)}


@app.get("/api/health")
def health():
    return {"ok": True, "root": str(ROOT)}
