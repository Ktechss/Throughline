"""FastAPI app behind the React UI.

    # Linux / WSL
    .venv/bin/python -m uvicorn backend.main:app --reload --port 8000
    # Windows
    .venv-win\\Scripts\\python.exe -m uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import shutil
import threading
from contextlib import asynccontextmanager
import tempfile
import time
import uuid
from urllib.parse import urlparse

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import (config, db, describe, gate, generate, prompt as promptlib, prompter,
               timeline)
from . import framing_data, getup_data, lighting_data
from . import providers
from .interactions_data import INTERACTIONS
from .scenes_data import MOMENTS
from .config import (ARCHIVE_FORMAT, ARCHIVE_QUALITY, BODIES, BODIES_META,
                     CHARACTERS, CharPath, EDIT, GOLD, HOME_PATH,
                     IMAGES, NAILS, PLACES, POSE_REFS,
                     PROMPT_CAP, REF_BUDGET, REFS, RESOLUTION, ROOT, SCENE_EDIT,
                     SCENE_TEXT2IMG, TEXT2IMG, TIMELINE_PATH, WARDROBE)

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Recover any download that was parked before the UI is even served: a
    # reseller's result URL expires in ~24h, so the sooner the sweep runs after a
    # restart, the more likely a paid-for image is still there to fetch.
    _start_sweeper()
    yield


app = FastAPI(title="Throughline", lifespan=_lifespan)

# Create tables + import the JSON ledgers once (idempotent — only imports while a
# table is still empty). Runs, videos and wardrobe meta now live in eve1.db; the
# JSON files stay on disk as a cold backup. See backend/db.py.
db.init_db()

# Vite dev server. Same-origin in production; this is for `npm run dev`.
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def scope_character(request, call_next):
    """Let the caller state which character it means, per request.

    The active character was one process-global that anything could change, so a
    second tab, another window or a script could redirect work already in flight
    elsewhere. It happened: an outfit generated while the browser showed one
    character was filed under another, because the global had moved in between.

    The browser now sends X-Character on every call and it wins for the life of
    that request. Absent or unknown, nothing is pinned and the persistent default
    applies — so curl, the docs page and any older client behave exactly as before.

    ⚠ A HEADER CANNOT REACH AN <img>. That gap shipped, and it showed up as the
    worst-looking bug of the lot: the scene composer requested Alexa's
    "Casual1.webp" thumbnail, the browser sent no header because it is an image
    tag, the server fell back to the active character, and Kiara's dress appeared
    in Alexa's picker. The data was never wrong — only the picture of it.
    So a `?character=` query parameter is honoured too, which is the only form an
    <img> src can carry.
    """
    cid = (request.headers.get("x-character")
           or request.query_params.get("character"))
    token = config.scope_active(cid if cid and db.chars_get(cid) else None)
    try:
        return await call_next(request)
    finally:
        config.unscope_active(token)


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


# An uploaded style reference is NOT her. It informs hair, mood and lighting and
# nothing else (see REFERENCE_MODES), and it may well be a photograph of a real
# person — which this project never displays as a character. It was reachable as
# an avatar because the fallback below sorted refs/ alphabetically and
# "seed-upload.png" won, so a character briefly wore a stranger's face on her
# card. Excluded by name, at the one place that picks a face to show.
_NOT_HER = ("seed-upload",)


def _char_avatar_src(cid: str) -> Path | None:
    """Best image to represent a character on its card: her BIO face if set, else
    a face she was actually generated as. None while she has neither."""
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
                    and not x.name.startswith(".")
                    and not x.stem.startswith(_NOT_HER)]
            if imgs:
                return imgs[-1] if sub == "images" else imgs[0]
    return None


def _char_has_identity(cid: str) -> bool:
    return (config.char_base(cid) / "state" / "gallery.npz").exists()


def _char_reference(cid: str) -> str | None:
    """Her MASTER FACE filename, or None if one has never been chosen.

    Not the same question as `has_identity` (which asks whether she has been
    calibrated). A character with no reference cannot be photographed at all —
    `shot()` refuses — so this is the difference between a usable character and
    an unfinished one, and the UI gates entry on it.
    """
    bio = config.char_base(cid) / "state" / "bio.json"
    try:
        ref = (json.loads(bio.read_text()) or {}).get("reference")
    except (OSError, ValueError):
        return None
    return ref if ref and (config.char_base(cid) / "refs" / ref).exists() else None


def _pending_faces(cid: str) -> int:
    """Master-face candidates she is waiting on a choice between."""
    if _char_reference(cid):
        return 0
    imgs = config.char_base(cid) / "images"
    return sum(1 for r in db.runs_all(character_id=cid)
               if (r.get("meta") or {}).get("guided_seed")
               and (imgs / r["file"]).exists())


def _char_status(cid: str, pending: int, has_ref: bool) -> tuple[str, dict | None]:
    """Where this character is in her life, and the job still working on her.

    Creation is a DRAFT, not a modal you have to sit through. It takes minutes,
    and there is no reason to hold the browser hostage for them: the character
    row exists from the first instant, so she can appear in the roster as a card
    that fills itself in while you carry on working on someone else.

    Every state below is derived from durable facts — a file on disk, a row in
    the db — except `building`, which asks the in-memory job registry. That is
    the honest answer: if the backend restarted mid-build, nothing IS working on
    her any more, and `stalled` is exactly what the user needs to be told rather
    than a spinner that never resolves.
    """
    if has_ref:
        return "ready", None
    # A LIVE job outranks whatever candidates exist so far. Checking `pending`
    # first said "awaiting_face" the moment the first of four faces landed, so a
    # build three minutes from finishing looked finished — and picking then would
    # have chosen from a partial set.
    jid = db.chars_doc(cid).get("creation_job")
    job = generate.job_status(jid) if jid else None
    if job and not job["done"]:
        return "building", {"id": job["id"], "stage": job.get("step") or job["stage"],
                            "elapsed": job.get("elapsed"), "have": pending}
    if pending:
        return "awaiting_face", None          # candidates waiting on a human
    return "stalled", ({"error": job["error"]} if job and job.get("error") else None)


def _char_view(c: dict) -> dict:
    # A character is USABLE once she has a face. Until then the studio is a dead
    # end: every shot 400s on the missing reference.
    has_ref = _char_reference(c["id"]) is not None
    pending = _pending_faces(c["id"])
    status, job = _char_status(c["id"], pending, has_ref)
    return {**c, "has_identity": _char_has_identity(c["id"]),
            "has_avatar": _char_avatar_src(c["id"]) is not None,
            "has_reference": has_ref,
            "pending_faces": pending,
            "status": status,          # ready | awaiting_face | building | stalled
            "job": job,
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

# The other three body parts the build owns. FRAME above is one line; these are
# the parts that actually carry the shape, and until now the picker did not
# write them — it set body.frame and left body.bust/waist/hips at prompt.py's
# defaults, which are Kiara's spec-sheet numbers. Picking "voluptuous" therefore
# produced a bio reading "pronounced curvy, full-figured hourglass" directly
# above "a full chest ... 40-inch hips", and compose() rebuilds the whole body
# section into the Subject line of every shot — so the picker was contradicted
# on every generation from the moment the character was created.
#
# Register matches _BUILD_FRAME, not _BUILD_FIGURE: this text rides on ordinary
# shots through the standard model, where _BUILD_FIGURE's explicit wording is
# both unnecessary and closer to the moderation boundary. Proportional rather
# than absolute — height is its own picker (168cm and 185cm cannot share a hip
# measurement), so these describe ratios and let body.height set the scale.
_BUILD_PARTS = {
    "slim": {
        "body.bust": "a small, neat bust",
        "body.waist": "a narrow, straight waist",
        "body.hips": "narrow hips, roughly in line with her shoulders",
    },
    "athletic": {
        "body.bust": "a small to average bust on a lean chest",
        "body.waist": "a lean, firm waist with visible definition",
        "body.hips": "narrow, strong hips and a firm seat",
    },
    "curvy": {
        "body.bust": "a full, rounded bust with a natural weight and a natural hang",
        "body.waist": "a clearly indented waist, distinctly narrower than both bust and hips",
        "body.hips": "full, rounded hips balancing the bust",
    },
    "voluptuous": {
        "body.bust": "a very full, heavy, rounded bust with a natural weight and a natural hang",
        "body.waist": "a dramatically narrow, deeply indented waist",
        "body.hips": "wide, full, rounded hips balancing the bust",
    },
    "full-figured": {
        "body.bust": "a full, heavy bust with a natural weight and a natural hang",
        "body.waist": "a soft, rounded midsection with a gently defined waist",
        "body.hips": "wide, full, soft hips",
    },
}

# --------------------------------------------------------------------------
# The rest of the identity pickers.
# --------------------------------------------------------------------------
# Creation writes 28 identity fields and used to ask about three of them, so a
# character was mostly whatever Claude invented from a sentence of free text —
# and you only saw it after four faces had been generated from it. These are the
# axes worth deciding up front.
#
# Every one is OPTIONAL and unset by default, which is the existing FACE_SHAPES
# convention: "" means Claude decides, and that is what keeps characters from all
# looking alike. A set pick does two things — it briefs Claude BEFORE the bio is
# written (so the other fields are written to agree with it) and then overrides
# the field afterwards, because the pick is authoritative.
#
# Values are photographable noun phrases, never adjectives. The rule from
# prompter's rule 4 applies here too: a model can render "a smooth, softly
# tapered jawline"; it cannot render "a nice jaw".
PICKERS: dict[str, dict[str, str]] = {
    # -- the skull. This is the geometry ArcFace keys on and the geometry a
    #    drifted generation loses first, so it earns the most pickers.
    "cheekbones": {
        "low": "low, gently rounded cheekbones with a soft plane below them",
        "soft": "softly defined cheekbones, present but not sharp",
        "defined": "clearly defined cheekbones with a visible plane beneath",
        "high": "high, quietly angular cheekbones",
    },
    "jawline": {
        "soft": "a soft jawline with little visible angle",
        "rounded": "a rounded jawline, wide at the angle and softly padded",
        "tapered": "a smooth, softly tapered jawline — defined but not angular",
        "square": "a squared jawline with a clear angle at the corner",
    },
    "chin": {
        "rounded": "a softly rounded chin of medium length",
        "pointed": "a narrow, gently pointed chin",
        "square": "a squared chin with a flat front plane",
        "long": "a longer-than-average chin, straight at the front",
    },
    # -- the features
    "eyes": {
        "almond": "almond-shaped eyes with a level set",
        "round": "large rounded eyes with an open lid",
        "hooded": "deep-set eyes with a heavy upper lid",
        "downturned": "eyes with a gently downturned outer corner",
        "upturned": "eyes with a slight upward tilt at the outer corner",
    },
    "brows": {
        "fine": "fine, lightly filled brows with a soft arch",
        "natural": "naturally full brows, softly groomed",
        "full": "thick, strongly defined brows",
        "straight": "straight-set brows with a minimal arch",
        "arched": "clearly arched brows with a defined peak",
    },
    "nose": {
        "small": "a small nose with a narrow bridge and a neat tip",
        "straight": "a straight nose with an even bridge",
        "rounded": "a rounded nose with a soft, full tip",
        "aquiline": "a nose with a high bridge and a slight curve",
        "broad": "a broader nose with a wide base and a soft tip",
    },
    "lips": {
        "thin": "slim lips with a defined edge",
        "medium": "medium lips with a fuller lower lip",
        "full": "full lips with a clear cupid's bow",
    },
    # -- hair. Granular parts, enabled for characters born after 19e3bda8.
    "hair_colour": {
        "jet black": "jet black with a cool sheen",
        "dark brown": "dark brown-black with a warm undertone",
        "brown": "mid-brown with softer strands at the ends",
        "chestnut": "warm chestnut brown",
        "auburn": "dark auburn with a red cast in the light",
    },
    "hair_length": {
        "crop": "cropped short, above the ear",
        "bob": "a chin-length bob",
        "shoulder": "shoulder-length",
        "mid-back": "long, falling to the mid-back",
        "waist": "very long, falling to the waist",
    },
    "hair_texture": {
        "straight": "thick and straight, with a heavy fall",
        "wavy": "softly wavy from around shoulder level",
        "curly": "defined curls with visible spring",
        "coily": "tightly coiled, dense and voluminous",
    },
}

# The REGISTER a face is written in — how flattering the proportions should be.
#
# This exists because the bio writer had two instructions steering it away from
# attractive ("prefer real, lived-in features over a generic 'attractive'
# template", and a ban on beauty adjectives) and none steering it toward one. It
# obeyed: characters came back with "a short, rounded chin that recedes very
# slightly". Kiara predates both rules, which is the whole reason she looks
# different from everyone made since.
#
# It is NOT a part and never becomes one. An "attractiveness" field would put an
# adjective into every shot prompt, which is precisely what makes an image model
# fall back on its generic beauty template. This steers WHICH PROPORTIONS get
# chosen while the bio is written, and then it is gone.
LOOKS = {
    "striking": "She should be memorable and photograph well — strong, editorial "
                "features: definite cheekbones, a clean jawline, a face that holds "
                "attention. Distinctive rather than merely pretty.",
    "attractive": "She should be naturally attractive — balanced, flattering "
                  "proportions: well-spaced eyes, a proportionate nose, a clean "
                  "jawline, good cheekbone placement. Pretty in an ordinary, "
                  "believable way, not a beauty-campaign way.",
    "natural": "She should look like an ordinary real person seen in good light — "
               "pleasant and unremarkable, neither striking nor plain.",
    "characterful": "She should be interesting rather than pretty — a face with "
                    "something specific about it. Let a feature be unusual: a "
                    "strong nose, wide-set eyes, a heavy brow. Memorable because "
                    "it is particular, not because it is flattering.",
}
DEFAULT_LOOK = "attractive"


# Which part each picker writes. Split out rather than folded into PICKERS so the
# vocabularies stay readable as plain option lists.
_PICKER_PART = {
    "cheekbones": "face.cheekbones", "jawline": "face.jawline", "chin": "face.chin",
    "eyes": "face.eyes", "brows": "face.brows", "nose": "face.nose", "lips": "face.lips",
    "hair_colour": "hair.colour", "hair_length": "hair.length",
    "hair_texture": "hair.texture",
}

# Skin is two pickers composing ONE part, because that is how skin.tone reads —
# "medium olive-brown skin with a warm undertone", not two sentences.
SKIN_TONES = {
    "fair": "fair", "light": "light", "medium": "medium",
    "olive": "medium olive", "brown": "warm brown", "deep": "deep brown",
}
SKIN_UNDERTONES = {
    "cool": "a cool undertone", "neutral": "a neutral undertone",
    "warm": "a warm undertone", "golden": "a golden undertone",
}


def _skin_text(tone: str, undertone: str) -> str:
    if not tone and not undertone:
        return ""
    t = SKIN_TONES.get(tone, "")
    u = SKIN_UNDERTONES.get(undertone, "")
    if t and u:
        return f"{t} skin with {u}"
    return f"{t} skin" if t else f"skin with {u}"


# --------------------------------------------------------------------------
# The MASTER FACE. Every image of her ever made descends from this one photo, so
# whatever it gets wrong is wrong forever — which is why it gets a fixed studio
# spec instead of whatever framing the moment suggests.
# --------------------------------------------------------------------------
# Deliberately boring. A neutral closed-mouth face on a plain background is the
# easiest thing in the world for ArcFace to read, and the gallery is later built
# from this seed — so a master face caught mid-laugh at an angle poisons every
# comparison that follows. The 85mm/head-and-shoulders framing is also the
# cheapest identity win available: it puts the face over gate.FACE_PLATEAU_PX,
# worth a measured 0.61 against 0.55 below it.
MASTER_FACE_PRESENTATION = (
    "Head-and-shoulders framing, eye-level camera, 85mm portrait lens, shallow "
    "depth of field. A calm, relaxed, closed-mouth expression looking straight "
    "into the lens. Minimal natural makeup, a plain cream top, no jewellery and "
    "nothing in her hair. Warm neutral background, soft diffused window-style "
    "light, accurate skin tones, professional full-frame camera realism."
)

# Facts, not wishes — the same principle as skin.facts in the part tree. A model
# can render "visible pores"; it cannot render "realistic".
MASTER_FACE_REALISM = (
    "Show authentic human skin: visible pores, fine peach fuzz, subtle "
    "pigmentation variation, faint under-eye texture, mild natural redness and a "
    "few tiny blemishes. Include realistic catchlights, moist waterlines, visible "
    "tear ducts, natural eyelid creases and individual eyebrow hairs. Her "
    "proportions are balanced but naturally imperfect, never mirror-symmetrical."
)

# What to steer AWAY from. Every item here is a specific failure this pipeline
# has actually produced, not a generic quality incantation.
MASTER_FACE_NEGATIVE = (
    "Avoid: any resemblance to a celebrity or public figure, plastic or waxy "
    "skin, an airbrushed or beauty-filter appearance, perfect symmetry, oversized "
    "eyes, an unnaturally tiny nose, exaggerated lips, an unnaturally sharp "
    "jawline, heavy makeup, CGI, illustration, or doll-like features."
)


# How an uploaded reference may be used. This is a SAFETY boundary as much as a
# quality one, and the two happen to agree.
#
# The old creation prompt said "Take her facial features, structure, hairstyle
# and overall likeness from @image1" — an instruction to COPY whatever was
# uploaded. Point that at a photograph of a real person and the pipeline produces
# that person's likeness, which this project forbids outright (see CLAUDE.md: she
# is entirely fictional, no real person's likeness, anywhere, ever).
#
# So an upload can only ever be INSPIRATION here: hair, mood, lighting, framing —
# never the face. Identity-lock mode is real and useful, but it belongs to HER
# OWN approved master face, which is what every later shot already does; it is
# not something an upload can opt into.
# "identity" is the third mode, and the only one that spends NOTHING.
#
# Creation's expensive step is inventing a face: four candidates at ~100s and one
# generation each, and most of the time the owner already has the face. They made
# it somewhere else, looked at it, and decided. Regenerating it here is paying
# twice for a decision already taken — and it cannot even reproduce it, because
# "inspiration" is forbidden from copying a face by design.
#
# So: upload it and it IS her. Zero generations, instant, and the picture she is
# built on is the one that was chosen rather than a fifth approximation of it.
#
# THE RULE THIS DOES NOT RELAX. She is entirely fictional; no real person's
# likeness, anywhere, ever. In "inspiration" mode that is enforced by the prompt,
# which is why _NOT_HER exists and why an inspiration upload never becomes an
# avatar. In "identity" mode there is no prompt to enforce anything — the file is
# used as-is — so the guarantee moves to the person uploading. The UI states it
# at the point of choosing, and it belongs there rather than buried here.
REFERENCE_MODES = ("none", "inspiration", "identity")

# Enough to see real variation without turning creation into a spending
# decision. Four faces from one spec differ in exactly the way that matters
# here — same brief, different person — which is the choice being made.
# The most faces one build will ever generate. Four is where the choice stops
# improving: enough to see genuinely different people from one spec, few enough
# that a build is still ~one image's wall-clock now they run in parallel.
#
# The COUNT is per-build and the caller's, because it is the one place in
# creation where the user is spending. Someone who knows what they want can take
# one; someone exploring takes four.
MASTER_FACE_CANDIDATES = 4

_INSPIRATION_CLAUSE = (
    "Use the attached image ONLY as loose inspiration for the hairstyle, "
    "photographic mood, lighting and general presentation. Create a clearly "
    "DIFFERENT, completely fictional woman with a facial identity of her own. Do "
    "not copy or closely replicate the reference person's face, eyes, nose, lips, "
    "smile, jawline or facial proportions, and she must not resemble any "
    "celebrity or public figure. Her face comes from the description below, not "
    "from the attached image."
)


# The non-identity parts a head-and-shoulders portrait genuinely contains.
#
# Everything else in the tree — where she is, how it was lit, which camera, what
# she is wearing, what she is doing — describes a SHOT, and the master face is
# not a shot. It has its own fixed spec above, and letting the character's shot
# parts through as well produced a prompt that argued with itself:
#
#   spec: "85mm portrait lens, shallow depth of field"
#   parts: "wide 24mm-equivalent lens" ... "no bokeh"
#   spec: "professional full-frame camera realism"
#   parts: "Never a professional camera, never a photoshoot"
#   spec: "warm neutral background, soft diffused window-style light"
#   parts: "a plain white studio cyclorama" ... "flat and even, no colour cast"
#
# Three direct contradictions on lens, light and register, and the parts win on
# volume. Flat-and-even is what a passport photo looks like, and that is what
# came back. The build block was the same failure in a quieter form: "curvy,
# full-figured, full chest, full hips" cannot render below the collarbone in a
# head crop, so it renders in her face — overriding the face parts that
# explicitly asked for a tapered jaw and a narrow chin.
#
# So the rule is: her identity parts, plus the four non-identity parts a head
# and shoulders actually shows. Framing, lens, light, background and capture are
# the spec's job and only the spec's job. Her full build is not lost — it reaches
# every later prompt through build_clause(), which is text and costs no slot.
_MASTER_FACE_KEEP = {"body.shoulders", "body.posture", "skin.facts",
                     "grooming.makeup"}


def _master_face_prompt(parts: list[promptlib.Part], inspired: bool,
                        look: str = DEFAULT_LOOK) -> str:
    """The prompt one master-face candidate is generated from.

    The face itself comes from `compose(has_reference=False)` — the one place in
    this pipeline that DOES describe her, because a brand-new character has no
    reference yet and the seed has to come from words. Everything else here is
    fixed: presentation, realism, and what to avoid.
    """
    kept = [p for p in parts if p.identity or p.id in _MASTER_FACE_KEEP]
    # The pose parts are dropped by _MASTER_FACE_KEEP, so the presentation
    # rides as its own block below — where it is the only voice on framing.
    face = promptlib.compose(kept, has_reference=False)
    blocks = [_INSPIRATION_CLAUSE] if inspired else []
    blocks += [
        "A highly photorealistic close-up identity portrait of a completely "
        "fictional woman, shot on a professional full-frame camera — a real "
        "photographed individual with a memorable, original face, never a CGI "
        "character, illustration or generic AI beauty model.",
        face,
        MASTER_FACE_PRESENTATION,
        # The register, restated here. The bio above already carries it as
        # proportions; this keeps the image model from averaging back toward its
        # own default when it renders them.
        LOOKS.get(look, LOOKS[DEFAULT_LOOK]),
        MASTER_FACE_REALISM,
        MASTER_FACE_NEGATIVE,
    ]
    return "\n\n".join(blocks)


# How many generations a build runs at once. Every call here is a ~100s wait on
# fal, so running them one after another spent the whole time idle: four faces
# took eight minutes of which almost none was ours, and the ten home corners took
# closer to twenty. In parallel a character is ready in about the time ONE image
# takes.
#
# Capped rather than unbounded. Ten simultaneous requests is impolite to the
# endpoint and buys little over four, and a cap keeps a failure mode
# (rate-limiting, a stalled connection) from arriving ten at a time.
BUILD_CONCURRENCY = 4


def _parallel(items, work, job: dict | None = None, label: str = "") -> tuple[list, list]:
    """Run `work(item)` over `items` concurrently. Returns (results, errors).

    Results keep the INPUT order, not the completion order — the face candidates
    are shown in a picker and a grid that reshuffles itself between page loads
    would be its own small bug.

    A failure is collected, never raised: one bad face is not a failed character,
    and one bad room is not a bad home. The caller decides whether what came back
    is enough.
    """
    from concurrent.futures import ThreadPoolExecutor

    results: list = [None] * len(items)
    errors: list[str] = []
    done = 0

    def run_one(i_item):
        i, item = i_item
        return i, work(item)

    with ThreadPoolExecutor(max_workers=min(BUILD_CONCURRENCY, len(items) or 1)) as pool:
        for fut in [pool.submit(run_one, p) for p in enumerate(items)]:
            try:
                i, out = fut.result()
                results[i] = out
            except Exception as exc:  # noqa: BLE001 — collected, not fatal
                errors.append(str(exc)[:120])
            done += 1
            if job is not None:
                job["step"] = f"{done}/{len(items)} {label}".strip()
    if job is not None:
        job["step"] = None
    return [r for r in results if r is not None], errors


def _height_text(cm: int) -> str:
    total_in = round(cm / 2.54)
    return f"{cm}cm ({total_in // 12}'{total_in % 12}\")"


def _write_bio(cid: str, updates: dict) -> None:
    """Read-modify-write bio.json for one character.

    Deliberately on the RAW file rather than through _bio_cfg(), which injects
    Kiara.png and cd-body.png as defaults — writing those back would bake the
    original character's reference into every new character's bio.
    """
    path = _state_path("bio.json", cid)
    cfg = json.loads(path.read_text()) if path.exists() else {}
    cfg.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n")


def _bodies_available() -> list[dict]:
    """Every figure a new character can be built from, across all characters.

    Lists saved BODY TYPES, not just each character's active body_reference.
    Building a figure costs generations and iteration, and the point of the body
    library is that the work is done once — but creation could previously only
    borrow whichever type happened to be active, so reusing any other one meant
    going back to the source character, selecting it, then creating. Every saved
    type is offered here instead.

    `id` is "<cid>" (that character's active body_reference, the old behaviour)
    or "<cid>:<type-id>" for a specific saved type. `_copy_body_from` parses
    both. The dict shape is unchanged so the creation picker renders it as-is.
    """
    out = []
    for row in db.chars_all():
        cid, who = row["id"], row["name"]
        meta = _state_path("bodies.json", cid)
        saved = json.loads(meta.read_text()).get("bodies", []) if meta.exists() else []
        for b in saved:
            f = config.char_base(cid) / "bodies" / b["id"]
            f = next((p for p in (f.with_suffix(s) for s in (".png", ".webp", ".jpg"))
                      if p.exists()), None)
            if f:
                out.append({"id": f"{cid}:{b['id']}", "name": f"{who} · {b['id']}",
                            "file": f.name, "build": b.get("build", "")})
        if saved:
            continue
        # No saved types — fall back to her active body reference, so a character
        # who never named a figure is still borrowable.
        path = _state_path("bio.json", cid)
        cfg = json.loads(path.read_text()) if path.exists() else {}
        name = cfg.get("body_reference")
        if name and (config.char_base(cid) / "refs" / name).exists():
            out.append({"id": cid, "name": who, "file": name, "build": ""})
    return out


def _copy_body_from(src_cid: str, dst_cid: str) -> str | None:
    """Copy one character's body reference onto another, WITHOUT her head.

    Sharing a figure is a reasonable thing to want and costs a generation to
    reproduce. Sharing the image as-is is not: a body reference is a full-length
    photograph and it contains a FACE — measured, 427px and frontal on one of
    these, and three faces on another because it is a turnaround sheet. That
    image is appended to `refs` on every shot, and `compose_tagged` has no role
    line for it, so nothing tells the model whose face to ignore. Copying it
    across characters would attach one woman's face to another woman's every
    photograph, which is the blending failure built by hand.

    So the head comes off. Everything below the lowest detected chin is kept,
    which is exactly the part anyone wanted to share — shoulders, waist, hips,
    limbs, proportion — and there is no identity left in the file to leak.

    The copy also registers the figure in her BODY LIBRARY, not just as her
    body_reference. Those are two different things and the first version only did
    the second: `bio.body_reference` is what rides on a shot, while `bodies/` +
    `state/bodies.json` is the picker the Bio tab actually renders. Setting one
    without the other produced a character who HAD the right figure on every
    photograph and showed an empty Body section, which reads as "the copy did
    not work" when it had.

    `src_cid` is either "<cid>" (her active body reference) or "<cid>:<type-id>"
    for one specific saved body type, as offered by _bodies_available().

    Returns the new filename, or None if there was nothing to copy.
    """
    src_cid, _, type_id = src_cid.partition(":")
    build_text = ""
    if type_id:
        meta = _state_path("bodies.json", src_cid)
        saved = json.loads(meta.read_text()).get("bodies", []) if meta.exists() else []
        entry = next((b for b in saved if b["id"] == type_id), None)
        if not entry:
            return None
        build_text = entry.get("build", "")
        src = next((p for p in ((config.char_base(src_cid) / "bodies" / type_id)
                                .with_suffix(s) for s in (".png", ".webp", ".jpg"))
                    if p.exists()), None)
        if src is None:
            return None
    else:
        src_path = _state_path("bio.json", src_cid)
        cfg = json.loads(src_path.read_text()) if src_path.exists() else {}
        name = cfg.get("body_reference")
        if not name:
            return None
        src = config.char_base(src_cid) / "refs" / name
        if not src.exists():
            return None

    dst = config.char_base(dst_cid) / "refs" / f"body-canonical{src.suffix}"
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image
        faces = gate.analyze_all(src)
        with Image.open(src) as im:
            box = gate.face_box(src)
            # face_box gives the best face; for a multi-face sheet take the
            # LOWEST chin so no head survives the crop.
            bottom = box[3] if box else 0
            if len(faces) > 1:
                bottom = max(bottom, int(im.height * 0.28))
            cut = min(int(bottom * 1.06), int(im.height * 0.55))
            if cut > 0 and im.height - cut > 200:
                im.crop((0, cut, im.width, im.height)).save(dst)
            else:
                shutil.copy2(src, dst)
    except Exception:  # noqa: BLE001 — a failed crop must not silently ship a face
        try:
            if gate.face_box(src):
                return None          # refuse rather than copy a head across
        except Exception:  # noqa: BLE001
            return None
        shutil.copy2(src, dst)

    # Register it in the body LIBRARY so the Bio tab has something to show and
    # the figure can be re-selected later, exactly as /api/bodies/save does.
    try:
        src_name = (db.chars_get(src_cid) or {}).get("name") or src_cid
        entry_id = type_id or f"from-{src_cid}"
        (config.char_base(dst_cid) / "bodies").mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, config.char_base(dst_cid) / "bodies" / f"{entry_id}.png")
        meta_path = _state_path("bodies.json", dst_cid)
        data = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        bodies = [b for b in (data.get("bodies") or []) if b.get("id") != entry_id]
        # Carry the SOURCE's build text, not a "copied from X" placeholder. The
        # library's whole job is that image and text travel together (see
        # /api/bodies/select, which restores this text into body.bust) — a copy
        # that keeps the image and drops the wording recreates on the new
        # character exactly the image-vs-text drift the pairing exists to stop.
        bodies.append({"id": entry_id,
                       "build": build_text or f"figure copied from {src_name} (head cropped)",
                       "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps({"active": entry_id, "bodies": bodies},
                                        indent=2) + "\n")
    except Exception:  # noqa: BLE001 — the reference is what matters; the
        pass                          # library entry is convenience on top
    return dst.name


def _build_home(job: dict, cid: str, style: str, surroundings: str) -> int:
    """Her ten home corners, or none. Returns how many were rendered.

    Gated on the style text being present: with nothing to describe the house,
    ten generations buy ten unrelated generic rooms — real spend for something
    the Home tab can do better later, once she has a home worth describing.
    Silence here is a deliberate skip, and it is said out loud in the job note
    rather than left to be discovered.

    Shared by both creation paths so that skipping face generation does not also
    skip the home, and so the ten-generation decision lives in exactly one place.
    """
    style, surroundings = style.strip(), surroundings.strip()
    if style or surroundings:
        _state_path("home.json", cid).write_text(json.dumps(
            {"style": style, "surroundings": surroundings}, indent=2) + "\n")
    if not style:
        job["note"] = ("home skipped — no house style given; "
                       "generate corners from the Home tab")
        return 0
    # Same argument as the faces, and a bigger win: ten rooms one after another
    # was the longest part of a build by far.
    rooms, failed = _parallel(
        HOME_CORNERS, lambda c: _render_corner(c["key"], None, cid), job, "rooms")
    if failed:
        job["note"] = f"{len(failed)} home corners failed: {failed[0]}"
    return len(rooms)


@app.post("/api/characters/guided")
async def create_character_guided(
    name: str = Form(...),
    description: str = Form(""),
    face_shape: str = Form(""),
    build: str = Form(""),
    height_cm: str = Form(""),
    age: str = Form(""),
    faces: str = Form(""),          # how many candidates to generate (1..MASTER_FACE_CANDIDATES)
    look: str = Form(""),           # register: see LOOKS
    # The rest of the identity pickers (see PICKERS). All optional; blank means
    # Claude decides, which is what keeps characters from converging on one face.
    cheekbones: str = Form(""),
    jawline: str = Form(""),
    chin: str = Form(""),
    eyes: str = Form(""),
    brows: str = Form(""),
    nose: str = Form(""),
    lips: str = Form(""),
    skin_tone: str = Form(""),
    skin_undertone: str = Form(""),
    hair_colour: str = Form(""),
    hair_length: str = Form(""),
    hair_texture: str = Form(""),
    body_from: str = Form(""),   # copy this character's FIGURE (head cropped off)
    home_style: str = Form(""),
    home_surroundings: str = Form(""),
    reference: UploadFile | None = File(None),
    reference_mode: str = Form("inspiration"),
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
    try:
        years = int(float(age))
        if not (18 <= years <= 60):
            years = 0
    except (ValueError, TypeError):
        years = 0
    try:
        want_faces = min(MASTER_FACE_CANDIDATES, max(1, int(float(faces))))
    except (ValueError, TypeError):
        want_faces = MASTER_FACE_CANDIDATES
    look = look.strip().lower()
    if look not in LOOKS:
        look = DEFAULT_LOOK
    if reference_mode not in REFERENCE_MODES:
        raise HTTPException(400, f"reference_mode must be one of {REFERENCE_MODES}")

    # Collect the free-form pickers, dropping anything not in its vocabulary. An
    # unknown value is treated as unset rather than rejected: a stale UI should
    # give you a Claude-invented field, not a failed character.
    picks = {k: v for k, v in (
        ("cheekbones", cheekbones), ("jawline", jawline), ("chin", chin),
        ("eyes", eyes), ("brows", brows), ("nose", nose), ("lips", lips),
        ("hair_colour", hair_colour), ("hair_length", hair_length),
        ("hair_texture", hair_texture),
    ) if v.strip().lower() in PICKERS[k]}
    picks = {k: v.strip().lower() for k, v in picks.items()}
    skin = _skin_text(skin_tone.strip().lower(), skin_undertone.strip().lower())

    # READ AND VALIDATE THE UPLOAD FIRST, before any character exists.
    #
    # This was a rollback — create the character, then delete it again if the
    # image turned out to have no face in it. That is the wrong shape twice over:
    # set_active() had already pointed the app at the character being deleted, so
    # the next request recreated its folders, and a failed creation left an empty
    # directory and an active id naming nobody. Validating first means there is
    # nothing to undo.
    data: bytes = b""
    ext = ".png"
    if reference is not None and reference_mode != "none":
        data = await reference.read()
        ext = Path(reference.filename or "seed.png").suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
    use_own_face = bool(data) and reference_mode == "identity"
    if use_own_face:
        tmp = Path(tempfile.gettempdir()) / f"tl-identity-probe{ext}"
        tmp.write_bytes(data)
        try:
            gate.analyze(tmp)
        except (gate.NoFaceFound, ValueError):
            raise HTTPException(
                400, "no face detected in that image — upload a clear, "
                     "front-facing photo of her, or generate faces instead") from None
        finally:
            tmp.unlink(missing_ok=True)

    cid = _unique_char_id(name)
    config.ensure_char_dirs(cid)
    char = db.chars_create(cid, name)
    config.set_active(cid)                # the build job runs on the now-active char

    # Her figure, copied from someone who already has one. Free, instant, and
    # headless — see _copy_body_from for why the crop is not optional.
    # body_from is "<cid>" or "<cid>:<body-type-id>" — validate the cid half.
    if body_from.strip() and db.chars_get(body_from.strip().partition(":")[0]):
        copied = _copy_body_from(body_from.strip(), cid)
        if copied:
            _write_bio(cid, {"body_reference": copied})

    seed_upload: Path | None = None
    own_face: Path | None = None
    if data:
        if use_own_face:
            # Named as HER, not as a seed. The _NOT_HER exclusion exists to keep
            # an *inspiration* upload off her card, because that one may be a
            # photograph of someone real; this one is the face she is, so it must
            # be the file every later shot points at.
            own_face = config.char_base(cid) / "refs" / f"{cid}-identity{ext}"
            own_face.parent.mkdir(parents=True, exist_ok=True)
            own_face.write_bytes(data)
        else:
            seed_upload = _unique_ref_path(f"seed-upload{ext}")
            seed_upload.write_bytes(data)

    def run(job: dict) -> dict:
        # 1) Claude writes her identity fields; the explicit pickers OVERRIDE
        job["stage"] = "writing bio"
        parts = _load_parts(cid)
        # The granular hair parts ship OFF so existing characters keep their
        # single-line hair.base. A character born here has no such history, so it
        # gets the granular form and the blob is retired for it — describing hair
        # colour, length, texture, parting and hairline separately is what a
        # generator inventing a face from nothing actually needs.
        parts = [promptlib.Part(**{**p.dict(),
                                   "enabled": p.id != "hair.base"})
                 if p.id.startswith("hair.") else p
                 for p in parts]
        writable = [p for p in parts
                    if p.section in ("subject", "face", "hair", "skin", "body")
                    and p.id != "subject.energy" and p.enabled]
        fields = [{"id": p.id, "label": p.label, "hint": p.text} for p in writable]
        # BRIEF Claude with every set pick before it writes anything. The point
        # is not redundancy with the override below: it is that the OTHER twenty
        # fields get written to agree with the choice. Tell it the jaw is square
        # and it will not hand back soft rounded cheeks to sit above it.
        desc = description
        # The register leads: every field below is chosen under it, so it has to
        # be read before the specifics rather than after.
        desc += (f"\nThe look to write her in: {LOOKS[look]} "
                 "This line describes the TARGET, not the wording: express it by "
                 "choosing proportions, and never quote it back into a field. In "
                 "particular subject.age carries her age and descent only — never "
                 "how attractive she is.")
        if years:
            desc += f"\nShe is {years} years old."
        if shape:
            desc += f"\nHer face shape is {shape}."
        if build:
            desc += f"\nHer body build is {build}."
        if height:
            desc += f"\nHer height is {_height_text(height)}."
        for key, val in picks.items():
            desc += f"\nHer {key.replace('_', ' ')}: {PICKERS[key][val]}."
        if skin:
            desc += f"\nHer skin: {skin}."
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
            updates.update(_BUILD_PARTS[build])
        if height:
            updates["body.height"] = _height_text(height)
        for key, val in picks.items():
            updates[_PICKER_PART[key]] = PICKERS[key][val]
        if skin:
            updates["skin.tone"] = skin
        if years:
            # subject.age carries her DESCENT as well as her age ("A 26-year-old
            # South Asian woman"), and the picker only chose the number — so
            # substitute the number and leave the rest of Claude's phrase alone.
            cur = updates.get("subject.age") or next(
                (p.text for p in parts if p.id == "subject.age"), "")
            updates["subject.age"] = (re.sub(r"\b\d{1,2}\b", str(years), cur, count=1)
                                      if re.search(r"\b\d{1,2}\b", cur)
                                      else f"A {years}-year-old woman")
        parts = [promptlib.Part(**{**p.dict(), "text": updates.get(p.id, p.text)})
                 for p in parts]
        _save_parts(parts, cid)

        # 2) generate MASTER-FACE CANDIDATES.
        #
        # Several, not one. The master face is the image every future picture of
        # her descends from, so committing to whatever the first seed returned
        # was the single worst-leveraged decision in the pipeline: a face nobody
        # chose, generated once, locked in forever. Generating a handful and
        # letting a human pick costs a few more images once and is the only
        # judgement call in this project that SHOULD be a human's — it is
        # choosing who she is, not measuring whether it is still her.
        #
        # Nothing is committed here. No reference, no calib seed, no body. The
        # candidates are just rows; the pick endpoint does the committing.
        #
        # UNLESS she arrived with her own face. Then there is nothing to invent
        # and nothing to choose between: commit it and skip the whole step. This
        # is the entire saving — four generations and ~100s of wall clock — and
        # it is also the only path where the face she ends up with is exactly the
        # one that was looked at and approved.
        if own_face is not None:
            job["stage"] = "committing her face"
            _write_bio(cid, {"reference": own_face.name,
                             "calib_seed": own_face.name})
            corners = _build_home(job, cid, home_style, home_surroundings) \
                if home_style.strip() else 0
            return {"character": cid, "home_corners": corners, "candidates": [],
                    # No picker to show: she is ready to shoot immediately. The
                    # caller sends her to Calibrate instead, which is where the
                    # quality actually comes from.
                    "face_from_upload": True}

        job["stage"] = "generating faces"
        prompt = _master_face_prompt(parts, inspired=bool(seed_upload), look=look)
        refs = [seed_upload] if seed_upload else None
        session = generate.new_session(f"master face: {name}")
        # In parallel: four independent ~100s waits on fal have no reason to
        # queue behind each other. `progress` is deliberately NOT passed —
        # generate() would have four threads overwriting one another's stage
        # string; _parallel owns the counter instead and reports "2/4 faces".
        def one_face(i: int) -> dict:
            return generate.generate(
                prompt=prompt, refs=refs, aspect="3:4",
                # gpt-image-2 for the one image that compounds forever:
                # measured 0.813 against nano-banana's 0.678 on exactly this
                # shot (a frontal studio close-up). Shots stay on nano.
                endpoint=(EDIT if refs else TEXT2IMG),
                fallback_endpoint=SCENE_EDIT,
                session=session, character=cid,
                # No gallery exists yet by definition — this IS the seed hunt.
                # Gating would only ever record "gallery is empty".
                gated=False,
                meta={"guided_seed": True, "candidate": i + 1,
                      "from_upload": bool(seed_upload)})

        candidates, errors = _parallel(
            list(range(want_faces)), one_face, job, "faces")
        if not candidates:
            raise RuntimeError("no face candidates could be generated: "
                               + "; ".join(errors[:2]))
        if errors:
            job["note"] = f"{len(errors)} of {want_faces} faces failed"

        # 5) HOME — the third of her three defining pieces. Ten corners from one
        #    shared house style, so "her kitchen" means one specific kitchen from
        #    the first shot onward.
        #
        #    Gated on the style text being present: with nothing to describe the
        #    house, ten generations buy ten unrelated generic rooms — real spend
        #    for something the Home tab can do better later, once she has a home
        #    worth describing. Silence here is a deliberate skip, and it is said
        #    out loud in the job note rather than left to be discovered.
        corners_done = _build_home(job, cid, home_style, home_surroundings)

        # Nothing is committed yet — that is the point. The caller picks one of
        # these and POSTs it back to /api/characters/{cid}/master-face, which is
        # where the reference, the calibration seed and the body get set.
        return {"character": cid, "home_corners": corners_done,
                "candidates": [{"run_id": c["id"], "file": c["file"]}
                               for c in candidates]}

    jid = generate.start_job(f"create {name}", run)
    # Durable, so the roster can still find this build after a page reload — the
    # job registry is in memory and the browser holding the only reference to it
    # was how a creation got orphaned.
    db.chars_set_doc(cid, creation_job=jid)
    return {"character": _char_view(char), "job": jid}


class MasterFaceReq(BaseModel):
    run_id: str


@app.post("/api/characters/{cid}/master-face")
def set_master_face(cid: str, req: MasterFaceReq):
    """Commit one candidate as her MASTER FACE. This is where a character becomes
    usable, and it is deliberately a separate, human-made step.

    Creation generates candidates and commits nothing. This endpoint takes the
    chosen one and makes it three things at once:

      reference    — @image1 on every future shot. Creation never used to set
                     this, so a new character fell back to DEFAULT_BIO_REF
                     ('Kiara.png'), a file only the original character has, and
                     `shot()` refused every request with a message pointing at
                     the wrong tab. A character you cannot photograph is not a
                     character.
      calib_seed   — the face calibration generates its gallery angles FROM.

    It does NOT generate a body reference. That was here and produced consistently
    poor figures, because inventing a whole body from a head-and-shoulders photo
    is a guess — and it then rode as @image2 on every later shot, so one bad guess
    propagated. Build reaches the prompt as text instead; Bio -> Advanced body
    makes a real one when there is a figure worth pinning.

    The face is verified to contain a detectable face first. `/api/bio/reference/
    from-run` has always done this and creation never did, which meant a seed
    with no findable face surfaced much later as an unexplained calibration
    failure.
    """
    if not db.chars_get(cid):
        raise HTTPException(404, cid)
    row = next((r for r in generate.all_runs() if r["id"] == req.run_id), None)
    if not row:
        raise HTTPException(404, req.run_id)
    src = config.char_base(cid) / "images" / row["file"]
    if not src.exists():
        raise HTTPException(404, f"{row['file']} is not on disk")

    dest = _promote(src, config.char_base(cid) / "refs" / f"{cid}-identity.png")
    try:
        gate.analyze(dest)
    except (gate.NoFaceFound, ValueError):
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "no face detected in that candidate — pick another") from None

    bio_path = _state_path("bio.json", cid)
    cfg = json.loads(bio_path.read_text()) if bio_path.exists() else {}
    cfg["reference"] = dest.name        # the fix: she is shootable from here on
    cfg["calib_seed"] = dest.name
    bio_path.write_text(json.dumps(cfg, indent=2) + "\n")

    # NO BODY REFERENCE. Creation used to generate one here and the results were
    # consistently poor: a full-body activewear studio shot made from a single
    # head-and-shoulders reference is asking the model to invent a whole figure
    # from a face, and it invents a generic one. It then rode as @image2 on every
    # later shot, so one bad guess propagated into everything.
    #
    # Nothing needs it. Both consumers guard with .exists(), so a character
    # without one simply spends one fewer reference — which the measurement
    # prefers anyway (2 refs 0.622, 3 refs 0.579) — and her proportions still
    # reach every prompt through build_clause(), which is text and costs no slot.
    #
    # The capability is not gone, only the automatic one: Bio -> Advanced body
    # still creates one deliberately, from a shape reference, when there is a
    # figure worth pinning.
    return {"reference": dest.name, "calib_seed": dest.name, "job": None}


@app.get("/api/characters/{cid}/avatar")
def character_avatar(cid: str):
    src = _char_avatar_src(cid)
    if not src:
        raise HTTPException(404, "no avatar yet")
    state = config.char_base(cid) / "state"
    state.mkdir(parents=True, exist_ok=True)
    # Key the cache on WHICH FILE it came from, not just that file's mtime. A
    # single ".avatar.jpg" compared against src.mtime cannot notice the source
    # being SWAPPED for a different file: choosing her master face points this at
    # refs/<cid>-identity, whose mtime is older than a cache built minutes
    # earlier from the upload — so the check said "fresh" and she kept the wrong
    # face permanently. A per-source name makes a swap a cache miss by
    # construction.
    cache = state / f".avatar-{src.stem}.jpg"
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        from PIL import Image
        im = Image.open(src).convert("RGB")
        im.thumbnail((512, 512))
        im.save(cache, "JPEG", quality=82)
        for stale in state.glob(".avatar*.jpg"):
            if stale != cache:
                stale.unlink(missing_ok=True)
    # The browser caches by URL, and the URL does not change when she gets a
    # face. Revalidate so the card updates the moment she does.
    return FileResponse(cache, headers={"Cache-Control": "no-cache"})


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

# A background job owns its character for its whole life, so it must not read the
# ACTIVE one on every write — the user is free to click another character while a
# ~15-minute build runs, and CharPath would happily follow them. Passing `cid`
# resolves against that character's folder instead; omitting it keeps the old
# active-character behaviour every request handler wants.
def _state_path(name: str, cid: str | None = None) -> Path:
    return config.char_base(cid) / "state" / name


def _load_parts(cid: str | None = None) -> list[promptlib.Part]:
    PARTS_PATH = _state_path("parts.json", cid)
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


def _save_parts(parts: list[promptlib.Part], cid: str | None = None) -> None:
    _state_path("parts.json", cid).write_text(
        json.dumps([p.dict() for p in parts], indent=2) + "\n")


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


# ---------------------------------------------------------------- runs

@app.get("/api/runs")
def runs():
    """This character's runs, plus the collaborations she appears IN.

    A collaboration is owned by whoever started it (`character_id`) and records
    everyone in it (`meta.cast`). Without the second query a shot of Kiara and
    Sonam would exist only in Kiara's review, and Sonam would have no way to see
    a photograph she is standing in. `guest_of` marks those so the UI can group
    them rather than mixing them into her own work — and the owner never sees a
    run twice, because her own list already has it.
    """
    cid = config.get_active()
    mine = generate.all_runs()
    seen = {r["id"] for r in mine}
    guest = []
    for other in (c["id"] for c in db.chars_all() if c["id"] != cid):
        for r in db.runs_all(newest_first=True, character_id=other):
            if r["id"] in seen:
                continue
            if cid in ((r.get("meta") or {}).get("cast") or []):
                guest.append({**r, "guest_of": other})
    return {"runs": mine + guest}


class MarkReq(BaseModel):
    decision: str | None = None   # "approve" | "reject" | null


@app.post("/api/runs/{run_id}/mark")
def mark(run_id: str, req: MarkReq):
    try:
        return generate.mark(run_id, req.decision)
    except KeyError:
        raise HTTPException(404, run_id) from None


def _resolve_body_candidate(run_id: str, how: str) -> None:
    """Mark a body candidate as dealt with, so it stops being offered.

    Body previews are restored from the ledger now (they used to die with the
    tab), which made the opposite bug: a body you had just SAVED came straight
    back as an unsaved candidate on the next refresh, asking to be saved or
    discarded again. The ledger has no idea a choice was made unless we record
    one — so both exits, save and discard, stamp the run.
    """
    try:
        row, _cid = _run_and_owner(run_id)
    except HTTPException:
        return
    row.setdefault("meta", {})["body_resolved"] = how
    try:
        db.runs_update(run_id, row)
    except KeyError:
        pass


class BodyDismissReq(BaseModel):
    run_id: str


@app.post("/api/bio/body-ref/dismiss")
def body_ref_dismiss(req: BodyDismissReq):
    """Discard a body candidate without saving it. The image stays in the ledger
    like any other run; it just stops being offered as a pending choice."""
    _resolve_body_candidate(req.run_id, "discarded")
    return {"ok": True}


class RefetchReq(BaseModel):
    run_id: str


class ImportReq(BaseModel):
    url: str
    character: str | None = None
    brief: str = ""
    provider: str = ""
    model: str = ""


def _pull_to_disk(url: str, dest: Path) -> int:
    """Download one result URL to `dest`, in the format the row's name promises.

    ONE download path, shared by the manual refetch and the automatic sweep
    below. They were separate, and drifted: generate._download grew a browser
    User-Agent for kie's CDN while this one did not, so the endpoint that exists
    to rescue a failed download 403'd for the exact reason the download had.
    """
    import urllib.request
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        # kie's result CDN 403s urllib's default UA. fal's is indifferent.
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=generate.DOWNLOAD_TIMEOUT) as r, \
                open(tmp, "wb") as fh:
            shutil.copyfileobj(r, fh)
        if tmp.stat().st_size < 10_000:      # same floor generate() uses
            raise ValueError("re-downloaded file is implausibly small")
        # The provider serves the ORIGINAL png, but the row names the archived
        # file. Land it in the format the name promises, or the row points at a
        # .webp full of PNG bytes — readable, since PIL sniffs content, but a lie
        # on disk and 10x the size the archive was chosen for.
        if dest.suffix.lower() == f".{ARCHIVE_FORMAT}":
            from PIL import Image
            with Image.open(tmp) as im:
                im.convert("RGB").save(dest, ARCHIVE_FORMAT.upper(),
                                       quality=ARCHIVE_QUALITY or 90, method=4)
            tmp.unlink(missing_ok=True)
        else:
            tmp.replace(dest)
        return dest.stat().st_size
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# How long a parked run stays worth sweeping. fal's URLs persist indefinitely —
# a July run was refetched successfully this session — but kie and poyo both
# document results as available for ~24 HOURS. So a reseller shot that fails to
# download is recoverable only inside that window, and after it the credits are
# spent for nothing. 20h leaves margin; older rows stay refetchable by hand.
SWEEP_WINDOW_H = 20
SWEEP_EVERY_S = 600


def _sweep_missing() -> int:
    """Re-pull any recent run whose image never landed. Returns how many.

    The immediate path already retries three times before parking the row, so
    everything reaching here has failed three times in a row — which is either
    permanent (a 403, a dead URL) or a stall that outlived one generation. The
    first stays broken and costs one request per sweep; the second heals itself,
    which is the entire point.
    """
    now = time.time()
    healed = 0
    # EVERY character, not the active one. generate.all_runs() is scoped to
    # whoever is active — 391 of 447 rows at the time this was written — so a
    # parked download could hide behind a character switch and quietly age past
    # the reseller's 24h URL window while the sweep looked elsewhere. That is
    # also why /api/runs/missing did not list the tea-shop shot.
    for row in db.runs_all_everywhere():
        # A task we stopped waiting on is the other way an image goes missing,
        # and it needs resolving BEFORE the source_url branch: there is no URL to
        # pull yet, only a task id. poyo is the slow provider this exists for —
        # its work finishes and bills after we have given up, so without this the
        # picture is paid for and unreachable.
        if row.get("pending_tasks") and row.get("file"):
            found = db.runs_owner(row["id"])
            if found:
                _, pcid = found
                pdest = config.char_base(pcid) / "images" / row["file"]
                if not pdest.exists():
                    for task in (row.get("pending_tasks") or []):
                        try:
                            got = providers.reclaim(task.get("provider"),
                                                    task.get("task_id"))
                        except Exception:                   # noqa: BLE001
                            continue          # still failing; try again next sweep
                        if not got:
                            continue          # still running; leave it parked
                        try:
                            _pull_to_disk(got["images"][0]["url"], pdest)
                        except Exception:                   # noqa: BLE001
                            continue
                        row["source_url"] = got["images"][0]["url"]
                        row["provider"] = task.get("provider")
                        row["credits"] = got.get("credits")
                        row["pending_tasks"] = None
                        db.runs_update(row["id"], row)
                        healed += 1
                        break

        url = row.get("source_url")
        if not url or not row.get("file"):
            continue
        found = db.runs_owner(row["id"])
        if not found:
            continue
        _, cid = found
        dest = config.char_base(cid) / "images" / row["file"]
        if dest.exists():
            continue
        try:
            age_h = (now - time.mktime(time.strptime(
                row.get("created", ""), "%Y-%m-%dT%H:%M:%S"))) / 3600
        except Exception:                                   # noqa: BLE001
            age_h = 0
        if age_h > SWEEP_WINDOW_H:
            continue
        try:
            _pull_to_disk(url, dest)
            healed += 1
        except Exception:                                   # noqa: BLE001
            pass        # next sweep, or by hand — never fatal
    return healed


def _start_sweeper() -> None:
    """Heal missing downloads in the background, on startup and every 10 min.

    A daemon thread rather than an async task because _pull_to_disk is blocking
    urllib, and a 20MB 4K image would otherwise stall the event loop serving the
    UI. Wired through lifespan below — on_event is deprecated in this FastAPI.
    """
    def loop() -> None:
        while True:
            try:
                n = _sweep_missing()
                if n:
                    print(f"[sweeper] recovered {n} missing image(s)")
            except Exception as exc:                        # noqa: BLE001
                print(f"[sweeper] {type(exc).__name__}: {str(exc)[:120]}")
            time.sleep(SWEEP_EVERY_S)

    threading.Thread(target=loop, daemon=True, name="refetch-sweeper").start()


# ------------------------------------------------------------------ providers
# Who renders, in what order, and which are switched off. All three resell the
# same Google model, so this is a price/latency decision rather than a quality
# one — measured on one prompt, three references, 4K, scored on her own gallery:
#
#     fal    0.4304   $0.30            66s
#     kie    0.4267   $0.12 (24 cr)   220s
#     poyo   0.4426   $0.175 (35 cr)  265s
#
# 0.016 of spread against seed-to-seed variance of 0.12-0.63 on identical
# prompts. The order is a running preference — "kie is queueing today, put fal
# first" — so it is persisted and editable live rather than an env var needing a
# restart.


class ProviderOrderReq(BaseModel):
    order: list[dict]        # [{name, enabled}] in priority order


@app.get("/api/providers")
def get_providers():
    """The chain, with what each costs and whether it can actually run."""
    rows = []
    for r in providers.load_order():
        c = providers.CATALOGUE[r["name"]]
        rows.append({**r, "label": c["label"], "usd": c["usd"],
                     "seconds": c["seconds"], "note": c["note"],
                     "key_env": c["key"], "has_key": providers.available(r["name"])})
    return {"providers": rows, "chain": providers.chain(),
            # kie's balance is the one that silently decides whether the cheap
            # path works at all: 24 credits per 4K edit, and an empty account
            # falls through to fal at full price without complaining. Cached 60s
            # server-side because the sidebar polls this on every open tab.
            "kie_credits": providers.kie_credits()}


@app.put("/api/providers")
def put_providers(req: ProviderOrderReq):
    saved = providers.save_order(req.order)
    return {"providers": saved, "chain": providers.chain()}


class ModelReq(BaseModel):
    model: str


@app.get("/api/models")
def get_models():
    """The kie model catalogue and which one renders by default.

    `ceiling` is the honest maximum rather than the requested one — seedream
    5-pro has no 4K tier, so a 4K request silently renders at 2K. Surfacing that
    next to the price is the difference between choosing it and being surprised
    by a small face.

    Measured on one project prompt, same references, scored on her own gallery:
    nano-banana-pro 0.7634 · seedream-4.5 0.7724 · 5-pro 0.7638 · 5-lite 0.6658.
    Identity is close across all four; photorealism is NOT — nano renders skin
    and hand anatomy the seedream tiers do not, which no number here reports.
    """
    return {"models": providers.model_rows(), "default": providers.load_model()}


@app.put("/api/models")
def put_model(req: ModelReq):
    try:
        return {"default": providers.save_model(req.model),
                "models": providers.model_rows()}
    except providers.ProviderError as exc:
        raise HTTPException(400, str(exc)) from exc


class VideoReq(BaseModel):
    run_id: str                  # the APPROVED still to animate, OR a video run
                                 # when continue_from is set
    prompt: str = ""             # what should move
    provider: str = "poyo"       # "poyo" | "kie"
    model: str | None = None     # a key from that provider's video catalogue
    duration: int = 5
    resolution: str = "1080p"
    # The LAST frame, on models that take one (kling-3.0). The clip is then
    # interpolated between two approved stills instead of wandering out from
    # one, which is the strongest identity anchor this pipeline can give a clip.
    end_run_id: str | None = None
    # Animate a still the gate did NOT keep. Off by default because a clip
    # inherits the identity of its first frame, so this buys 15 seconds whose
    # identity was never established. On when the owner has looked at the shot
    # and wants it anyway — the run records that it was an explicit choice
    # rather than an oversight.
    allow_ungated: bool = False
    # Continue from the LAST FRAME of an existing clip, so a sequence can run
    # past the model's own duration cap (Kling stops at 10s). The last frame
    # becomes the next clip's first frame, which is the only way to chain
    # image-to-video without a visible jump.
    #
    # Identity compounds here: every link starts from a generated frame rather
    # than an approved still, so drift accumulates. The frame scores on each
    # clip are what make that visible instead of assumed.
    continue_from: bool = False


@app.get("/api/video/models")
def video_models():
    return {"catalogue": providers.video_catalogue(),
            "models": providers.video_rows(),
            "default": providers.DEFAULT_VIDEO_MODEL}


@app.post("/api/video")
def make_video(req: VideoReq):
    """Animate a still that already passed the gate.

    The refusal below is the design, not a safety rail: a clip inherits the
    identity of its first frame, so animating an UNGATED still would produce a
    video whose identity was never established at any point — five seconds of
    unverified claim. Animating a kept shot inherits a number that already
    exists.
    """
    row, cid = _run_and_owner(req.run_id)
    src = config.char_base(cid) / "images" / row["file"]
    if not src.exists():
        raise HTTPException(404, f"{row['file']} is not on disk — refetch it first")

    is_video = (row.get("kind") or "") == "video"
    if req.continue_from:
        if not is_video:
            raise HTTPException(400, "continue_from expects a video run to continue")
        still = _last_frame(src)
    else:
        if is_video:
            raise HTTPException(400, "that run is already a video — pass "
                                     "continue_from to extend it")
        still = src

    v = row.get("verdict") or {}
    ungated = v.get("status") not in ("kept", "reclaimed")
    if req.continue_from:
        ungated = True            # a generated frame was never gated by definition
    elif ungated and not req.allow_ungated:
        raise HTTPException(
            409, f"that still is '{v.get('status')}' — animate a shot the gate kept, "
                 f"or pass allow_ungated to accept a clip whose identity was "
                 f"never established")

    # The end frame gets the SAME gate check as the start frame. A clip is only
    # as anchored as its weakest anchor: interpolating from a kept still to an
    # ungated one hands the model a destination whose identity was never
    # established, and the clip will faithfully arrive there.
    end_still = None
    if req.end_run_id:
        if not providers.video_supports_end_frame(req.provider, req.model):
            raise HTTPException(
                400, f"{req.provider}/{req.model or providers.DEFAULT_VIDEO_MODEL} takes a "
                     f"start frame only — pick a model that accepts an end frame")
        erow, ecid = _run_and_owner(req.end_run_id)
        if (erow.get("kind") or "") == "video":
            raise HTTPException(400, "the end frame must be a still, not a clip")
        if erow["id"] == row["id"]:
            raise HTTPException(400, "the end frame must be a different shot "
                                     "than the start frame")
        end_still = config.char_base(ecid) / "images" / erow["file"]
        if not end_still.exists():
            raise HTTPException(404, f"{erow['file']} is not on disk — refetch it first")
        ev = (erow.get("verdict") or {}).get("status")
        if ev not in ("kept", "reclaimed") and not req.allow_ungated:
            raise HTTPException(
                409, f"the end frame is '{ev}' — animating toward a shot the gate "
                     f"did not keep gives the clip an unverified destination. "
                     f"Pass allow_ungated to accept that.")

    owner = cid
    def run(job: dict) -> dict:
        return generate.generate_video(
            end_still=end_still,
            still=still, prompt=req.prompt or "Gentle natural motion, the camera "
                                             "almost still, her expression unchanged.",
            model=req.model, duration=req.duration, resolution=req.resolution,
            provider=req.provider,
            character=owner, progress=job, source_run=req.run_id,
            session=generate.new_session(f"video: {req.run_id}"),
            meta={"brief": req.prompt,
                  # Recorded so an unscoreable clip is legible later as a
                  # decision, not an accident.
                  "source_status": v.get("status"),
                  "ungated_source": ungated,
                  "end_run": req.end_run_id,
                  "continued_from": req.run_id if req.continue_from else None})

    return {"job": generate.start_job(f"video: {req.run_id}", run)}


class MotionSuggestReq(BaseModel):
    run_id: str                  # the still to read, OR a clip when continuing
    duration: int = 5            # what the suggestions have to fit inside
    idea: str = ""               # the owner steering: "she laughs and looks away"
    end_run_id: str | None = None  # read BOTH frames and direct the journey
    continue_from: bool = False  # read the clip's last frame, not the clip
    # Which model will render it. Only used to bound the duration Claude may
    # recommend — a suggestion of 12s is useless if the chosen model caps at 10.
    provider: str = "kie"
    model: str | None = None


@app.post("/api/video/suggest")
def suggest_motion(req: MotionSuggestReq):
    """Read the shot and propose what should move in it.

    Claude sees the FRAME, not the prompt that made it — so it can direct motion
    against what actually landed (how tight the crop is, where her hands are,
    what is behind her) rather than against what was asked for. Those diverge
    often enough that the run's own brief is passed as context rather than as
    the source of truth.

    Costs a Claude call and nothing else: this proposes text for the box. No
    video is rendered until the owner picks one and presses animate.
    """
    row, cid = _run_and_owner(req.run_id)
    src = config.char_base(cid) / "images" / row["file"]
    if not src.exists():
        raise HTTPException(404, f"{row['file']} is not on disk — refetch it first")

    is_video = (row.get("kind") or "") == "video"
    if req.continue_from or is_video:
        if not is_video:
            raise HTTPException(400, "continue_from expects a video run")
        frame = _last_frame(src)
    else:
        frame = src

    # The brief is what the shot was FOR. A motion suggestion that fights it —
    # animating a considered portrait into a walk-and-talk — is wasted, so it
    # rides along even though the frame is the primary evidence.
    meta = row.get("meta") or {}
    bits = [meta.get("brief") or "", meta.get("pose_id") or "",
            f"wearing {meta['wardrobe']}" if meta.get("wardrobe") else ""]
    context = " · ".join(b for b in bits if b)

    # With an end frame the question changes from "what could move here?" to
    # "how does it get from this to that?", so both images go to Claude.
    end_bytes, end_media = None, "image/png"
    if req.end_run_id:
        erow, ecid = _run_and_owner(req.end_run_id)
        epath = config.char_base(ecid) / "images" / erow["file"]
        if not epath.exists():
            raise HTTPException(404, f"{erow['file']} is not on disk — refetch it first")
        end_bytes = epath.read_bytes()
        end_media = describe.media_type(epath.name, None)

    # Resolved from the catalogue rather than trusted from the client, so the
    # recommendation is always a length the provider will actually accept.
    allowed = None
    try:
        table = providers.KIE_VIDEO if req.provider == "kie" else providers.POYO_VIDEO
        spec = table.get((req.model or providers.DEFAULT_VIDEO_MODEL).strip())
        if spec:
            allowed = list(spec["durations"])
    except Exception:                                   # noqa: BLE001
        allowed = None

    try:
        out = describe.suggest_motion(
            frame.read_bytes(),
            describe.media_type(frame.name, None),
            duration=req.duration,
            context=context,
            idea=req.idea,
            end_bytes=end_bytes,
            end_media=end_media,
            allowed_durations=allowed,
            continuing=bool(req.continue_from or is_video),
        )
    except describe.DescribeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return out


@app.post("/api/runs/import")
def import_run(req: ImportReq):
    """Adopt an orphaned provider URL into a real run.

    The third recovery sibling. /refetch re-pulls a run whose URL we kept and
    whose download failed; /reclaim finishes one we stopped waiting for; this one
    rescues a generation that never got a ROW AT ALL — the case where something
    threw between "task submitted" and "row inserted", so none of the parking
    logic ever ran and the only trace left is a URL in the provider's dashboard.

    That happened on 2026-08-14: five /api/shot calls, four rows, one finished
    and billed poyo image reachable only by hand. Recovering it should not
    require a script.
    """
    url = (req.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "need an http(s) URL")
    cid = req.character or config.get_active()
    if not db.chars_get(cid):
        raise HTTPException(404, f"no such character: {cid}")

    rid = uuid.uuid4().hex[:10]
    # Keep the provider's own extension. _pull_to_disk only re-encodes when the
    # name says .webp, so a .png lands byte-for-byte as served.
    ext = Path(urlparse(url).path).suffix.lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, f"unsupported image type {ext!r}")
    dest = config.char_base(cid) / "images" / f"{rid}{ext}"
    try:
        size = _pull_to_disk(url, dest)
    except Exception as exc:                                # noqa: BLE001
        raise HTTPException(502, f"could not fetch: {str(exc)[:160]}") from None

    width = height = None
    try:
        from PIL import Image
        with Image.open(dest) as im:
            width, height = im.size
    except Exception:                                       # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "that URL did not return a readable image")

    # Scored like any other shot. A recovered image is still a photo of her, and
    # exempting it would put an unmeasured row in a table whose whole point is
    # that every row carries a number.
    # Score against THIS character's gallery, not whoever happens to be active —
    # the same reason refUrl carries ?character=. config.scope_active is the
    # project's own per-request pin.
    token = config.scope_active(cid)
    try:
        verdict = gate.check(dest).dict()
    except Exception as exc:                                # noqa: BLE001
        verdict = {"status": "error", "reason": str(exc)[:200]}
    finally:
        config.unscope_active(token)

    db.runs_insert({
        "id": rid, "session": generate.new_session("recovered"),
        "file": dest.name, "source_url": url,
        "endpoint": "", "provider": req.provider or "unknown",
        "model": req.model or None, "credits": None,
        "width": width, "height": height,
        "prompt": "", "system": "", "refs": [], "pose": None, "seed": None,
        "aspect": "", "resolution": "", "seconds": 0,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "auto_leveled": 0.0, "mark": None,
        "meta": {"brief": req.brief or "recovered from a provider URL",
                 # Provenance, so this row is never mistaken for a normal
                 # generation when the corpus is read back.
                 "recovered": True, "recovered_from": url},
        "verdict": verdict,
    }, character_id=cid)
    return {"ok": True, "id": rid, "file": dest.name, "character": cid,
            "bytes": size, "width": width, "height": height,
            "verdict": verdict}


@app.post("/api/runs/reclaim")
def reclaim_run(req: RefetchReq):
    """Finish a shot whose provider was still working when we stopped waiting.

    The sibling of /api/runs/refetch. That one recovers a run whose URL we had
    and whose DOWNLOAD failed; this one recovers a run we abandoned BEFORE a URL
    existed, because polling ran out its budget. poyo is the slow one and the
    case this was built for: the task keeps running, finishes, and bills, and
    without the parked task id there is no handle left on the picture that was
    paid for.
    """
    doc, cid = _run_and_owner(req.run_id)      # same lookup refetch uses
    pending = doc.get("pending_tasks") or []
    if not pending:
        raise HTTPException(400, "no parked provider task on this run")

    errors = []
    for task in pending:
        try:
            r = providers.reclaim(task.get("provider"), task.get("task_id"))
        except providers.ProviderError as exc:
            errors.append(f"{task.get('provider')}: {exc}")
            continue
        if r is None:
            errors.append(f"{task.get('provider')}: still running")
            continue
        dest = config.char_base(cid) / "images" / doc["file"]
        _pull_to_disk(r["images"][0]["url"], dest)
        doc["source_url"] = r["images"][0]["url"]
        doc["provider"] = task.get("provider")
        doc["credits"] = r.get("credits")
        doc["pending_tasks"] = None
        doc["verdict"] = {"status": "reclaimed",
                          "reason": "recovered from a parked provider task; "
                                    "not re-scored"}
        db.runs_update(req.run_id, doc)
        return {"ok": True, "file": doc["file"], "provider": task.get("provider"),
                "credits": r.get("credits")}
    raise HTTPException(409, "; ".join(errors) or "nothing to reclaim")


@app.post("/api/runs/refetch")
def refetch_run(req: RefetchReq):
    """Re-download a run's image when the file has gone missing.

    A run row is the record; the file is only the picture. An interrupted
    download, a half-finished sync or a disk tidy can take the file while the row
    stays — and until now the only way back was to regenerate, paying again for
    an image that already exists on fal's CDN.

    Only re-downloads. It never regenerates, because a regeneration is a
    DIFFERENT image with the same row, and silently swapping one for the other is
    worse than saying no. Runs made before source_url was recorded have nothing
    to fetch, and are told so plainly.
    """
    row, cid = _run_and_owner(req.run_id)
    dest = config.char_base(cid) / "images" / row["file"]
    if dest.exists():
        return {"ok": True, "file": row["file"], "action": "already-on-disk"}
    url = row.get("source_url")
    if not url:
        raise HTTPException(
            409, "this run predates source-url recording, so there is nothing to "
                 "re-download — regenerate it from the Shoot tab if you want it back")
    try:
        size = _pull_to_disk(url, dest)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"could not re-download: {str(exc)[:160]}") from None
    return {"ok": True, "file": row["file"], "action": "refetched", "bytes": size}


@app.get("/api/runs/missing")
def runs_missing():
    """Runs whose image is not on disk, and whether each can be re-fetched."""
    out = []
    for r in generate.all_runs():
        if r.get("file") and not (IMAGES / r["file"]).exists():
            out.append({"run_id": r["id"], "file": r["file"],
                        "created": r.get("created"),
                        "refetchable": bool(r.get("source_url"))})
    return {"missing": out}


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
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}


def _serve_thumb(src_dir: Path, name: str, box: tuple[int, int] = (512, 512)):
    src = src_dir / Path(name).name
    if not src.exists():
        raise HTTPException(404, name)
    cache_dir = src_dir / ".thumbs"
    cache_dir.mkdir(exist_ok=True)
    cache = cache_dir / f"{Path(name).stem}.jpg"
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        from PIL import Image
        # A clip has no still for PIL to open — it would raise, and since the
        # review grid asks for a thumbnail per row, every video would 500 the
        # tile it lives in. Frame one is the honest poster anyway: for an
        # animated still it IS the approved shot the clip started from.
        poster = _first_frame(src) if src.suffix.lower() in VIDEO_SUFFIXES else src
        im = Image.open(poster).convert("RGB")
        im.thumbnail(box)
        im.save(cache, "JPEG", quality=80)
    return FileResponse(cache)


@app.get("/api/images/{name}/thumb")
def image_thumb(name: str):
    return _serve_thumb(IMAGES, name)


def _first_frame(video: Path) -> Path:
    """Frame one of a clip, cached beside it — the poster the grid shows.

    Cheap on purpose: the same cv2 read as _last_frame, keyed on mtime like every
    other derivative here, so a grid of clips costs one decode each and never
    re-decodes.
    """
    import cv2
    cache = video.parent / ".frames"
    cache.mkdir(exist_ok=True)
    out = cache / f"{video.stem}-first.jpg"
    if out.exists() and out.stat().st_mtime >= video.stat().st_mtime:
        return out
    cap = cv2.VideoCapture(str(video))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise HTTPException(422, f"could not read a first frame from {video.name}")
    cv2.imwrite(str(out), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return out


def _last_frame(video: Path) -> Path:
    """The final frame of a clip, written as a JPEG the video models accept.

    Chaining image-to-video is the only way past a model's duration cap, and it
    needs the previous clip's last frame as the next one's first. Cached beside
    the clip on mtime, like every other derivative here.
    """
    import cv2
    cache = video.parent / ".frames"
    cache.mkdir(exist_ok=True)
    out = cache / f"{video.stem}-last.jpg"
    if out.exists() and out.stat().st_mtime >= video.stat().st_mtime:
        return out
    cap = cv2.VideoCapture(str(video))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Two frames back, not the very last: encoders often leave the final frame
    # duplicated or slightly degraded.
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n - 2))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise HTTPException(422, f"could not read a last frame from {video.name}")
    cv2.imwrite(str(out), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return out


@app.get("/api/images/{name}/hires")
def image_hires(name: str, factor: str = "2"):
    """A DELIVERY copy, upscaled on topaz and cached beside the original.

    Derived on demand into a hidden sibling dir, exactly like .thumbs/ and
    .outfitcrops/, and keyed on the source's mtime. That ordering is the point:
    the archived file stays the single source of truth, the recorded verdict is
    never recomputed, and nothing that scores images can reach this path.

    It must stay that way. Measured on the 5-pro rooftop shot at x2:

        face_px      169 -> 338     (x2.00)
        similarity   0.6417 -> 0.6363  (-0.0055)

    The pixels double and the identity signal does not, because insightface
    detects at det_size=(640,640) and ArcFace embeds a 112x112 crop — a 169px
    face is already downsampled twice before it is read. An upscaled file scored
    by the gate would therefore clear MIN_FACE_PX and the FACE_PLATEAU_PX band on
    manufactured confidence, and would join a corpus of 207 shots calibrated at
    native resolution. This endpoint exists so that never happens by accident:
    upscaling is something you EXPORT, not something you generate.
    """
    src = IMAGES / Path(name).name
    if not src.exists():
        raise HTTPException(404, name)
    cache_dir = IMAGES / ".hires"
    cache_dir.mkdir(exist_ok=True)
    cache = cache_dir / f"{Path(name).stem}@{factor}x.png"
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        try:
            r = providers.kie_upscale(src, factor)
        except providers.ProviderError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            # PNG on purpose: a delivery asset should not be re-compressed,
            # and _pull_to_disk only re-encodes when the name says .webp.
            _pull_to_disk(r["images"][0]["url"], cache)
        except Exception as exc:                          # noqa: BLE001
            raise HTTPException(502, f"upscale downloaded failed: {exc}") from exc
    return FileResponse(cache)


@app.get("/api/wardrobe/{name}/thumb")
def wardrobe_thumb(name: str):
    return _serve_thumb(WARDROBE, name, (256, 384))


@app.get("/api/pose-refs/{name}/thumb")
def pose_ref_thumb(name: str):
    return _serve_thumb(POSE_REFS, name, (256, 384))


@app.get("/api/refs/{name}/thumb")
def ref_thumb(name: str, character: str = ""):
    # ?character= because an <img> cannot send X-Character. Reference FILENAMES
    # collide across characters by design — every one of them has a
    # calib-front.png and a body-canonical.webp — so an unscoped request does not
    # 404, it silently serves whoever happens to be active. That is how one
    # character's calibration face appeared inside another's Bio tab.
    return _serve_thumb(config.char_base(character or None) / "refs", name, (256, 384))


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
    # Specific angles to generate. Without this the only control was `count`,
    # which takes CALIB_FACES[:n] from the front — so topping up a character who
    # already has five meant regenerating those five to reach the sixth. Every
    # duplicate is a paid generation for an image already on disk.
    angles: list[str] | None = None
    # Skip angles she already has. On by default: re-running calibration should
    # cost only what is missing.
    skip_existing: bool = True
    # Which kie model renders this. None uses the project default
    # (providers.load_model). Per-request so the wardrobe can be made on
    # one model and the shot on another without changing the default.
    model: str | None = None


@app.post("/api/calibrate/faces")
def calibrate_faces(req: CalibFacesReq):
    """Generate `count` canonical headshots (identity-locked) on the primary model.

    Faces are generated from the calibration SEED, not the BIO reference — so the
    uploaded seed drives calibration without ever becoming the default identity.
    """
    cfg = _bio_cfg()
    owner = config.get_active()          # pin now; the jobs outlive the request
    seed_name = cfg.get("calib_seed") or cfg.get("reference")
    face = REFS / Path(seed_name).name if seed_name else None
    if not face or not face.exists():
        raise HTTPException(400, "no calibration seed — upload a base image first (Step 1)")
    if req.angles:
        wanted = [a.strip() for a in req.angles]
        unknown = [a for a in wanted if a not in dict(CALIB_FACES)]
        if unknown:
            raise HTTPException(400, f"unknown calibration angles: {unknown}")
        todo = [(a, d) for a, d in CALIB_FACES if a in wanted]
    else:
        todo = CALIB_FACES[:max(1, min(req.count, len(CALIB_FACES)))]

    if req.skip_existing:
        have = {(r.get("meta") or {}).get("angle")
                for r in db.runs_all(character_id=owner)
                if (r.get("meta") or {}).get("calibrate") == "face"}
        todo = [(a, d) for a, d in todo if a not in have]
    if not todo:
        return {"jobs": [], "note": "she already has every angle asked for"}

    jobs = []
    for angle, desc in todo:
        prompt = (f"Headshot portrait of @image1 — {desc}. Plain neutral studio "
                  f"background, soft even lighting, head and shoulders framing. "
                  f"{IDENTITY_LOCK_LINE} Photorealistic, real skin texture, sharp "
                  f"focus on the face.")

        def run(job: dict, prompt=prompt, angle=angle, cid=owner) -> dict:
            row = generate.generate(
                prompt=prompt, system="", refs=[face], aspect="3:4",
                session=generate.new_session(f"calib face: {angle}"), progress=job,
                character=cid, model=req.model,
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
    """Generated faces awaiting selection, newest first.

    Two kinds land here. Calibration faces (`calibrate: face`) are the angles a
    calibrated character is scored on. MASTER-FACE candidates (`guided_seed`) are
    the four a brand-new character is offered at creation — and they are listed
    ONLY while she still has no reference.

    That condition is the point. Creation hands its candidates to a picker in the
    browser, and a picker that lives in page state dies with the tab: close it at
    the wrong moment and the character is left unshootable, holding four perfectly
    good faces with no way to choose one. Surfacing them here means the choice
    always has a home, and once it is made they stop cluttering the list.

    Skip any whose image file is gone — a deleted image must not resurface as an
    empty ghost card. The ledger row is the record; the file is the picture.
    """
    unclaimed = not (REFS / _bio_cfg()["reference"]).exists()
    out = []
    for r in generate.all_runs():
        meta = r.get("meta") or {}
        kind = ("face" if meta.get("calibrate") == "face"
                else "master" if (meta.get("guided_seed") and unclaimed)
                else None)
        if kind and (IMAGES / r["file"]).exists():
            out.append({"id": r["id"], "file": r["file"], "kind": kind,
                        "angle": meta.get("angle"),
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
    # Re-derive the threshold, exactly as /api/gallery/remove already does. Only
    # ADD was missing it, so a character calibrated by adding faces ended up with
    # a full gallery and NO threshold.json — silently judged against
    # DEFAULT_THRESHOLD instead of her own measured stranger floor, which makes
    # her "kept" mean something different from everyone else's. Best-effort:
    # under three entries there is nothing to derive yet, and that must not block
    # the add that gets you to three.
    threshold = None
    try:
        threshold = gate.calibrate_from_gallery()["threshold"]
    except Exception:  # noqa: BLE001 — too few faces yet, or an unreadable gallery
        pass
    return {"view": name, "threshold": threshold,
            "yaw": round(face.yaw, 1), "face_px": face.width,
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
def ref_file(name: str, character: str = ""):
    p = config.char_base(character or None) / "refs" / Path(name).name
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
    # Re-derive the threshold. /api/gallery/from-run and /api/gallery/remove both
    # already do this; from-ref was the one door left that changed the yardstick
    # without re-measuring it, and the drift is silent because everything keeps
    # working — the gallery just stops agreeing with the floor derived from it.
    #
    # Kiara is the case. Her `profile-right` (yaw +70.3) was added here after her
    # threshold was computed, so 13 vectors were being scored against a floor
    # derived from 12: stored 0.58 against a recomputed 0.4761. Drop that one
    # entry and the recomputation returns 0.5795 — which is where the stored
    # number came from. Every collaboration rejection of hers tonight (0.4811,
    # 0.4880, 0.5024, 0.5093, 0.5251) sat inside that 0.10 gap.
    #
    # Best-effort, matching from-run: under three entries there is nothing to
    # derive, and that must not block the add that gets you to three.
    threshold = None
    try:
        threshold = gate.calibrate_from_gallery()["threshold"]
    except Exception:  # noqa: BLE001 — too few faces yet, or an unreadable gallery
        pass
    return {"view": req.view, "yaw": round(face.yaw, 1), "threshold": threshold,
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

    # BODY CANDIDATES, restored from the ledger rather than remembered by the tab.
    # A generated body preview used to live only in page state: it was filtered
    # out of `shots` and surfaced nowhere else, so switching to Review — or
    # reloading — silently discarded a body you had just paid to generate, with
    # no way back to it. The runs were never lost; nothing was showing them.
    out["body_candidates"] = [
        {"run_id": r["id"], "file": r["file"], "created": r.get("created")}
        for r in generate.all_runs()
        if (r.get("meta") or {}).get("body_ref_create")
        and not (r.get("meta") or {}).get("body_resolved")
        and (IMAGES / r["file"]).exists()
    ][:8]
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
    row, cid = _run_and_owner(run_id)
    # Name the identity per-character (e.g. robin-identity.png). A shared name
    # ('kiara-identity.png' for everyone) made the thumbnail URL identical across
    # profiles, so the browser served a CACHED face from another character even
    # though the file on disk was correct. Per-character names keep URLs distinct.
    base = config.char_base(cid)
    dest = _promote(base / "images" / row["file"], base / "refs" / f"{cid}-identity.png")
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
    # Which kie model renders this. None uses the project default
    # (providers.load_model). Per-request so the wardrobe can be made on
    # one model and the shot on another without changing the default.
    model: str | None = None


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

    owner = config.get_active()          # pin now; the job outlives the request
    def run(job: dict) -> dict:
        return generate.generate(
            prompt=prompt, system="", refs=refs, aspect=aspect,
            session=generate.new_session("body reference"), progress=job,
            character=owner, model=req.model,
            meta={"body_ref_create": True, "shape": shape_clean,
                  "shape_ref": req.shape_ref, "turnaround": req.turnaround},
            fallback_endpoint=SCENE_EDIT, extra=extra)

    return {"job": generate.start_job("body reference", run)}


@app.post("/api/bio/body-ref/save")
def body_ref_save(payload: dict = Body(...)):
    """Lock a generated body image in as the BODY reference (@image2 everywhere)."""
    run_id = payload["run_id"]
    row, cid = _run_and_owner(run_id)
    base = config.char_base(cid)
    dest = _promote(base / "images" / row["file"], base / "refs" / "body-canonical.png")
    _resolve_body_candidate(run_id, "saved")
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
    row, cid = _run_and_owner(run_id)
    base = config.char_base(cid)
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ").strip() or run_id
    _promote(base / "images" / row["file"], base / "bodies" / f"{safe}.png")
    _resolve_body_candidate(run_id, "saved")
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


def _run_and_owner(run_id: str) -> tuple[dict, str]:
    """Resolve a run for an action that PROMOTES it — to a reference, a body, an
    outfit, a pose ref.

    These all used to look the run up in the ACTIVE character's ledger, which
    quietly made every one of them a race. Generating an outfit and saving it are
    separate clicks minutes apart; switch character in between and the save
    returned 404 for an image sitting right there on screen, with the generation
    stranded. Observed exactly that on a wardrobe save.

    Resolving globally also fixes the subtler half: the promotion now lands in the
    folder of the character the run BELONGS to, so it can never file one
    character's outfit under another's name.
    """
    hit = db.runs_owner(run_id)
    if not hit:
        raise HTTPException(404, run_id)
    return hit


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

    Case is the same class of bug. An outfit saved as "Dayout9" and a row keyed
    "DayOut9" are the same garment to everyone except this function, which
    stranded the row: it listed in the picker and 400'd on selection with "no
    such wardrobe". Exact match still wins — two files differing only in case are
    two files — but a unique case-insensitive match beats returning nothing.
    """
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = directory / f"{ident}{ext}"
        if p.exists():
            return p
    if not directory.exists():
        return None
    hits = [p for p in directory.iterdir()
            if p.is_file() and p.stem.lower() == ident.lower()
            and p.suffix.lower() in _IMAGE_EXT]
    return hits[0] if len(hits) == 1 else None


def _wardrobe_meta(cid: str | None = None) -> dict:
    return db.wardrobe_meta(cid)


def _save_wardrobe_meta(d: dict, cid: str | None = None) -> None:
    db.wardrobe_save_all(d, cid)


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


def _unique_wardrobe_path(name: str, cid: str | None = None) -> Path:
    """No-clobber outfit filename: never overwrite an existing outfit (that is how
    an image and a different outfit's description desync). Suffixes -2, -3, … ."""
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ").strip() or "outfit"
    safe = "-".join(safe.split())

    # Testing only "<name>.png" was a live no-clobber HOLE. Every wardrobe file
    # is .webp since the archive migration, so ".png does not exist" was always
    # true, this returned a taken name as free, and _promote then rewrote the
    # suffix to .webp and copied straight over the existing outfit. Ask whether
    # the NAME is taken, in any image extension and in any case — the same
    # question a case-insensitive filesystem would ask when this folder is
    # carried to another machine.
    wd = config.char_base(cid) / "wardrobe"
    taken = {p.stem.lower() for p in wd.iterdir()
             if p.is_file() and p.suffix.lower() in _IMAGE_EXT} if wd.exists() else set()
    if safe.lower() not in taken:
        return wd / f"{safe}.png"
    n = 2
    while f"{safe}-{n}".lower() in taken:
        n += 1
    return wd / f"{safe}-{n}.png"


def _canon_category(category: str) -> str:
    """Canonical category / name-prefix: alnum only, first letter upper (e.g.
    'day out' -> 'Dayout', 'night' -> 'Night')."""
    c = "".join(ch for ch in (category or "") if ch.isalnum())
    return (c[0].upper() + c[1:]) if c else "Outfit"


def _next_wardrobe_name(category: str, cid: str | None = None) -> str:
    """Auto-name an outfit as <Category><next number> — the number continues that
    category's existing sequence (Dayout1..9 -> Dayout10)."""
    import re
    cat = _canon_category(category)
    wd = config.char_base(cid) / "wardrobe"
    mx = 0
    for p in (wd.iterdir() if wd.exists() else []):
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
    the original if no face is found or the face already fills the frame.

    The cache sits BESIDE the outfit it came from, derived from the file's own
    path rather than from OUTFIT_CROPS. That constant is a CharPath onto whoever
    is active, which was fine while every outfit belonged to the character on
    screen and is wrong the moment a scene dresses two women: cropping a guest's
    outfit would file the crop under the owner. Locating the cache from the
    source needs no character threaded through it and cannot be pointed at the
    wrong one — the same failure already fixed three times elsewhere today.
    """
    from PIL import Image
    crops = Path(path).parent / ".outfitcrops"
    crops.mkdir(exist_ok=True)
    # Archive format, not PNG: these are crops of 4K turnarounds, and as PNG the
    # cache grew to 1.4 GB — larger than the wardrobe it was derived from, for
    # files that are rebuilt on demand and never shown to anyone.
    cache = crops / f"{path.stem}.{ARCHIVE_FORMAT}"
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return cache
    (crops / f"{path.stem}.png").unlink(missing_ok=True)   # pre-WebP crop
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
    # fal's own moderation dial, 1 (strictest) to 6, default 4 — same contract as
    # SceneReq. A turnaround is the FIRST thing a garment goes through, so an
    # intimates brief the default refuses never reaches a shot at all: the
    # wardrobe item cannot be created, and the category looks impossible when it
    # is only unattempted. Opt-in per request; not a raised global default.
    #
    # MEASURED, so nobody spends another two generations on it: this dial does
    # NOT rescue an intimates turnaround. A sheer embroidered teddy described
    # with the garment's own retail vocabulary was refused at the default AND at
    # 6 (least strict), both times as
    #   {"loc": ["body", "prompt"], "type": "content_policy_violation"}
    # — `loc` is the PROMPT, not the image. safety_tolerance governs output
    # moderation; it has no bearing on an input screen, so raising it changes
    # nothing here. Keep the parameter (it is the right control to expose, and
    # it does apply to shots), but a prompt-level refusal is a provider policy
    # boundary, not a tuning problem.
    safety_tolerance: str | None = None
    # Which kie model renders the turnaround. None keeps the default.
    model: str | None = None


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
        f"{identity_clause} {build_clean} "
        # THE ANTI-SLIM CLAUSE, which this path was missing and body_ref_create
        # has always had. Naming the build is not enough: main.py's own picker
        # comment says text alone regresses toward slim, which is why
        # _BUILD_FIGURE ends in "distinctly full-figured, not slim".
        #
        # Measured here. Ethnic1's turnaround was generated from
        # body-canonical (curvy athlete full) with the proportions clause already
        # present, and came back a standard slim fashion-model physique wearing
        # the saree. Every shot in that outfit then inherited the flattened
        # figure, because a shot takes its body from the wardrobe sheet — so this
        # one regression propagates to everything she wears.
        #
        # Nothing caught it: a turnaround is gated=False by design (a garment
        # swatch is not a photo of her), so no number was watching this step.
        "Her FIGURE is as important as the garment here: render her build "
        "faithfully and prominently exactly as @image2 shows it — the same "
        "bust-to-waist-to-hip ratio and the same curves — never slimming her "
        "down and never substituting a generic slim fashion-model physique. "
        f"Identical outfit, proportions, stance and lighting "
        f"across all four panels.\n\nShe is wearing: {outfit}. Change ONLY the clothing "
        "to this outfit.\n\nPhotorealistic RAW photograph quality, real skin "
        "texture, ultra-sharp detail.")

    owner = config.get_active()          # pin now; the job outlives the request
    def run(job: dict) -> dict:
        # Generate only — no save. The image lands in data/images like any run;
        # the user saves it into the wardrobe via /api/wardrobe/from-run after
        # they see and approve the preview.
        return generate.generate(prompt=prompt, system="", refs=refs, aspect="16:9",
                                 session=generate.new_session(f"create outfit: {label}"),
                                 progress=job, character=owner, model=req.model,
                                 # A turnaround is a garment swatch, not a photo of
                                 # her — /api/wardrobe/from-run uses only its clothing.
                                 # Gating it scores whichever of its four panels
                                 # renders the biggest face, at ~200px: 116 of 118 were
                                 # rejected for face size alone. Not a measurement.
                                 gated=False,
                                 meta={"outfit_create": req.outfit, "body": _bodies().get("active"),
                                       "safety_tolerance": req.safety_tolerance},
                                 # NOTE: this fallback is a no-op and kept only as a
                                 # marker. It was written when the primary was
                                 # gpt-image-2 ("render it on the scene model instead
                                 # of dead-spinning"), but PRIMARY_EDIT is now
                                 # SCENE_EDIT itself, and generate() only appends a
                                 # fallback when it differs from the primary. A
                                 # refusal here is therefore nano-banana's own, and
                                 # safety_tolerance below — not this line — is what
                                 # answers it.
                                 fallback_endpoint=SCENE_EDIT,
                                 safety_tolerance=req.safety_tolerance,
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
    row, cid = _run_and_owner(run_id)
    # Auto-name <Category><next#>; no-clobber as a final safety net.
    dest = _promote(config.char_base(cid) / "images" / row["file"],
                    _unique_wardrobe_path(_next_wardrobe_name(category, cid), cid))
    # Persist the description it was made with + its category, keyed to THIS file's
    # stem, so image and description can never belong to different outfits.
    meta = _wardrobe_meta(cid)
    meta[dest.stem] = {"description": row.get("meta", {}).get("outfit_create"),
                       "category": category, "created": row.get("created")}
    _save_wardrobe_meta(meta, cid)
    return {"id": dest.stem, "file": dest.name, "category": category}


@app.get("/api/wardrobe/{name}/file")
def wardrobe_file(name: str, character: str = ""):
    p = config.char_base(character or None) / "wardrobe" / Path(name).name
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
    row, cid = _run_and_owner(run_id)
    base = config.char_base(cid)
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or run_id
    dest = _promote(base / "images" / row["file"], base / "pose-refs" / f"{safe}.png")
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

# SCOPED BY CHARACTER, all of it. These used to resolve through the NAILS /
# NAILS_META CharPath proxies onto whichever character happened to be ACTIVE,
# with no cid anywhere — the identical shape of the bug that filed one
# character's outfit under Kiara and then showed Kiara's dress in Alexa's picker.
# It was invisible while nails were only ever reached from inside one open
# Studio; a scene with a cast of three reaches three characters' nails at once,
# which is exactly the condition that made the wardrobe version visible.
#
# Same fix as the precedents: take a cid and default it to the active character,
# so existing single-character callers are unchanged. See _wardrobe_meta(cid),
# _corner_file(key, cid) and gate.load_gallery(cid).

def _nails_dir(cid: str | None = None) -> Path:
    return config.char_base(cid) / "nails"


def _nails_meta_path(cid: str | None = None) -> Path:
    return config.char_base(cid) / "state" / "nails.json"


def _nails_meta(cid: str | None = None) -> dict:
    p = _nails_meta_path(cid)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_nails_meta(d: dict, cid: str | None = None) -> None:
    p = _nails_meta_path(cid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2) + "\n")


def _nails(cid: str | None = None) -> list[dict]:
    meta = _nails_meta(cid)
    d = _nails_dir(cid)
    out = []
    for p in sorted(d.iterdir()) if d.exists() else []:
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            m = meta.get(p.stem, {}) or {}
            out.append({"id": p.stem, "file": p.name,
                        "name": m.get("name") or p.stem,
                        "category": m.get("category") or "Uncategorized",
                        "description": m.get("description", "")})
    return out


@app.get("/api/nails")
def list_nails(character: str = ""):
    return {"nails": _nails(character or None)}


def _next_nail_name(color: str, cid: str | None = None) -> str:
    """<color><n> — n is one past the highest existing index for that colour."""
    color = (color or "other").strip().lower() or "other"
    nums = []
    for m in _nails_meta(cid).values():
        if (m.get("category") or "").strip().lower() == color:
            nm = (m.get("name") or "").strip().lower()
            if nm.startswith(color) and nm[len(color):].isdigit():
                nums.append(int(nm[len(color):]))
    return f"{color}{max(nums) + 1 if nums else 1}"


@app.post("/api/nails/upload")
async def nails_upload(file: UploadFile = File(...), color: str = Form(""),
                       character: str = Form("")):
    """Save a manicure reference image. Colour is the category; the name is
    auto-assigned as <colour><n>. Image-only — no description/Claude call (the
    image is used directly as the reference)."""
    cid = character or None
    data = await file.read()
    d = _nails_dir(cid)
    d.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"
    i = 1
    while _find_by_id(d, f"nail{i}"):
        i += 1
    dest = d / f"nail{i}{ext}"
    dest.write_bytes(data)
    color = (color.strip().lower() or "other")
    name = _next_nail_name(color, cid)
    meta = _nails_meta(cid)
    meta[dest.stem] = {"name": name, "category": color, "description": ""}
    _save_nails_meta(meta, cid)
    return {"id": dest.stem, "file": dest.name, "name": name, "category": color, "description": ""}


class NailDescReq(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None


@app.put("/api/nails/{name}")
def nails_update(name: str, req: NailDescReq, character: str = ""):
    cid = character or None
    stem = Path(name).stem
    meta = _nails_meta(cid)
    cur = meta.get(stem, {}) or {}
    if req.name is not None:
        cur["name"] = req.name.strip() or stem
    if req.category is not None:
        cur["category"] = req.category.strip() or "Uncategorized"
    if req.description is not None:
        cur["description"] = req.description
    meta[stem] = cur
    _save_nails_meta(meta, cid)
    return {"id": stem, **cur}


@app.get("/api/nails/{name}/file")
def nails_file(name: str, character: str = ""):
    p = _nails_dir(character or None) / Path(name).name
    if not p.exists():
        raise HTTPException(404, name)
    return FileResponse(p)


@app.get("/api/nails/{name}/thumb")
def nails_thumb(name: str, character: str = ""):
    # `character` is a QUERY parameter and not only a header because an <img>
    # cannot send X-Character. That is precisely how the wardrobe version of this
    # bug reached the UI: the JSON list was correctly scoped, and then every
    # thumbnail fell back to the active character and showed the wrong woman's
    # things. The scope_character middleware honours ?character= for the same
    # reason.
    return _serve_thumb(_nails_dir(character or None), name, (256, 256))


@app.delete("/api/nails/{name}")
def nails_delete(name: str, character: str = ""):
    cid = character or None
    stem = Path(name).stem
    (_nails_dir(cid) / Path(name).name).unlink(missing_ok=True)
    meta = _nails_meta(cid)
    if stem in meta:
        del meta[stem]
        _save_nails_meta(meta, cid)
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


def _validate_moments() -> None:
    """Every key a moment names must resolve. Checked at import, loudly.

    The scenes_data docstring has claimed "Validated on import" since the file
    was written and nothing validated anything. That was survivable at 26 moments
    with one cross-referenced field; it is not at 66 with eight, because a typo in
    a place, interaction, framing or lighting key does not raise — it silently
    produces a moment that fills in nothing, which reads as "this preset does not
    do much" rather than as a bug.

    Deliberately an assert at import rather than a test: these libraries are
    edited as data by whoever is authoring content, and the failure should arrive
    when the server starts rather than when someone eventually runs the suite.
    """
    inter = {i for g in INTERACTIONS.values() for i in g}
    light = {i for g in lighting_data.LIGHTING.values() for i in g}
    allowed = {
        "place": set(_CORNER) | {""},
        "interaction": inter | {""},
        "framing": set(framing_data.FRAMING),
        "lighting": light | {""},
        "time_of_day": set(lighting_data.TIME_OF_DAY) | {""},
        "holder": set(promptlib.CAMERA_HOLDERS),
        "flaws": set(promptlib.SNAPSHOT_FLAWS),
        "shot_type": set(promptlib.SHOT_TYPES),
    }
    bad = [f"{grp}.{mid}: {field}={m.get(field, '')!r}"
           for grp, items in MOMENTS.items()
           for mid, m in items.items()
           for field, ok in allowed.items()
           if m.get(field, "") not in ok]
    if bad:
        raise ValueError("scenes_data has unresolvable keys: " + "; ".join(bad))


def _validate_interactions() -> None:
    """The placeholder rules, enforced rather than documented.

    Three checks on the DATA, each for a failure that has actually happened:

    1. A duplicate id. Two groups can each define one and the later silently wins
       in the flattened lookup.
    2. C in an entry a cast of two can be offered. The third tag would never be
       substituted and the letter C would reach the model as itself.
    3. A standalone capital A used as the ENGLISH ARTICLE. The substitution cannot
       tell it from the placeholder, so "A half-hug that neither..." goes out as
       "@image1 half-hug". Caught by the invariant that placeholders come in
       pairs: A names the FIRST of at least two people, so a text naming A without
       naming B is either an article or a typo. That found three real instances in
       this library, one of them written into the same commit as the rule.

    Plus one check on the MECHANISM. The substitution was once a bare str.replace
    and ate the A of "All", the B of "Both" and the C of "Caught" — 11 of the then
    35 entries, reaching the model as "@image1ll three standing in a row". A data
    check cannot catch that regression, because the word-boundary substitution
    this validator would use to look for it is the very thing that would have been
    reverted. So the mechanism is exercised directly on a string built to break
    the old version.
    """
    canary = "All of them. Both of us. Caught mid-hug. A holds B and C waits."
    probe = canary
    for i, sentinel in enumerate(("\x00", "\x01", "\x02")):
        probe = re.sub(rf"\b{'ABC'[i]}\b", sentinel, probe)
    if "All" not in probe or "Both" not in probe or "Caught" not in probe:
        raise ValueError("the A/B/C substitution is eating whole words again — "
                         "it must match on a word boundary")

    seen: set[str] = set()
    bad: list[str] = []
    for items in INTERACTIONS.values():
        for iid, d in items.items():
            txt, mc = d["text"], d["min_cast"]
            if iid in seen:
                bad.append(f"{iid}: duplicate id")
            seen.add(iid)
            if re.search(r"\bC\b", txt) and mc < 3:
                bad.append(f"{iid}: names C at min_cast {mc}")
            if re.search(r"\bA\b", txt) and not re.search(r"\bB\b", txt):
                bad.append(f"{iid}: names A without B — article, or a typo")
    if bad:
        raise ValueError("interactions_data is malformed: " + "; ".join(bad))


_validate_moments()
_validate_interactions()
# Only these rooms open to the outside — the balcony/window VIEW (buildings, street,
# skyline) belongs here and NOWHERE else. Every other corner is a fully interior room.
_VIEW_ROOMS = {"balcony", "terrace", "living_room"}


def _home(cid: str | None = None) -> dict:
    HOME_PATH = _state_path("home.json", cid)
    if HOME_PATH.exists():
        try:
            d = json.loads(HOME_PATH.read_text())
            return {"style": (d.get("style") or "").strip(),
                    "surroundings": (d.get("surroundings") or "").strip()}
        except Exception:  # noqa: BLE001
            pass
    return {"style": "", "surroundings": ""}


def _corner_file(key: str, cid: str | None = None) -> Path | None:
    """The stored image for a corner, whatever its extension.

    `cid` names whose place. A scene offers the OWNER's corners — "Kiara's
    kitchen" — and without this it would resolve through PLACES to whoever
    happens to be active, which is the same failure already fixed in
    db.runs_all, the wardrobe helpers, the gate loaders and _outfit_ref.
    """
    return _find_by_id(config.char_base(cid) / "places" if cid else PLACES, key)


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


def _corner_prompt(key: str, cid: str | None = None) -> str:
    """The scene prompt for one corner, from the shared house style + corner type.

    Split out of the endpoint so guided character creation builds her whole flat
    through exactly the same wording the Home tab uses — one house, one prompt,
    whichever door you came in by.
    """
    corner = _CORNER[key]
    h = _home(cid)
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


def _render_corner(key: str, job: dict, cid: str | None = None) -> dict:
    """Generate one corner and drop it into its slot. Shared by the Home tab and
    guided character creation (which pins `cid` for the life of its job)."""
    corner = _CORNER[key]
    places = config.char_base(cid) / "places"
    places.mkdir(parents=True, exist_ok=True)
    row = generate.generate(
        prompt=_corner_prompt(key, cid), system="", refs=None, aspect="4:3",
        character=cid,
        endpoint=SCENE_TEXT2IMG, session=generate.new_session(f"home: {corner['label']}"),
        # An empty room has no face in it by design ("NO people" above), so
        # gating one only ever records no_face — a failure that isn't one.
        gated=False,
        progress=job, meta={"home_create": key})
    src = config.char_base(cid) / "images" / row["file"]
    if src.exists():
        _promote(src, places / f"{key}.png")
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
def home_thumb(key: str, character: str = ""):
    # Corner KEYS collide across every character — they all have a "kitchen" and
    # a "bedroom". Unscoped, this serves the active character's room inside
    # someone else's Home tab.
    f = _corner_file(key, character or None)
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
@app.get("/api/characters/options")
def character_options():
    """The axes a NEW character can be specified along, for the drawer to render.

    Served rather than duplicated in the frontend so the vocabularies have one
    home: an option the backend cannot map is one the UI must not offer, and a
    stale copy in JS would silently fall back to "Claude decides" while looking
    like a choice.
    """
    return {
        "max_faces": MASTER_FACE_CANDIDATES,
        # Whose figure can be copied into a new character, free.
        "bodies_available": _bodies_available(),
        "looks": list(LOOKS),
        "default_look": DEFAULT_LOOK,
        "face_shapes": FACE_SHAPES,
        "builds": BUILDS,
        "skin_tones": list(SKIN_TONES),
        "skin_undertones": list(SKIN_UNDERTONES),
        # {axis: [option, ...]} — the label IS the value; the noun phrase it maps
        # to is the backend's business.
        "pickers": {k: list(v) for k, v in PICKERS.items()},
    }


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
        "optics": [{"id": k, **v} for k, v in promptlib.OPTICS.items()],
        "exposure": [{"id": k, **v} for k, v in promptlib.EXPOSURE.items()],
        "grooming_state": [{"id": k, **v} for k, v in promptlib.GROOMING_STATE.items()],
        "aspects": framing_data.ASPECTS,
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


# How much saved outfit TEXT rides along when the outfit also has an IMAGE.
# A turnaround shows fabric, print, cut and drape better than any sentence;
# what it cannot show is lip colour, nail colour and small accessories, and
# those fit comfortably here. Set by the failure that found it: 1,940
# characters of saree description overrode its own reference print.
_OUTFIT_TEXT_CAP = 600

# A selfie is cropped at the waist at the very most, so most of a garment
# description names things the frame physically cannot contain — the hem, the
# slit, the shoes. Left in, that text does not just waste room, it FIGHTS the
# crop: the model widens out to fit the outfit it was told to show, which is why
# a selfie came back full-length with the phone visible as a prop.
#
# Measured on the failing shot: 406 characters of selfie direction against 2,626
# of wardrobe and body catalogue — 87%. Trimmed harder here than the normal cap,
# because "the picture already carries it" and "the picture cannot show it" are
# different problems and the second one is worse.
_SELFIE_TEXT_CAP = 220


# In water, hair is the tell — and the pipeline was actively causing it.
#
# The identity lock says "her face, skin, HAIR, features and identity come only
# from @image1" (prompter.py) and "skin and hair come only from @image1"
# (the body-reference line below). @image1 is her calibration reference: dry,
# styled, soft waves. So a pool shot carried an absolute instruction to copy dry
# hair from a photograph, against a pose merely mentioning water — and the
# absolute instruction won. Every pool generation came back with a bone-dry head
# on a wet body, which is the single clearest AI tell there is.
#
# The resolution is that hair COLOUR and LENGTH are identity; hair STATE is not.
# This clause frees the state and leaves identity untouched.


def _is_wet_pose(pose_id: str | None, brief: str = "") -> bool:
    """True when the scene puts her in water, so the dry-hair lock must be lifted.

    Reads the Pool & Water category rather than matching a prefix, so a renamed
    id cannot silently stop being wet, and also catches a brief that describes
    water without a pose being picked.
    """
    if pose_id and pose_id in (promptlib.POSE_GROUPS.get("Pool & Water") or {}):
        return True
    return bool(re.search(r"\b(pool|swim|swimming|underwater|sea|ocean|beach|"
                          r"shower|rain|soaked|drenched|jacuzzi|hot tub)\b",
                          brief or "", re.I))


# Every selfie category, not just the handheld one. This checked "Selfie
# (Handheld)" alone, which was correct on the day it was written and stopped
# being correct the moment the library grew: "Selfie (Mirror)" (25) and "Selfie
# (Car)" (50) are 75 poses that are unmistakably selfies and were getting the
# 600-char outfit cap meant for a photograph someone else took. The cap exists
# because a selfie crop physically cannot contain a hem or a shoe — which is as
# true in a car as it is at arm's length.
_SELFIE_GROUPS = ("Selfie (Handheld)", "Selfie (Mirror)", "Selfie (Car)")

# The registers the phone doctrine applies to. `editorial`, `luxury` and
# `commercial` ARE a professional shoot — telling them "never a professional
# camera" contradicts their own opener. Everything that gates on register reads
# this one tuple.
PHONE_REGISTERS = ("candid", "street", "pov")

# NOBODY ELSE IN FRAME, unless the brief asked for someone.
#
# The scene path has had this since the nightclub shot came back with NINE faces.
# The shot path never got it, and the shot path is where nearly every image is
# made. Measured over 613 runs: 26 were scored out of a crowd — one of them out
# of EIGHTEEN faces — and 7 of those were KEPT.
#
# It matters more than set dressing because of how `gate.check` picks a subject.
# It scores the face that best matches the gallery, which is the right rule (the
# largest face is whoever stood nearest the lens, not necessarily her) and it
# makes every extra person an extra chance to score a stranger and call it her.
# A max over four candidates is not the same measurement as a score.
#
# Suppressed by DEFAULT and lifted by the brief, not the other way round: of 347
# solo briefs, 284 never mention another person and 63 explicitly want one. A
# blanket suppression would fight the briefs that ask for a club or a market;
# a blanket allowance is what produced the eighteen faces.
_WANTS_PEOPLE = re.compile(
    r"\bcrowd\w*\b|\bpeople\b|\bbystander\w*\b|\bpassers?[- ]?by\b|"
    r"\bstranger\w*\b|\bfriends?\b|\bguests?\b|\bpatrons?\b|\bdancers?\b|"
    r"\bcouple\b|\bgroup\b|\bqueue\b|\bwedding\b|\bmarriage\b|\bconcert\b|"
    r"\bcelebrat\w*\b|\bbirthday\b|\bparty\b|\bwith her (mother|sister|friend)\b",
    re.I)



def _wants_people(brief: str, allow: bool) -> bool:
    """True when someone other than her may be in frame."""
    return bool(allow or _WANTS_PEOPLE.search(brief or ""))


def _is_selfie_pose(pose_id: str | None, brief: str = "",
                    camera_holder: str = "") -> bool:
    """True when this shot is a selfie, from the pose, the brief, or the holder.

    Read from the library rather than a prefix match, so a renamed id cannot
    silently stop being a selfie — and now also from the brief, the same widening
    `_is_wet_pose` already has. Run 15e2298957 is why: the brief said "took her
    phone and captured imperfect selfie", no pose was picked, and every selfie
    rule in the pipeline sat out a shot that was explicitly asked to be one.
    """
    if camera_holder in ("selfie", "mirror"):
        return True
    if pose_id and any(pose_id in (promptlib.POSE_GROUPS.get(g) or {})
                       for g in _SELFIE_GROUPS):
        return True
    return bool(re.search(r"\bselfie(s)?\b|\bselfi\b", brief or "", re.I))


# Who held the camera, and how imperfect the frame is, read out of the brief when
# the caller did not say.
#
# Both knobs have existed on ShotReq since they were written, are served to the
# UI, and are wired into the Collaborate page. Measured over the first 607 runs:
# `camera_holder` was set 7 times and `flaws` was set ZERO times. A control that
# is never reached is not a control, and the Shoot tab — where nearly every image
# is made — never sent either one.
#
# So they are inferred here as a floor, never a ceiling: an explicit value always
# wins, and whatever is inferred is recorded in meta so the run says what it did
# rather than doing it invisibly.
_MIRROR_RE = re.compile(r"\bmirror\b|\breflection\b", re.I)
_IMPERFECT_RE = re.compile(
    r"\bimperfect\b|\bcandid\b|\bunposed\b|\bmessy\b|\bcasual\b|\bnatural\b|"
    r"\bunfiltered\b|\bunedited\b|\brandom\b|\bquick\b|\beveryday\b", re.I)
_WOKEN_RE = re.compile(
    r"\bjust wo(ke|ken)\b|\bwaking up\b|\bwakes up\b|\bwoke up\b|\bhalf.asleep\b|"
    r"\bsleepy\b|\byawn(ing|s|ed)?\b|\bbed ?head\b|\bfirst thing in the morning\b",
    re.I)
_WORKOUT_RE = re.compile(
    r"\bgym\b|\bworkout\b|\bworking out\b|\bexercis\w*\b|\byoga\b|\brunning\b|"
    r"\bjog\w*\b|\bsweaty\b|\bpost.workout\b", re.I)
# A studio/editorial brief is asking for exactly the professional optics the
# phone default forbids. Detect it so the inference stands down rather than
# telling a deliberate studio shoot it may not have a portrait lens.
_STUDIO_RE = re.compile(
    r"\bstudio\b|\beditorial\b|\bphotoshoot\b|\bphoto ?shoot\b|\bcampaign\b|"
    r"\bcatalogue\b|\bcatalog\b|\blookbook\b|\bprofessional (photo|camera|shoot)\b",
    re.I)


def _infer_capture(brief: str, pose_id: str | None, holder: str, flaws: str,
                   optics: str = "", grooming_state: str = "",
                   shot_type: str = "candid"
                   ) -> tuple[str, str, str, str, list[str]]:
    """Return (camera_holder, flaws, optics, grooming_state, notes).

    Explicit values always pass through untouched — this is a floor for the
    knobs nobody sets, not a policy that overrides the ones they do.
    """
    notes: list[str] = []
    b = brief or ""
    studio = bool(_STUDIO_RE.search(b)) or shot_type in (
        "editorial", "luxury", "commercial")

    if not holder:
        mirror_pose = bool(pose_id and pose_id in (
            promptlib.POSE_GROUPS.get("Selfie (Mirror)") or {}))
        if mirror_pose or (_MIRROR_RE.search(b) and _is_selfie_pose(None, b)):
            holder = "mirror"
            notes.append("camera_holder=mirror inferred from the brief")
        elif _is_selfie_pose(pose_id, b):
            holder = "selfie"
            notes.append("camera_holder=selfie inferred from the brief")

    if not flaws and _IMPERFECT_RE.search(b):
        # `subtle`, never `snapshot`. snapshot sets expected_low=True and costs
        # real similarity; asking for it is a decision, not an inference.
        flaws = "subtle"
        notes.append("flaws=subtle inferred from the brief")

    if not optics and not studio:
        # A selfie is held at arm's length on the front camera; anything else on
        # a phone register is still a phone, and still deep-focus. This is the
        # line that answers the 51 unasked-for "85mm"s.
        optics = "phone-front" if holder in ("selfie", "mirror") else "phone-deep"
        notes.append(f"optics={optics} inferred (phone register)")

    if not grooming_state:
        if _WOKEN_RE.search(b):
            grooming_state = "just-woken"
            notes.append("grooming_state=just-woken inferred from the brief")
        elif _WORKOUT_RE.search(b):
            grooming_state = "post-workout"
            notes.append("grooming_state=post-workout inferred from the brief")

    return holder, flaws, optics, grooming_state, notes


# A shot has no framing picker — the brief carries it in words. This reads them
# back so the preview can say which side of the 400px plateau a shot will land
# on. Deliberately crude: it exists to catch "full body" before it costs a
# generation, not to predict a pixel count. Longest phrases first so
# "head and shoulders" is not eaten by "head".
_FRAMING_WORDS = [
    ("head_shoulders", ("head and shoulders", "head & shoulders", "headshot",
                        "head shot")),
    ("close_up", ("close-up", "close up", "tight crop", "extreme close")),
    ("chest_up", ("chest up", "chest-up", "bust shot")),
    ("waist_up", ("waist up", "waist-up", "waist level", "from the waist")),
    ("knee_up", ("knee up", "knee-up", "three-quarter length")),
    ("full_body", ("full body", "full-body", "head to toe", "head-to-toe",
                   "full length", "full-length")),
    ("wide", ("wide shot", "wide angle", "environmental portrait")),
    ("from_behind", ("from behind", "back view")),
    ("over_shoulder", ("over the shoulder", "over-the-shoulder")),
]


def _framing_from_brief(brief: str) -> str:
    b = (brief or "").lower()
    for key, phrases in _FRAMING_WORDS:
        if any(p in b for p in phrases):
            return key
    return ""


class ShotReq(BaseModel):
    # Compose everything and return it INSTEAD of generating. Same request shape
    # as a real shot on purpose: the only honest preview of a prompt is the
    # prompt, produced by the code that would have sent it.
    preview: bool = False
    # Attach the pinned body reference EVEN when an outfit already owns @image2.
    # Off by default because it is a third image and that is measured to cost
    # ~0.04 of identity; on when the figure matters more than the last 0.04,
    # which for a body built deliberately is most of the time.
    body_ref: bool = False
    brief: str = ""              # the ONLY thing the user writes
    prompt: str | None = None    # AI-written (Claude) prompt, edited by the user;
                                 # used VERBATIM when present instead of the template
    aspect: str = "3:4"
    seed: int | None = None
    with_character: str | None = None   # a COLLABORATION: her face rides as @image2
                                        # and the run records both in meta.cast
    wardrobe_id: str | None = None   # attach this saved outfit as @image2
    pose_id: str | None = None       # a pose from the text library
    pose_text: str | None = None     # raw pose text, overrides the library lookup —
                                     # lets a past shot's pose be reused even after the
                                     # library is regenerated and its id is orphaned
    pose_ref_id: str | None = None   # a pose REFERENCE image, attached as @image3
    nail_id: str | None = None       # a manicure reference image, attached as @imageN
    shot_type: str = "candid"
    resolution: str | None = None    # "1K" | "2K" | "4K" (nano). None -> config default
    # Which kie model renders this shot. None keeps the configured default.
    # The tiers do NOT share a resolution vocabulary — see providers.KIE_MODELS —
    # so asking for 4K on seedream-5-pro silently yields 2K, and the run row
    # records what actually rendered rather than what was asked for.
    model: str | None = None
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
    # fal's own moderation dial, 1 strictest to 6 least strict, default 4.
    # 11b4f1a chose per-request over a raised global default — "a quiet
    # platform-wide loosening is not a decision that belongs in a config
    # constant where nobody sees it" — and then no per-request control was ever
    # built, so every shot in the first 613 runs went out on a default nobody
    # picked. The field was added to wardrobe and scene and missed here, despite
    # that commit saying it "does apply to shots".
    #
    # ⚠ It governs OUTPUT moderation. A prompt-level refusal (loc: ["body",
    # "prompt"]) is a provider policy boundary and raising this changes nothing —
    # see the wardrobe request for the measured case.
    safety_tolerance: str | None = None
    date: str | None = None          # ISO date this shot happens on. None = today
    use_timeline: bool = False       # OFF by default: appending season/manicure text to
                                     # every shot changes output nobody asked to change.
                                     # Set true (with a date) when you WANT the year to
                                     # show — monsoon light, a manicure at its end
    camera_holder: str = ""          # who took it: selfie/mirror/friend/stranger/timer.
                                     # Also a face-size lever — see CAMERA_HOLDERS
    flaws: str = ""                  # "" | subtle | snapshot. Deliberate imperfection;
                                     # "snapshot" is expected to score low, by design
    allow_crowd: bool = False        # let other people into a solo shot. Inferred
                                     # from the brief when it names them; see
                                     # _WANTS_PEOPLE for why the default suppresses
    optics: str = ""                 # "" | phone-deep | phone-front | portrait
    exposure: str = ""               # "" | blown-window | dark-face | phone-hdr | low-light
    grooming_state: str = ""         # "" | just-woken | end-of-day | unmaintained |
                                     # post-workout. Overrides the standing grooming
                                     # line, so it is appended after it — see
                                     # promptlib.late_clauses


class AiPromptReq(BaseModel):
    brief: str = ""
    wardrobe_id: str | None = None
    pose_id: str | None = None
    pose_text: str | None = None     # raw pose text override (reused orphaned pose)
    pose_ref_id: str | None = None
    shot_type: str = "candid"
    with_character: str | None = None   # writing for a COLLABORATION: Claude must
                                        # put BOTH subjects in the scene


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
            pose_text=pose_text, cast=2 if req.with_character else 1)
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
    # Pin the character for the whole request AND the job it starts. Everything
    # below — the guest lookup, the refs, the cast, the row — must agree on whose
    # shot this is, and the active character can move underneath a long job.
    owner_cid = config.get_active()

    # Whatever loses a reference slot is recorded here and returned to the
    # caller — never dropped silently.
    demoted: list[str] = []

    # Reference order defines the @image tags: @image1 = face (always).
    face = REFS / _bio_ref()
    if not face.exists():
        raise HTTPException(400, "no BIO reference set — import one on the face tab")
    refs = [face]

    # A COLLABORATION. @image2 is the guest's face, which spends the entire
    # measured reference budget (2 refs 0.622 against 3 refs 0.579), so an outfit
    # cannot also have a slot — it rides as text from the description already
    # stored on its wardrobe row, and says so in `ref_demoted` rather than going
    # quietly missing.
    cast: list[str] = []
    guest_name = ""
    if req.with_character:
        guest = req.with_character
        if guest == owner_cid:
            raise HTTPException(400, "a collaboration needs two different characters")
        grow = db.chars_get(guest)
        if not grow:
            raise HTTPException(404, guest)
        gref = _char_reference(guest)
        if not gref:
            raise HTTPException(400, f"{grow['name']} has no master face yet — "
                                     "choose one before shooting with her")
        refs.append(config.char_base(guest) / "refs" / gref)
        cast = [owner_cid, guest]
        guest_name = grow["name"]

    has_wardrobe = False
    has_body_ref = False
    if req.wardrobe_id:
        w = _find_by_id(WARDROBE, req.wardrobe_id)
        if not w:
            raise HTTPException(400, f"no such wardrobe: {req.wardrobe_id}")
        if cast:
            # @image2 is the guest. A third reference is measurably worse than
            # two (0.579 vs 0.622), and on a shot already asking the model to
            # hold two identities apart it is the wrong thing to spend on. The
            # outfit still reaches the prompt as text below.
            demoted.append("outfit (collaboration — @image2 is the second face)")
        else:
            refs.append(_outfit_ref(w))   # @image2 = outfit, head cropped off (no competing face)
            has_wardrobe = True

    # THE BODY REFERENCE. Attached when no outfit took @image2, or on demand.
    #
    # It used to be `elif not cast:` hanging off the wardrobe branch, which meant
    # a pinned figure applied only to shots where she was not wearing anything
    # chosen — that is, almost never. Reported as "identity was never an issue,
    # it is just the body shape I am missing": a rooftop set shot in a saree had
    # `curvy athlete full` pinned and every frame reached the model with her
    # build as TEXT alone, because @image2 was the garment.
    #
    # Text does not hold a body any better than it holds a garment. The saree
    # print proved the same thing from the other side: 1,940 words describing a
    # fabric lost to the photograph of it.
    #
    # So `body_ref=True` buys the third slot deliberately. It is measured and it
    # is real — 2 refs 0.622 against 3 refs 0.579 — but that is the owner's trade
    # to make, and for a figure that took a day to build it is often the right
    # one. Still never on a collaboration: there @image2 is the guest's face and
    # a fourth image on a shot already holding two identities apart is the wrong
    # place to spend.
    cfg = _bio_cfg()
    body = REFS / cfg["body_reference"]
    wants_body = (not has_wardrobe or req.body_ref) and not cast
    if wants_body and body.exists():
        refs.append(body)
        has_body_ref = True
        if has_wardrobe:
            demoted.append("body reference added as a 3rd image "
                           "(costs ~0.04 similarity, holds her figure)")

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
    # The photographic doctrine — camera, skin, constraints. See capture_clause's
    # docstring: these sections were unreachable from a shot until 2026-08-24, so
    # every one of the first 607 runs shipped without a single word of it.
    #
    # ⚠ Gated on the REGISTER, and this was wrong for a day. capture_clause says
    # "never a professional camera, never a photoshoot"; SHOT_TYPES["editorial"]
    # opens the same prompt with "Editorial photo". Shipping both is an argument,
    # not a directive. `_sys` below was gated from the start and `_infer_capture`
    # stands down on a studio brief — this one was not, so three mechanisms held
    # three different opinions about whether the phone doctrine applies to a
    # studio register. One predicate now, so they cannot drift apart again.
    phone_register = req.shot_type in PHONE_REGISTERS
    capture_text = promptlib.capture_clause(_parts) if phone_register else ""
    # Who held the camera and how imperfect the frame is — inferred from the brief
    # when the caller left them blank. Recorded in `demoted` so the run says so.
    holder_id, flaws_id, optics_id, groom_id, _inferred = _infer_capture(
        req.brief, req.pose_id, req.camera_holder, req.flaws,
        req.optics, req.grooming_state, req.shot_type)
    demoted.extend(_inferred)
    # POV is a specific faceless first-person framing that a generic AI prompt (which
    # references @image1 and describes her posing) would fight — so POV always uses
    # the template's POV branch and ignores any AI prompt.
    # A collaboration inverts the pipeline's most load-bearing assumption: that
    # exactly one person is in frame and she is @image1. Say the second woman is
    # a second woman, explicitly, or the model averages the two references into
    # one face — the failure `check_cast` measures as `blended`.
    collab_clause = ""
    if cast:
        collab_clause = (
            f"TWO DIFFERENT WOMEN are in this photograph: @image1 and @image2. "
            f"@image1 is one person and @image2 is another — render them as two "
            f"distinct individuals who do not resemble each other. Keep each "
            f"face exactly as its own reference shows it. Do NOT blend, merge or "
            f"average their features, and do not give them the same face.")

    if req.prompt and req.prompt.strip() and not req.pov:
        # AI-written (and user-edited) prompt: use it verbatim, only running the
        # moderation sanitiser so a trigger can't slip through. The reference
        # tags (@image1/2/3) are the user's/Claude's responsibility here.
        base = req.prompt.strip()
        if build_text:
            base = f"{base} {build_text}"
        if carry_text:
            base = f"{base} {carry_text}"
        # Same treatment, and the most important instance of it. Claude writes
        # the SCENE; the camera is ours. Left to itself it asked for "85mm" in 51
        # prompts and "shallow depth of field" in 40 — the exact look camera.body
        # forbids — because camera.body was not in the prompt to argue with it.
        # Appended AFTER Claude's text so that when the two disagree, we win.
        if capture_text:
            base = f"{base} {capture_text}"
        # Same treatment as the build clause: appended rather than handed to
        # Claude. Who held the camera and how imperfect the frame is are
        # photographic facts, and an AI prompt written before they were chosen
        # would otherwise contradict them.
        holder = (promptlib.CAMERA_HOLDERS.get(holder_id) or {}).get("text", "")
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
        flaw = (promptlib.SNAPSHOT_FLAWS.get(flaws_id) or {}).get("text", "")
        if flaw:
            base = f"{base} {flaw}"
        if collab_clause:
            base = f"{collab_clause} {base}"
        text, sanitised = promptlib.sanitise(base)
    else:
        pose_text = req.pose_text or promptlib.POSES_LIBRARY.get(req.pose_id or "", "")
        text, sanitised = promptlib.compose_tagged(
            req.brief, pose_text=pose_text, has_wardrobe=has_wardrobe,
            pose_ref_tag=pose_ref_tag, build_text=build_text, shot_type=req.shot_type,
            camera_holder=holder_id, flaws=flaws_id,
            carry_text=carry_text, capture_text=capture_text, pov=req.pov,
            phone=phone_register)
        if collab_clause:
            text = f"{collab_clause} {text}"

    # The BODY reference needs a role line, and this was measured the hard way.
    #
    # When no outfit is chosen, body-canonical rides as @image2 — and it is a
    # full-length photograph that CONTAINS HER FACE. compose_tagged only names
    # @image1, so nothing told the model what the second image was for. Two
    # unexplained faces went to nano-banana and it returned a stranger:
    #
    #   same prompt, face ref + unlabelled body ref : 0.1473  REJECTED
    #   same prompt, face reference alone           : 0.7838  kept
    #
    # A 0.64 swing — the body reference was not shaping her build, it was
    # replacing her identity. _copy_body_from's docstring already warned that an
    # unlabelled body image "has no role line for it, so nothing tells the model
    # whose face to ignore"; that hazard was live on every outfit-less shot.
    #
    # Same exclusion shape body_ref_create uses on its own @image2.
    if has_body_ref:
        # The TAG, not a guess. This line hardcoded @image2, which is right only
        # when the body reference is the second image — and with an outfit also
        # attached it is the third. The prompt then said "take ONLY the clothing
        # from @image2" and "take the body shape from @image2" in the same
        # breath, which is not a directive, it is an argument.
        body_tag = f"@image{refs.index(body) + 1}"
        text += (f" Her build and proportions match {body_tag} — take ONLY the "
                 f"body shape, proportions and silhouette from {body_tag}. Her "
                 f"face, identity, bone structure, skin and hair come only from "
                 f"@image1, never from {body_tag}.")

    # Carry the outfit's FULL styling into the shot. The turnaround (@image2) has
    # her head cropped and may not show every accessory, so the saved outfit
    # description supplies the lip colour, nail colours, jewellery, bag and
    # accessories the image alone would drop. These are STYLING, not identity —
    # her face still comes only from @image1.
    #
    # Keyed on the outfit being CHOSEN, not on it winning a reference slot. On a
    # collaboration the guest owns @image2 and the outfit is demoted to text —
    # which is only a demotion if the text actually goes; otherwise "demoted"
    # would quietly mean "dropped".
    if req.wardrobe_id:
        desc = (_wardrobe_meta().get(req.wardrobe_id, {}) or {}).get("description")
        # When the outfit HAS its own image, the description competes with it —
        # and loses the thing only a picture can carry. Measured on a real street
        # shot: a 1,940-character saree description rode alongside its turnaround,
        # and the model painted the print from the WORDS. Reference: bold coral,
        # sky-blue and mustard blooms. Result: small washed-out pink roses, blue
        # and yellow gone. Drape, blouse and shoes survived; the pattern did not.
        #
        # The same prompt ran 4,517 characters with 3,631 of them wardrobe and
        # grooming boilerplate — 80% — against ~880 characters of the scene the
        # user actually asked for. The street, the park and the blurred families
        # never stood a chance, and the face landed at 360px under the plateau.
        #
        # So when the image is attached the text is TRIMMED to what a cropped
        # turnaround genuinely cannot show — lip and nail colour, jewellery, bag,
        # eyewear — and stops re-describing fabric the picture is already holding.
        # With no image (a collaboration demotes it) the full text stays, because
        # then words are all there is.
        # A selfie crop overrides the normal cap — see _SELFIE_TEXT_CAP. This
        # applies whether or not an outfit image is attached, because the limit
        # here is the FRAME, not what the reference already carries.
        selfie = _is_selfie_pose(req.pose_id, req.brief, holder_id)
        cap = _SELFIE_TEXT_CAP if selfie else _OUTFIT_TEXT_CAP
        if desc and (has_wardrobe or selfie) and len(desc) > cap:
            cut = desc[:cap]
            # Prefer a sentence end, then any clause end, and only then a word
            # boundary. The bare `or cut` fallback shipped mid-word — run
            # a99848d7ce ends "...the wrap-style skirt fa" — which happens on any
            # garment description written as one long sentence, i.e. most of them.
            end = max(cut.rfind("."), cut.rfind(";"))
            if end < cap // 2:
                end = cut.rfind(" ")
            desc = (cut[:end + 1].rstrip(" ;") if end > 0 else cut).rstrip()
            if not desc.endswith("."):
                desc += "."
            demoted.append(
                f"outfit description trimmed to {len(desc)} chars "
                + ("(a selfie crop cannot show most of it)" if selfie
                   else "(@image2 carries the garment)"))
        # Only point at @image2 when @image2 IS the outfit. On a collaboration
        # that tag holds the guest's FACE, and telling the model to take garments
        # from it is worse than saying nothing — the description alone carries
        # the look in that case.
        from_ref = "from @image2 " if has_wardrobe else ""
        styling = ""          # bound unconditionally: the prompt budget below
                              # needs to know whether there is one to drop
        if desc and desc.strip():
            if req.face_accessories:
                styling, _extra = promptlib.sanitise(
                    "She is WEARING this complete look in the shot — show every "
                    "element on her, not only the clothing: reproduce the garments "
                    f"{from_ref}and also render her hairstyle and hair colour, "
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
                styling, _extra = promptlib.sanitise(
                    f"She is wearing this look — reproduce the garments {from_ref}"
                    "and apply its hairstyle and hair colour, lip colour, nail "
                    "colours, jewellery, bag, belt and watch. But do NOT add any "
                    "sunglasses, glasses, eyewear, "
                    "hat or anything covering or obscuring her face — keep her face "
                    "fully clear, uncovered and visible, even if the description "
                    "mentions such items. Her facial identity comes only from "
                    f"@image1: {desc.strip()}")
            sanitised += _extra
            text = f"{text} {styling}"

    # Manicure reference: match her nails to the chosen nail image. Nails only —
    # face/identity stay with @image1, outfit unchanged.
    if nail_tag:
        nail_line, _extra = promptlib.sanitise(
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
        sanitised += _extra
        text = f"{text} {nail_line}"

    # Home reference: the brief named one of her rooms — put her in HER home, the
    # exact space shown in the corner image, so the house stays consistent.
    if place_tag:
        where = ("a place she goes regularly" if place_kind == "regular"
                 else "her own home")
        thing = "space" if place_kind == "regular" else "room"
        place_line, _extra = promptlib.sanitise(
            f"SETTING — {where}: the location and background of this photo is "
            f"exactly the {thing} shown in {place_tag} — reproduce that same place (the "
            f"furniture, walls, layout, décor and overall setting) faithfully and keep "
            f"it consistent. Do not invent or substitute a different {thing}. She is "
            f"naturally within this space doing what the brief describes; her identity "
            f"still comes only from @image1.")
        sanitised += _extra
        text = f"{text} {place_line}"

    # The date, last: season, hair era and manicure wear. Appended rather than
    # handed to the prompter for the same reason the build clause is — Claude is
    # barred from describing her, and hair and nails sit right on that line.
    # POV shots are faceless and hairless in frame, so only the season applies.
    if tl_clause:
        when_line, _extra = promptlib.sanitise(
            timeline.clause(when, {}, [])[0] if req.pov else tl_clause)
        if when_line:
            sanitised += _extra
            text = f"{text} {when_line}"

    # LAST, deliberately, and after both prompt branches have converged.
    #
    # It was first added to the AI-prompt branch alone, which meant a template
    # shot — the common case — never got it and came back dry-headed anyway.
    # Placing it here also puts it after the two clauses that cause the problem:
    # the body-reference line above and the outfit styling below both say hair
    # comes only from @image1, and the later line is the one that wins.
    # THE SHARED TAIL. Every clause here contradicts something earlier on
    # purpose, which is why it is a tail — see promptlib.late_clauses for the
    # order and what each one has to arrive after.
    #
    # It lives in promptlib rather than here because /api/scene needs the same
    # set and had none of it: a pool scene came back dry-headed because the fix
    # for exactly that was written on this path only. One implementation now.
    #
    # ⚠ Everything appended AFTER the two prompt branches converge skips the
    # sanitise() that ran inside them. _WET_HAIR sat in that hole safely by luck
    # of wording; "her face is bare" did not, and fal refused a whole generation
    # over it. The pass runs here so the next clause added is covered by default.
    suppress_crowd = not cast and not _wants_people(req.brief, req.allow_crowd)
    if suppress_crowd:
        demoted.append("no other people in frame (say so in the brief to allow them)")

    tail = ""
    for _txt in promptlib.late_clauses(
            optics=optics_id, exposure=req.exposure, grooming_state=groom_id,
            wet=_is_wet_pose(req.pose_id, req.brief),
            suppress_crowd=suppress_crowd,
            subjects=len(cast) + 1 if cast else 1):
        _clean, _extra = promptlib.sanitise(_txt)
        sanitised += _extra
        tail = f"{tail} {_clean}" if tail else _clean

    # THE PROMPT BUDGET.
    #
    # kie refuses an over-long prompt at createTask and the chain then walks to
    # poyo and fal, so the caller is shown the LAST provider's complaint — on
    # 2026-08-25 a fal content_policy_violation for a prompt whose real problem
    # was that it ran 5,367 characters. Nothing anywhere counted them.
    #
    # Dropped in order of what the FRAME can least afford to lose, which is the
    # inverse of what a prompt naturally accumulates. The body block goes first:
    # 450 characters of bust, waist and hip measurements are worth their length
    # in a full-length shot and worth nothing in a chest-up selfie, and it is the
    # single largest block that is invisible at the crop the rest of the prompt
    # asks for. Everything dropped is reported — a prompt silently shortened is
    # the same class of failure as a reference silently dropped.
    # ⚠ The TAIL IS NEVER TRIMMED. Every clause in it only works by arriving
    # last — optics overrules an invented focal length, grooming_state overrules
    # "nails clean and even" — so cutting from the end removes exactly the lines
    # the prompt was built to let win. The first version of this budget did trim
    # the end, and cut the crowd clause in half.
    _room = PROMPT_CAP - len(tail) - 1
    if len(text) > _room:
        for _block, _why in ((build_text, "body measurements"),
                             (carry_text, "standing grooming"),
                             (locals().get("styling", ""), "outfit styling")):
            if len(text) <= _room:
                break
            if _block and _block in text:
                text = text.replace(f" {_block}", "").replace(_block, "")
                demoted.append(f"dropped {_why} — prompt over {PROMPT_CAP} chars")
        if len(text) > _room:
            _cut = text[:_room]
            _end = _cut.rfind(". ")
            text = (_cut[:_end + 1] if _end > _room // 2 else _cut).rstrip()
            demoted.append(f"prompt head truncated — still over {PROMPT_CAP} "
                           f"after dropping what it could")

    if tail:
        text = f"{text} {tail}"

    label = req.brief.strip()[:60] or "untitled shot"
    session = generate.new_session(label)

    # Store the pose's actual TEXT alongside its id. The pose library can be
    # regenerated (ids change), which orphans a past shot's pose_id — so the
    # text is what lets "use this pose" survive a library rebuild.
    pose_text_used = req.pose_text or promptlib.POSES_LIBRARY.get(req.pose_id or "", "")

    # POV framing is phone-portrait; use 4:5 unless the caller set a non-default aspect.
    # No face to gate, so the 4K-for-face-pixels rationale (config) doesn't apply — 2K is fine.
    aspect = ("4:5" if req.pov and req.aspect in (None, "", "3:4") else req.aspect)

    # PREVIEW returns from inside the real path, deliberately.
    #
    # There was already a /api/shot/preview, and it lied by omission: it called
    # compose_tagged alone and never saw the outfit styling, the nail line, the
    # place line, the timeline clause or the body-reference directive. So it
    # reported ~880 characters for a prompt that shipped at 4,517 — it would
    # have told the owner the street brief was fine, right before it wasn't.
    #
    # A preview assembled by a second code path drifts from the first. This one
    # cannot, because it IS the first: same references, same demotions, same
    # sanitiser report, same string. The cost of that is one early return.
    #
    # `share` is the number the failure actually turned on. A brief that is 20%
    # of its own prompt does not get rendered; the wardrobe boilerplate does.
    if getattr(req, "preview", False):
        brief_chars = len(req.brief.strip())
        return {
            "prompt": text,
            "chars": len(text),
            "brief_chars": brief_chars,
            "brief_share": round(brief_chars / max(len(text), 1), 3),
            "references": [{"tag": f"@image{i + 1}", "file": p.name}
                           for i, p in enumerate(refs)],
            "demoted": demoted,
            "sanitised": sanitised,
            "aspect": aspect,
            "resolution": req.resolution or RESOLUTION,
            # A shot has no framing PICKER (that is a scene axis), so the size is
            # estimated from the brief's own words. Rough on purpose — the point
            # is to show which side of the 400px plateau this lands on before
            # paying, not to predict a number.
            "face_px": framing_data.estimate_face_px(
                _framing_from_brief(req.brief), max(len(cast), 1), aspect,
                req.resolution or RESOLUTION),
            "plateau_px": gate.FACE_PLATEAU_PX,
            "cast": cast,
        }

    # promptlib.SYSTEM says "never a fashion shoot, never a studio session", which
    # is right for a phone register and flatly wrong for the three registers that
    # ARE a studio session. Send it only where it agrees with the opener.
    #
    # ⚠ It reaches fal only. kie_generate and poyo_generate take no system field,
    # and the chain is kie → poyo → fal, so on the usual path this ships nothing.
    # That is precisely why capture_clause puts the doctrine IN the prompt — the
    # same argument generate.py:398 already makes for gpt-image. Treat this as a
    # bonus on the fallback provider, not as the mechanism.
    _sys = promptlib.SYSTEM if phone_register else ""

    def run(job: dict) -> dict:
        return generate.generate(
            prompt=text, system=_sys, refs=refs, aspect=aspect,
            seed=req.seed, session=session, progress=job, character=owner_cid,
            # If gpt-image-2 refuses a revealing outfit on content_policy, render
            # it on the scene model instead (weaker identity, recorded) rather
            # than dead-spinning to a failure.
            fallback_endpoint=SCENE_EDIT,
            resolution=req.resolution, model=req.model,
            safety_tolerance=req.safety_tolerance,
            meta={"brief": req.brief, "bio_references": [p.name for p in refs],
                  # Present ONLY on a collaboration. generate() branches the gate
                  # on it, and the guest's review finds her shots by it.
                  **({"cast": cast, "guest": guest_name} if cast else {}),
                  "wardrobe": req.wardrobe_id, "pose_id": req.pose_id,
                  "pose_text": pose_text_used,
                  "pose_ref": req.pose_ref_id, "nail_id": nail_id,
                  "home_corner": home_corner.stem if home_corner else None,
                  "sanitised": sanitised, "pov": req.pov,
                  "ref_demoted": demoted, "when": tl_facts,
                  "camera_holder": holder_id, "flaws": flaws_id,
                  "optics": optics_id, "exposure": req.exposure,
                  "grooming_state": groom_id,
                  # Recorded because it changes what the gate's number MEANS: a
                  # frame with other people in it is scored as a max over faces.
                  "allow_crowd": _wants_people(req.brief, req.allow_crowd),
                  # A deliberately imperfect frame is EXPECTED to score low —
                  # motion blur and a half-caught expression degrade the very
                  # geometry ArcFace reads. Recording it here is what keeps that
                  # low number from being counted as drift later.
                  #
                  # Grooming state does the same thing by a different route:
                  # puffy eyes and a slept-on face move the landmarks ArcFace
                  # measures. Either one alone is enough to expect a low score.
                  "expected_low": bool(
                      (promptlib.SNAPSHOT_FLAWS.get(flaws_id) or {}).get("expected_low")
                      or (promptlib.GROOMING_STATE.get(groom_id) or {}).get("expected_low")),
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


# ============================================================== scene composer
# A scene is written as prose with @mentions and the CAST falls out of the text:
# "@kiara and @sonam on a rooftop" is a two-hander. That is the right shape for a
# photograph of several people — a collaboration is not something one character
# does to another, it is a cast — and it is why this lives on the landing page
# rather than inside anybody's studio.

# Ids contain hyphens (sakshi-singh), so the pattern must allow them. Trailing
# punctuation is not part of a name: "@kiara," ends at the comma. The lookbehind
# is what stops "email me at hi@kiara.com" casting Kiara in a scene — a mention
# starts a word, it does not sit inside one.
_MENTION = re.compile(r"(?<![\w.])@([A-Za-z0-9][A-Za-z0-9_-]*)")

# {id: entry} across every category, so a lookup by id needs no group.
_INTERACTIONS_FLAT = {i: d for g in INTERACTIONS.values() for i, d in g.items()}


def _parse_cast(prompt: str) -> list[str]:
    """The characters named in a scene, in order of first mention.

    ONE implementation, used both by the endpoint that tells the UI which
    wardrobe pickers to show and by the endpoint that actually builds the prompt.
    A second copy in the client would be a copy that can disagree with the one
    that matters, and the disagreement would show up as an outfit attached to the
    wrong woman.

    Unknown mentions are IGNORED rather than rejected: an email address or a
    stray '@' in a brief is not a failed scene, and refusing one would make the
    composer unusable on ordinary prose.
    """
    known = {c["id"].lower(): c["id"] for c in db.chars_all()}
    out: list[str] = []
    for raw in _MENTION.findall(prompt or ""):
        cid = known.get(raw.lower())
        if cid and cid not in out:
            out.append(cid)
    return out


class SceneCastReq(BaseModel):
    prompt: str = ""


@app.post("/api/scene/cast")
def scene_cast(req: SceneCastReq):
    """Who is in this scene — resolved server-side so the composer and the
    generator can never disagree about the cast."""
    cast = _parse_cast(req.prompt)
    rows = {c["id"]: c for c in db.chars_all()}
    return {"cast": [{"id": cid, "name": rows[cid]["name"],
                      "has_reference": _char_reference(cid) is not None}
                     for cid in cast]}


class SceneReq(BaseModel):
    prompt: str = ""                       # prose with @mentions
    wardrobe: dict[str, str] = {}          # {character_id: outfit_id}
    place: str = ""                        # a corner/regular key, from the OWNER
    activity: str = ""                     # what is happening
    interaction: str = ""                  # how the cast is arranged (cast > 1)
    pose: str = ""                         # how one body is arranged (cast == 1)
    holder: str = ""                        # who held the camera
    flaws: str = ""                        # how imperfect the frame is
    shot_type: str = "candid"

    # ---- per-character GETUP. {character_id: value} throughout, because a cast
    # is a set of people and every one of them gets dressed separately. Outfits
    # and nails name a saved ASSET; the rest are text, either a key from
    # getup_data or free prose typed into the same box.
    nails: dict[str, str] = {}             # {cid: nail_id} — an image reference
    hair: dict[str, str] = {}              # {cid: HAIR_STYLING key or free text}
    makeup: dict[str, str] = {}            # {cid: MAKEUP key or free text}
    accessories: dict[str, list[str]] = {}  # {cid: [ACCESSORIES keys or text]}
    footwear: dict[str, str] = {}          # {cid: FOOTWEAR key or free text}
    poses: dict[str, str] = {}             # {cid: poses_data id} — how ONE body
                                           # is arranged, alongside the group
                                           # interaction rather than instead of it

    # ---- scene-wide axes
    framing: str = ""                      # FRAMING key. Placed EARLY, see below
    lighting: str = ""                     # LIGHTING key
    time_of_day: str = ""                  # TIME_OF_DAY key
    weather: str = ""                      # WEATHER key
    season: str = ""                       # SEASON key
    face_accessories: bool = True          # render face-worn items (sunglasses,
                                           # caps). Off keeps her eyes visible,
                                           # which is where the gate reads hardest
    # Background people. Default OFF: a cast scene is about the cast, and the
    # gate scores whichever face best matches the gallery — so every extra face
    # is another chance to score a stranger instead of her. Turn on for the venue
    # and street briefs that genuinely want life behind the subject, and expect
    # faces_in_frame to rise with it.
    allow_crowd: bool = False
    # The tail axes, same vocabulary as a shot. See promptlib.late_clauses.
    optics: str = ""
    exposure: str = ""
    grooming_state: str = ""
    prompt_override: str | None = None     # a written prompt used VERBATIM in
                                           # place of everything assembled here —
                                           # same contract as ShotReq.prompt
    # fal's own moderation dial, 1 (strictest) to 6, default 4. Explicit per
    # request: the default is right for nearly everything, and a commercial
    # product brief is the case where the provider's control is worth reaching
    # for rather than assuming the category is impossible.
    safety_tolerance: str | None = None
    # Which optional references spend an image SLOT rather than riding as text.
    # Every one of them has a text form, so this is a real choice and not a
    # degradation: outfits carry their saved description, corners carry their
    # `gen` line. Default: outfits yes, place no — because a place is the one
    # whose text form loses least.
    as_image: dict[str, bool] = {}         # {"outfit:kiara": True, "place": False}
    aspect: str = "3:4"
    resolution: str | None = None
    seed: int | None = None
    # Which kie model renders this scene. None uses the project default
    # (providers.load_model). Per-request so a scene and the wardrobe worn in it
    # can be made on different renderers without changing the default.
    model: str | None = None


_FRAMING_ORDER = {k: v["order"] for k, v in framing_data.FRAMING.items()}
_LIGHTING_FLAT = {k: v for g in lighting_data.LIGHTING.values() for k, v in g.items()}

# Flattened once. Every getup vocabulary is {group: {id: text}}, and the composer
# sends an id — or, when someone typed their own, the prose itself.
_HAIR_FLAT = {k: v for g in getup_data.HAIR_STYLING.values() for k, v in g.items()}
_MAKEUP_FLAT = {k: v for g in getup_data.MAKEUP.values() for k, v in g.items()}
_FOOTWEAR_FLAT = {k: v for g in getup_data.FOOTWEAR.values() for k, v in g.items()}
_ACCESSORY_FLAT = {k: v for g in getup_data.ACCESSORIES.values() for k, v in g.items()}
_GETUP_FLAT = {id(getup_data.HAIR_STYLING): _HAIR_FLAT,
               id(getup_data.MAKEUP): _MAKEUP_FLAT,
               id(getup_data.FOOTWEAR): _FOOTWEAR_FLAT}


def _getup_text(library: dict, value: str | None) -> str:
    """A library id, or the free text somebody typed instead.

    Free text is a first-class input, not a fallback: the vocabularies are a
    starting point and no list of thirty hairstyles covers what a person can do
    to their hair. An unrecognised value is therefore used verbatim rather than
    dropped, which is also what keeps a stale UI from silently losing a field.
    """
    v = (value or "").strip()
    if not v:
        return ""
    return _GETUP_FLAT[id(library)].get(v) or v


def _accessory_texts(values: list[str], *, allow_face: bool) -> list[str]:
    """Accessory texts, with the face-worn ones dropped when asked.

    `allow_face=False` is a real identity lever and not a style preference.
    ArcFace reads hardest on the eye region — the mirror-selfie clause in
    prompt.py exists because forcing her eyes onto the reflection moved the same
    shot from 0.334 to 0.628 — and dark lenses remove both eyes outright. A shot
    that has to be gated should not be wearing sunglasses.
    """
    out = []
    for v in values:
        v = (v or "").strip()
        if not v:
            continue
        entry = _ACCESSORY_FLAT.get(v)
        if entry is None:
            out.append(v)          # free text, same rule as _getup_text
        elif allow_face or not entry["face"]:
            out.append(entry["text"])
    return out


def _spend_optional(req: "SceneReq", cid: str, key: str, cast_size: int,
                    spent: int = 0) -> bool:
    """Should this optional reference spend an IMAGE slot, or ride as text?

    Faces are never asked — they are mandatory, so a cast of three starts at
    three references before anyone puts on a shoe. Measured: 2 refs 0.622, 3 refs
    0.579. So the DEFAULT flips with the cast: at one or two people an outfit or
    a manicure is worth its slot, and at three or more it is not, because the
    budget is already spent on being able to tell who is who.

    `cast_size <= 2` alone was not enough. It asks how many PEOPLE there are, not
    how many references have already been spent, so a two-hander with outfits and
    manicures on both reached FIVE — the nightclub scene did exactly that against
    a measured optimum of two.

    But charging OUTFITS against a running count was worse than the problem. The
    cast is walked in order, so the first character's outfit was evaluated with
    one slot spent and passed, and the second's with three spent and failed:
    whoever happened to be mentioned first kept her garment and the other silently
    lost hers. A collaboration where only one woman wears what she was dressed in
    is not a budget saving, it is a wrong picture — and the demotion does not even
    buy the garment back in words, because text does not hold a garment. Soni's
    plum cocktail dress was described correctly in the prose and she still came
    back in something else entirely.

    So outfits are a CLASS, not a queue. At a cast of one or two everybody's
    outfit gets a slot or nobody's does, which is symmetric and matches what the
    pipeline is for. At three or more they all fall back to text together —
    telling three women apart is what the budget is really for.

    Manicures lose their slot as soon as there is more than one person, which is
    what keeps a two-hander at four references (two faces, two outfits) rather
        than five. That is the cheapest thing to give up: the saved nail
    description already carries shape, colour and finish as words, and unlike a
    garment those words survive. A solo shot still gets the image.

    Explicit always wins. This only decides what happens when nobody said, and
    anything refused here still reaches the prompt as text and is recorded in the
    ledger as mode="text", so nothing goes quietly missing.
    """
    if key in req.as_image:
        return bool(req.as_image[key])
    if cast_size > 2:
        return False
    if key.startswith("outfit:"):
        return True
    return cast_size == 1


def _build_scene(req: "SceneReq") -> dict:
    """Everything a scene needs, plus a LEDGER of what it spent to get there.

    References are attached per character in cast order — her face, then her
    outfit if it was given a slot — and the prompt SAYS what each tag holds:

        @image1  Kiara's face     @image3  Sonam's face
        @image2  Kiara's outfit   @image4  Sonam's outfit

    Stated, not implied. A positional convention the model has to infer is one
    off-by-one away from dressing somebody in a face, and at four references that
    mistake is invisible in the output.

    Every optional reference can ride as an IMAGE or as TEXT, and the ledger says
    which. That is the honest way to present a real cost: two references measured
    0.622 and three measured 0.579, so a two-hander with both outfits and a place
    is five — and every one of those extras already has a text form good enough to
    fall back to. The caller decides; this records the decision.
    """
    cast = _parse_cast(req.prompt)
    if not cast:
        raise HTTPException(400, "name at least one character with @, e.g. @kiara")

    owner = cast[0]
    rows = {c["id"]: c for c in db.chars_all()}
    refs: list[Path] = []
    roles: list[str] = []
    ledger: list[dict] = []
    face_tag: dict[str, str] = {}

    def spend(kind: str, key: str, path: Path, label: str) -> str:
        refs.append(path)
        tag = f"@image{len(refs)}"
        ledger.append({"kind": kind, "key": key, "label": label,
                       "mode": "image", "tag": tag, "file": path.name})
        return tag

    for cid in cast:
        ref = _char_reference(cid)
        if not ref:
            raise HTTPException(400, f"{rows[cid]['name']} has no master face yet")
        name = rows[cid]["name"]
        face_tag[cid] = spend("face", cid, config.char_base(cid) / "refs" / ref,
                              f"{name}'s face")
        roles.append(f"{face_tag[cid]} is {name}'s face.")

        # NOT `if not oid: continue`. It used to be, and when getup was added
        # below it every hairstyle, makeup, accessory and shoe silently did
        # nothing unless an outfit happened to be picked too — five dead axes
        # from one early exit. Caught by the per-axis hash diff, which exists
        # because shot_type was dead for months without anyone noticing.
        oid = (req.wardrobe or {}).get(cid)
        if oid:
            w = _find_by_id(config.char_base(cid) / "wardrobe", oid)
            if not w:
                raise HTTPException(400, f"no such outfit for {name}: {oid}")
            desc = (_wardrobe_meta(cid).get(oid, {}) or {}).get("description") or ""
            # Outfits default to an image slot at a cast of one or two, and to
            # text at three or more — see _spend_optional. Garments are the thing
            # a description reproduces least reliably, which is what earns the
            # slot; telling three women apart is what outranks it.
            if _spend_optional(req, cid, f"outfit:{cid}", len(cast), len(refs)):
                tag = spend("outfit", cid, _outfit_ref(w), f"{name}: {oid}")
                roles.append(f"{tag} is the outfit {name} is wearing — reproduce "
                             f"those garments on her, and take NOTHING about her "
                             f"face from it.")
            else:
                ledger.append({"kind": "outfit", "key": cid, "label": f"{name}: {oid}",
                               "mode": "text", "tag": None, "file": w.name})
            if desc.strip():
                roles.append(f"{name}'s look in full: {desc.strip()}")

        # ---- the rest of her GETUP, attributed to her tag so a cast of three
        # does not end up with one shared hairstyle. Text, not references: hair,
        # makeup, accessories and shoes are all things a sentence reproduces well
        # enough, and every image slot spent here is measured off the identity
        # (2 refs 0.622, 3 refs 0.579). Nails are the exception below — a nail
        # design is exactly what words reproduce worst.
        getup: list[str] = []
        styling = _getup_text(getup_data.HAIR_STYLING, (req.hair or {}).get(cid))
        if styling:
            # "her hair IS worn..." never "her hair is long and dark". Styling
            # only; colour, length and texture are identity and belong to her
            # reference. See a9cc83cd.
            getup.append(f"her hair {styling}")
        face_up = _getup_text(getup_data.MAKEUP, (req.makeup or {}).get(cid))
        if face_up:
            getup.append(face_up)
        worn = _accessory_texts((req.accessories or {}).get(cid) or [],
                                allow_face=req.face_accessories)
        if worn:
            getup.append("wearing " + ", ".join(worn))
        shoes = _getup_text(getup_data.FOOTWEAR, (req.footwear or {}).get(cid))
        if shoes:
            # Only below a knee-up frame is there anything to see. Above it this
            # spends prompt attention outside the picture.
            if _FRAMING_ORDER.get(req.framing, 9) >= _FRAMING_ORDER["knee_up"]:
                getup.append(f"in {shoes}")
            else:
                ledger.append({"kind": "footwear", "key": cid,
                               "label": f"{name}: shoes", "mode": "dropped",
                               "tag": None, "file": None})
        if getup:
            roles.append(f"{face_tag[cid]} — {name} — has {'; '.join(getup)}.")

        # @imageN = her manicure. An image because a nail design is the one piece
        # of getup a description reliably loses.
        nid = (req.nails or {}).get(cid)
        if nid:
            npath = _find_by_id(_nails_dir(cid), nid)
            if not npath:
                raise HTTPException(400, f"no such manicure for {name}: {nid}")
            nmeta = (_nails_meta(cid).get(nid, {}) or {})
            if _spend_optional(req, cid, f"nails:{cid}", len(cast), len(refs)):
                tag = spend("nails", cid, npath, f"{name}: {nmeta.get('name') or nid}")
                roles.append(f"{tag} is {name}'s manicure — reproduce that nail "
                             f"shape, length, colour and finish exactly on HER "
                             f"hands, and take nothing else from it.")
            else:
                ledger.append({"kind": "nails", "key": cid, "mode": "text",
                               "label": f"{name}: {nmeta.get('name') or nid}",
                               "tag": None, "file": npath.name})
                if (nmeta.get("description") or "").strip():
                    roles.append(f"{name}'s nails: {nmeta['description'].strip()}")

    # WHERE. The owner's corner, because a home belongs to somebody — labelled so
    # "whose kitchen" is never a guess.
    if req.place:
        corner = _CORNER.get(req.place)
        if not corner:
            raise HTTPException(400, f"unknown place: {req.place}")
        img = _corner_file(req.place, owner)
        label = f"{rows[owner]['name']}'s {corner['label'].lower()}"
        if img and req.as_image.get("place", False):
            tag = spend("place", req.place, img, label)
            roles.append(f"{tag} is the location — the setting is exactly the "
                         f"place shown there. Do not invent a different one.")
        else:
            ledger.append({"kind": "place", "key": req.place, "label": label,
                           "mode": "text", "tag": None,
                           "file": img.name if img else None})
            roles.append(f"The setting: {corner['gen']}.")

    # The user's prose, with every name turned into the tag it means.
    scene = req.prompt
    for cid, tag in face_tag.items():
        scene = re.sub(rf"(?<![\w.])@{re.escape(cid)}\b", tag, scene, flags=re.I)

    # The photographic REGISTER, first — same placement and same reason as the
    # shot path, where it is the opener everything after is written against.
    # SceneReq has carried shot_type since scenes existed and the composer has
    # always sent it; nothing read it, so every scene was built in whatever
    # register the brief happened to imply. `editorial` and `candid` produced
    # byte-identical prompts.
    opener = promptlib.SHOT_TYPES.get(req.shot_type, promptlib.SHOT_TYPES["candid"])
    parts = [f"{opener}."]

    # FRAMING, second — before the roles, before the brief, before anything that
    # could argue with it.
    #
    # On 2026-08-04 a three-person scene was briefed "Tight head-and-shoulders
    # crop ... nothing below the chest is in shot" as the last sentence of the
    # prose and came back waist-up with a ceiling in it. Framing written as one
    # more clause among twenty loses to the model's own idea of how to fit a cast
    # into the frame. The shot path already places the camera holder early for
    # the stated reason that it "decides the distance and the framing everything
    # after it is written against"; this is the same argument applied to the
    # thing that IS the framing.
    #
    # Whether early placement is enough is an open question with a cheap answer:
    # generate the same cast at head_shoulders and at full_body and read back
    # face_px. If the number does not move, this is decoration and the honest
    # response is a real crop step, not a louder sentence.
    frame = (framing_data.FRAMING.get(req.framing) or {}).get("text", "")
    if frame:
        parts.append(frame)

    parts += [" ".join(roles), scene.strip()]

    if req.activity.strip():
        parts.append(f"What is happening: {req.activity.strip()}.")

    # HOW THEY ARE ARRANGED. An interaction describes people relative to each
    # other and only makes sense with a cast; a pose describes one body. A and B
    # in the library text name the cast in mention order.
    if len(cast) > 1 and req.interaction:
        txt = _INTERACTIONS_FLAT.get(req.interaction, {}).get("text", "")
        if txt:
            # WORD-BOUNDARY, not substring. A bare .replace("A", tag) also ate the
            # A of "All", the B of "Both" and the C of "Caught" — 11 of the 35
            # entries, including BOTH three-person ones, which came out as
            # "@image1ll three standing in a row". The prompt still read as
            # English to a human skimming it, which is why it survived.
            for i, cid in enumerate(cast[:3]):
                txt = re.sub(rf"\b{'ABC'[i]}\b", face_tag[cid], txt)
            parts.append(txt)
    elif req.pose.strip():
        parts.append(req.pose.strip())

    # PER-CHARACTER POSE, alongside the interaction rather than instead of it.
    # An interaction says how the group is arranged relative to each other; it
    # cannot say that one of them is sitting while the others stand. All 551
    # entries in poses_data describe exactly one body, which is what makes them
    # usable here — attributed by tag so they land on the right woman.
    for cid in cast:
        pid = (req.poses or {}).get(cid)
        if not pid:
            continue
        ptext = promptlib.POSES_LIBRARY.get(pid) or pid
        parts.append(f"{face_tag[cid]}: {ptext}")

    # One wording, shared with the shot path, which had its own. See
    # promptlib.distinct_clause — this directive existed three separate times for
    # one measured failure (gate.check_cast's `blended`).
    distinct_clause = promptlib.distinct_clause([rows[c]["name"] for c in cast])
    if distinct_clause:
        parts.append(distinct_clause)

    # NOBODY ELSE IN FRAME. A brief that says "blurred crowd behind" gets one:
    # the nightclub scene came back with NINE faces, and check_cast then scores
    # "the one best matching the gallery" — which turns identity into a lottery
    # over strangers. Kiara took 0.5093 and a `drift` diagnosis on that frame.
    #
    # Default on, because a cast scene is about the cast. `allow_crowd` exists
    # for the venue and street briefs that genuinely want background life.
    crowd_clause = ""
    if cast and not req.allow_crowd:
        crowd_clause = promptlib.no_crowd_clause(len(cast)).strip()
        parts.append(crowd_clause)

    # WHEN AND WHAT THE AIR IS DOING. Every one of these emits nothing at all
    # when unset — no default. "Soft neutral lighting" appended to every prompt
    # is how a year of photographs ends up looking like one afternoon, and the
    # place and the hour already imply the light most of the time.
    for lib, key in ((_LIGHTING_FLAT, req.lighting),
                     (lighting_data.TIME_OF_DAY, req.time_of_day),
                     (lighting_data.WEATHER, req.weather),
                     (lighting_data.SEASON, req.season)):
        entry = lib.get(key or "")
        if entry and entry.get("text"):
            parts.append(entry["text"])

    holder = (promptlib.CAMERA_HOLDERS.get(req.holder) or {}).get("text", "")
    if holder:
        parts.append(holder)
    flaw = (promptlib.SNAPSHOT_FLAWS.get(req.flaws) or {}).get("text", "")
    if flaw:
        parts.append(flaw)

    # HER BUILD, PER PERSON. The shot path has carried build_clause and
    # carry_clause since they were written; a scene carried neither, so a
    # collaboration described nobody's figure and nobody's standing manicure —
    # the two things meant to be constant across every photograph she is in.
    #
    # Tagged per cast member rather than stated once, because with two women an
    # untagged "a 30-inch waist" is a description looking for someone to land on.
    # Same shape the pose lines above already use. Parts are per-character, so
    # each build comes from that character's own tree.
    for _cid in cast:
        _cparts = _load_parts(_cid)
        _who = face_tag.get(_cid, "")
        for _t in (promptlib.build_clause(_cparts), promptlib.carry_clause(_cparts)):
            if _t:
                parts.append(f"{_who}: {_t}" if _who and len(cast) > 1 else _t)

    # THE DOCTRINE, which this path never had. Every word of photographic
    # realism in the project lives in the camera/skin/constraints parts, and
    # until now a scene got one sentence ("Photorealistic, real skin texture")
    # while a shot got the whole part tree. Gated on the register for the same
    # reason it is on the shot path: telling an "Editorial photo" that it is
    # never a professional camera is an argument, not a directive.
    if req.shot_type in PHONE_REGISTERS:
        cap = promptlib.capture_clause(_load_parts())
        if cap:
            parts.append(cap)
    parts.append("Photorealistic, real skin texture, natural light, sharp focus "
                 "on every face.")

    # THE SHARED TAIL — same clauses, same order, same implementation as the
    # shot path. A pool scene used to come back with dry hair because the
    # wet-hair lock was written on the other path and never crossed over.
    #
    # `_is_wet_pose` reads the brief as well as the pose id, so a scene that
    # says "in the pool" gets it whether or not anyone picked a Pool & Water
    # pose for a cast member.
    parts.extend(promptlib.late_clauses(
        optics=req.optics, exposure=req.exposure,
        grooming_state=req.grooming_state,
        wet=_is_wet_pose(None, req.prompt or ""),
        subjects=max(1, len(cast))))

    assembled = " ".join(x for x in parts if x)

    # A written prompt replaces the PROSE assembled above — same contract as
    # ShotReq.prompt. The REFERENCES are still whatever the pickers spent, so the
    # @imageN tags the draft was written against stay valid; overriding the prose
    # must not silently re-order what the tags point at.
    #
    # But it used to replace the STRUCTURAL clauses too, and that is what broke
    # every collaboration in the database — all ten rejected. prompt_override is
    # the documented happy path (/api/scene/ai-prompt returns its draft "in
    # prompt_override's shape"), so in practice the role lines, the distinctness
    # clause and the crowd constraint were absent from every real scene.
    #
    # Traced on run d46c1a72ac, Kiara + Soni at a nightclub — five references
    # attached, TWO of them never named by the draft:
    #
    #   @image1 calib-front.webp          (Kiara's face)   named
    #   @image2 Outing4.webp              (outfit)         NOT NAMED
    #   @image3 nail5.jpg                 (manicure)       named
    #   @image4 soni-singh-identity.webp  (Soni's face)    named
    #   @image5 NightOut1.webp            (outfit)         NOT NAMED
    #
    # Result: 9 faces in frame, Kiara 0.5093 `drift`, rejected. Exactly the
    # failure the body-reference fix measured on the shot path, where one
    # unexplained image moved similarity 0.7838 -> 0.1473.
    #
    # So an override no longer gets to drop facts about what was ATTACHED. Any
    # reference whose tag the draft never mentions gets its role line back, and
    # the distinctness and crowd clauses are re-appended when missing. This is
    # the same precedent the shot path sets, where build_text, camera_holder and
    # flaws are appended to an AI prompt rather than trusted to it because a
    # prompt written earlier "would otherwise contradict them". Reference roles
    # are the stronger case: they describe what the model is actually being sent.
    # Missing ROLE lines open the prompt; the distinctness and crowd clauses
    # close it. That split is measured, not aesthetic. Moving the clauses to the
    # front on the theory that early placement wins — the argument the framing
    # note above makes — was tried and was WORSE on the same brief and refs:
    #
    #   clauses at tail : 6 faces | kiara 0.5024 | soni 0.6067 (kept)
    #   clauses at front: 8 faces | kiara 0.5251 | soni 0.4982 (rejected)
    #
    # n=1 each, so treat the ordering as weakly held; what it does rule out is
    # "just put the constraint first", which is the obvious next idea.
    override = (req.prompt_override or "").strip()
    if override:
        image_tags = [l["tag"] for l in ledger if l.get("mode") == "image" and l.get("tag")]
        unnamed = [t for t in image_tags if t not in override]
        head = " ".join(r for r in roles if any(t in r for t in unnamed))
        tail = [c for c in (distinct_clause, crowd_clause)
                if c and c.split(".")[0] not in override]
        raw = " ".join(x for x in ([head, override] + tail) if x)
    else:
        raw = assembled
    text, sanitised = promptlib.sanitise(raw)
    return {"prompt": text, "refs": refs, "cast": cast, "owner": owner,
            "ledger": ledger, "sanitised": sanitised, "assembled": assembled,
            "_roles": roles,
            "face_px": framing_data.estimate_face_px(
                req.framing, len(cast), req.aspect, req.resolution or RESOLUTION)}


@app.get("/api/scene/library")
def scene_library(cast: int = 1, owner: str = ""):
    """Moments, interactions and places for a cast of this size.

    Filtered SERVER-side by cast: an interaction that needs two people must not
    be offered to a solo scene, and the client should not have to know the rule.
    Places are the OWNER's and are labelled with her name, so "whose kitchen" is
    answered in the list rather than guessed at.
    """
    cid = owner or config.get_active()
    who = (db.chars_get(cid) or {}).get("name", cid)

    moments = {}
    for group, items in MOMENTS.items():
        keep = {mid: {**m, "id": mid} for mid, m in items.items()
                if m["min_cast"] <= cast}
        if keep:
            moments[group] = list(keep.values())

    # `label` is not decoration. Both of these are browsed by a component that
    # renders p.label, and without it 551 poses and 250 arrangements read as raw
    # kebab-case ids — "square-shoulders-direct" — which is exactly as useful as
    # the outfit dropdown that said "Casual1".
    inter = {}
    for group, items in INTERACTIONS.items():
        keep = [{"id": i, "label": i.replace("-", " "), "text": d["text"]}
                for i, d in items.items() if d["min_cast"] <= cast]
        if keep:
            inter[group] = keep

    places = []
    for c in (*HOME_CORNERS, *REGULAR_PLACES):
        f = _corner_file(c["key"], cid)
        # REGULAR_PLACES are already possessive ("Her gym", "Her street"), so
        # prefixing blindly produced "Kiara's her street".
        base = c["label"]
        base = base[4:] if base.lower().startswith("her ") else base
        places.append({"key": c["key"], "label": f"{who}'s {base.lower()}",
                       "has_image": bool(f)})
    def grouped(lib: dict, text_key: str = "") -> dict:
        """{group: [{id, label, text}]} — the shape every picker in the composer
        reads. Kept in one place so a new vocabulary is a data change only."""
        out = {}
        for group, items in lib.items():
            out[group] = [
                {"id": i,
                 "label": (d.get("label") if isinstance(d, dict) else None)
                          or i.replace("-", " "),
                 "text": (d.get(text_key or "text") if isinstance(d, dict) else d),
                 **({"face": d["face"]} if isinstance(d, dict) and "face" in d else {})}
                for i, d in items.items()]
        return out

    def flat(lib: dict) -> list[dict]:
        return [{"id": i, "label": d.get("label") or i, "text": d.get("text", "")}
                for i, d in lib.items()]

    return {"moments": moments, "interactions": inter, "places": places,
            "holders": [{"id": k, **v} for k, v in promptlib.CAMERA_HOLDERS.items() if k],
            "flaws": [{"id": k, **v} for k, v in promptlib.SNAPSHOT_FLAWS.items() if k],
            "shot_types": [{"id": k, "label": k} for k in promptlib.SHOT_TYPES],
            # framing carries its own predicted face size AT THIS CAST, so the
            # cost of a wide group shot is visible in the dropdown itself rather
            # than discovered afterwards in a verdict that says "abstain".
            "framing": [{"id": k, "label": v["label"], "text": v["text"],
                         "face_px": framing_data.estimate_face_px(
                             k, cast, "3:4", RESOLUTION)}
                        for k, v in sorted(framing_data.FRAMING.items(),
                                           key=lambda kv: kv[1]["order"]) if k],
            "aspects": framing_data.ASPECTS,
            "resolutions": ["1K", "2K", "4K"],
            "lighting": grouped(lighting_data.LIGHTING),
            "time_of_day": flat(lighting_data.TIME_OF_DAY),
            "weather": flat(lighting_data.WEATHER),
            "season": flat(lighting_data.SEASON),
            "hair": grouped(getup_data.HAIR_STYLING),
            "makeup": grouped(getup_data.MAKEUP),
            "accessories": grouped(getup_data.ACCESSORIES),
            "footwear": grouped(getup_data.FOOTWEAR),
            "poses": {g: [{"id": i, "label": i.replace("-", " "), "text": t}
                          for i, t in items.items()]
                      for g, items in promptlib.POSE_GROUPS.items()},
            "plateau_px": gate.FACE_PLATEAU_PX}


@app.post("/api/scene/ai-prompt")
def scene_ai_prompt(req: SceneReq):
    """Claude writes the scene prompt. Returned as a DRAFT, never sent to fal.

    The same contract as /api/shot/ai-prompt: Claude expands the brief, is
    forbidden to describe anyone, the result is sanitised and handed back for the
    user to edit. What differs is that a scene has already decided a great deal
    before Claude sees it — which tag holds whose face, how it is framed, what
    each of them is wearing — so all of that goes in as directives rather than
    being left for Claude to invent and then contradict.

    The draft comes back in `prompt_override`'s shape: paste it there and it is
    used verbatim, with the references unchanged, so the @imageN tags it was
    written against still point where it thinks they do.
    """
    s = _build_scene(req)
    rows = {c["id"]: c for c in db.chars_all()}
    tags = [l["tag"] for l in s["ledger"] if l["kind"] == "face" and l["tag"]]

    extra = ["Reference roles, which are already fixed and must be used exactly "
             "as given: " + " ".join(s["_roles"])]

    # NAME EVERY ATTACHED TAG. "Use the roles exactly as given" was not read as
    # "mention all of them": on the nightclub scene the draft named @image1,
    # @image3 and @image4 and described both OUTFITS in words instead, leaving
    # @image2 and @image5 attached with nothing said about them. Two unexplained
    # images went to the model and it returned nine faces.
    #
    # _build_scene now repairs that after the fact by prepending the missing role
    # lines, but a draft that names them itself puts each tag where the sentence
    # about it belongs, instead of in a block bolted to the front.
    img_tags = [l["tag"] for l in s["ledger"] if l["mode"] == "image" and l["tag"]]
    if img_tags:
        extra.append(
            "Every one of these reference tags is attached to the request and "
            "MUST appear at least once in the prompt you write, at the point "
            "where it is relevant: " + ", ".join(img_tags) + ". Do not describe "
            "an outfit or a manicure in words instead of pointing at its tag — "
            "the image is attached either way, and an image the prompt never "
            "names is one the model has to guess the purpose of.")

    frame = (framing_data.FRAMING.get(req.framing) or {}).get("text", "")
    if frame:
        # Framing goes in as a REQUIREMENT rather than a hint. Prose framing lost
        # to the model's default once already (2026-08-04, the head-and-shoulders
        # crop that came back waist-up); if Claude is writing the prompt, the
        # constraint has to survive into what it writes.
        extra.append(f"Include this framing instruction near the START of the "
                     f"prompt, close to verbatim: '{frame}'")
    if len(s["cast"]) > 1:
        extra.append("Do NOT invent an interaction or arrangement that "
                     "contradicts the reference roles above.")

    # NO CROWD, unless it was asked for. The draft that produced nine faces wrote
    # "blurred crowd behind" of its own accord — the brief said a stranger took
    # the photo in a club, and Claude filled the room in. _build_scene appends a
    # crowd constraint, but it then contradicts the draft's own prose and loses:
    # regenerating still gave six faces. The fix has to be that the prose never
    # asks for a crowd in the first place.
    #
    # This matters because the gate scores whichever face best matches the
    # gallery, so background people are not set dressing — they are extra chances
    # to score a stranger and call it her.
    if not req.allow_crowd:
        extra.append(
            "Do NOT write any background people into the scene. No crowd, no "
            "bystanders, no other patrons, dancers, staff or passers-by, and no "
            "reflections of other people — not even blurred, out of focus or in "
            "the far background. A busy venue is conveyed with lighting, "
            "bottles, glassware, furniture and depth of field, never with other "
            "human beings. Exactly "
            f"{len(s['cast'])} {'person is' if len(s['cast']) == 1 else 'people are'} "
            "in the photograph.")

    try:
        raw = prompter.rewrite(
            req.prompt, shot_type=req.shot_type, has_wardrobe=False,
            pose_text=req.activity.strip(), cast=len(s["cast"]),
            cast_tags=tags, extra_directives=extra)
    except prompter.PrompterError as exc:
        raise HTTPException(400, str(exc)) from exc
    clean, sanitised = promptlib.sanitise(raw)
    return {"prompt": clean, "sanitised": sanitised, "assembled": s["assembled"],
            "cast": [rows[c]["name"] for c in s["cast"] if c in rows],
            "ledger": s["ledger"], "face_px": s["face_px"]}


@app.post("/api/scene/preview")
def scene_preview(req: SceneReq):
    """The exact prompt, and the ledger of what it spent — before spending it.

    The composer renders this rather than guessing: which references are attached,
    at which tag, and what fell back to text. Tag roles are the failure that would
    be invisible in the output, so they are readable here first.
    """
    s = _build_scene(req)
    images = [x for x in s["ledger"] if x["mode"] == "image"]
    return {"prompt": s["prompt"], "cast": s["cast"], "owner": s["owner"],
            "ledger": s["ledger"], "images": len(images),
            "sanitised": s["sanitised"], "assembled": s["assembled"],
            # The predicted face size, and the measured band it lands in. This is
            # the number that decides whether the gate can say anything at all
            # about the picture, so it belongs next to the button, not in the
            # verdict afterwards.
            "face_px": s["face_px"], "plateau_px": gate.FACE_PLATEAU_PX}


@app.post("/api/scene")
def scene(req: SceneReq):
    """Generate a scene from prose with @mentions.

    Owned by the FIRST character mentioned, with the whole cast on the row —
    the shape check_cast and the review already understand, so a scene needs no
    new review surface and the others still see themselves in it.
    """
    s = _build_scene(req)
    cast, owner, refs = s["cast"], s["owner"], s["refs"]
    session = generate.new_session(req.prompt.strip()[:60] or "scene")

    def run(job: dict) -> dict:
        return generate.generate(
            prompt=s["prompt"], system="", refs=refs, aspect=req.aspect,
            seed=req.seed, session=session, progress=job, character=owner,
            fallback_endpoint=SCENE_EDIT, resolution=req.resolution,
            safety_tolerance=req.safety_tolerance, model=req.model,
            meta={"brief": req.prompt, "scene": True, "cast": cast,
                  "wardrobe_by": req.wardrobe, "place": req.place,
                  "activity": req.activity, "interaction": req.interaction,
                  # The ledger is kept so a scene can be read back later and the
                  # reference count explained rather than re-derived.
                  "ledger": s["ledger"],
                  "bio_references": [p.name for p in refs]})

    return {"job": generate.start_job(f"scene: {'+'.join(cast)}", run),
            "cast": cast, "references": len(refs)}


@app.post("/api/shot/preview")
def shot_preview(req: ShotReq):
    """The exact prompt this shot will send, and what it spent to get there.

    This used to compose its OWN approximation with compose_tagged and nothing
    else — no outfit styling, no nail line, no place line, no timeline clause, no
    body-reference directive. It reported ~880 characters for a prompt that
    shipped at 4,517, so the one time a preview would have earned its keep it
    said everything was fine.

    Now it runs the real path with preview=True and returns before generating.
    The prompt shown is the prompt sent, because it is the same string.
    """
    return shot(ShotReq(**{**req.dict(), "preview": True}))


# ------------------------------------------------------ learning from approvals
# Human approvals drive LEARNING — but never the gallery. Feeding approved output
# back into the yardstick drifts it toward the generator (the number climbs while
# the identity walks away; see gate.py). So approvals do two SAFE things instead:
#   1. Analytics — keep-rate by pose/outfit, so you learn which recipes work.
#   2. A gold set — the curated dataset a future LoRA trains on, kept apart from
#      the frozen gate.

def _shots() -> list[dict]:
    """Runs that are actual shots (have a brief) — not calibration/body/outfit gen.

    Clips are excluded even though they carry a brief. A video is `ungated` by
    construction — frame scoring is Phase 2 — so counting one here would move
    keep-rate without anything about her having changed, which is exactly the
    kind of manufactured number the gate exists to prevent. Same reasoning as the
    wardrobe turnaround: not gateable is not the same as not kept.
    """
    return [r for r in generate.all_runs()
            if "brief" in (r.get("meta") or {}) and (r.get("kind") or "") != "video"]


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

    # Stale thumbnails whose source image no longer exists. Clips count as live
    # sources here even though they are never scanned for deletion above — their
    # poster lands in the same .thumbs/ dir, and leaving them out of this set
    # deleted (and re-decoded) every video poster on every cleanup.
    if thumbs.exists():
        live = {p.stem for p in IMAGES.iterdir()
                if p.is_file() and p.suffix.lower() in (*exts, *VIDEO_SUFFIXES)}
        for t in thumbs.glob("*.jpg"):
            if t.stem not in live:
                t.unlink(missing_ok=True); counts["stale_thumbs"] += 1

    return {**counts, "freed_mb": round(freed / 1e6, 1)}


@app.get("/api/health")
def health():
    return {"ok": True, "root": str(ROOT)}
