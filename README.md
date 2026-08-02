# Throughline

**One face. Hundreds of shots. Zero drift.**

Throughline is a character-asset pipeline for producing hundreds of photorealistic
images of the *same* fictional person over time — across outfits, poses, scenes
and angles — without the face drifting into a different person every generation.

It's a **multi-character studio**: each character carries its own identity
fingerprint, calibration, body library, wardrobe, poses and images.

---

## The idea

**"Is this still her?" is a number, not a judgement.**

Every generated image is embedded with **ArcFace** and scored against the
character's gallery. The image generator is a swappable box in the middle; the
identity **gate** is model-agnostic and outlives whatever we generate with. Two
consequences show up throughout the app:

- **Identity is carried by reference images, never by describing the face in
  words.** When a reference exists, face-describing prompt fragments are dropped —
  words specify a *type*, not a *person*.
- **Every verdict is shown with its head-yaw and face-pixel size next to the
  similarity score** — a frontal image scores high whether or not a pose request
  was honoured, so the score is never read alone.

The one axis the gate is blind to is her **body** (clothing varies, so person
re-ID can't key on it); for that there's a manual approve/reject verdict.

> `FINDINGS.md` holds the measured numbers behind these decisions — read it (and
> `CLAUDE.md`) before changing the pipeline.

---

## Features

- **Character picker** — create a character (Claude writes a bio → generates the
  first face → sets a seed), enter, or delete.
- **Shoot** — brief + optional Claude-written prompt, resolution, face-accessory
  toggle, wardrobe + pose-library pickers, and a live generation queue that gates
  each shot the moment it finishes.
- **Bio** — identity reference management (import / upload / set BIO / add to
  gallery), body-type library + body-reference generation, and the editable part
  tree.
- **Calibrate** — seed → generate faces → approve on-model faces into a frozen
  fingerprint → recalibrate the threshold.
- **Outfit designer** — describe an outfit from a photo (Claude), enrich it with a
  tweak + attribute pickers, generate a turnaround, and save it to the wardrobe.
- **Review** — keep-rate stats by pose/outfit, approve/reject, export the
  human-approved **gold set** (a future LoRA dataset), and reclaim disk.

---

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI app, the ArcFace gate, prompt/part tree, fal generation |
| `backend/gate.py` | ArcFace embedding, gallery, threshold, calibration |
| `backend/prompt.py` | The part tree + `compose()` — every prompt fragment is editable data |
| `frontend/` | The UI — React + Vite + Tailwind (shadcn/ui), talks to `/api` |
| `frontend-legacy/` | Previous UI, archived for reference |
| `FINDINGS.md` | **Read first.** Measured results the pipeline is built on |
| `CLAUDE.md` | Project context and hard rules |
| `data/` | Generated images, gallery, per-character state, SQLite db — **gitignored** |

Runs and wardrobe metadata live in a single global SQLite db
(`data/eve1.db`); the per-character files live under `data/characters/<id>/`.

---

## Setup

**Prerequisites:** Python **3.11** (not 3.14 — `onnxruntime` has no wheels for it),
Node 18+, a [fal](https://fal.ai) API key, and an [Anthropic](https://console.anthropic.com) API key.

The code is **cross-platform**. Linux is the deploy target; native Windows still works.

### Linux / WSL (recommended)

```bash
cp .env.example .env      # then put your real keys in .env
./setup.sh                # venv (.venv) + backend deps + frontend + .env
./run.sh                  # backend :8000 + frontend :5173
```

Open **http://localhost:5173**. `./run.sh backend` or `./run.sh frontend` run one side.

If `python3.11` is missing on Ubuntu/WSL: `sudo apt install python3.11 python3.11-venv`.

### Windows (native)

```bash
cp .env.example .env
py -3.11 -m venv .venv-win
.venv-win\Scripts\python.exe -m pip install -r requirements.txt
.venv-win\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
# in a second terminal:
cd frontend && npm install && npm run dev      # http://localhost:5173
```

`.env` keys either way:

```
FAL_KEY=…            # image generation (fal.ai)
ANTHROPIC_API_KEY=…  # Claude — bio writing, AI prompt, describe/enrich
```

### What a character *is*

Three things: her **bio**, her **body**, and her **home**.

| | Stored as | Why it's identity |
|---|---|---|
| **Bio** | `state/bio.json`, `state/parts.json`, `refs/` | `refs/` is `@image1` — her face. Measured 0.860 with a reference against 0.531 from description alone, so words cannot stand in for it. `parts.json` is her written identity; absent, the code falls back to `default_parts()` and she is quietly replaced by a stranger's defaults. |
| **Body** | `state/bodies.json`, `bodies/`, `bio.json → body_reference` | The one axis the gate is blind to (person re-ID keys on clothing, which varies by design). No automated backstop, so losing it is unrecoverable. |
| **Home** | `state/home.json`, `places/` | Ten corners from one shared house style. "Her kitchen" means one specific kitchen, not a kitchen invented per shot. |

Everything else — wardrobe, poses, nails, past generations — is per-shoot
dressing. It can be remade. These three cannot.

Guided creation is built around exactly this: **bio → body → home**. Fill in the
home style and all ten corners generate on submit (≈10 extra generations, a few
minutes); leave it blank and it's skipped entirely, to be built later from the
Home tab.

---

## Moving to another machine

Three separate channels, none of which overlap. Cloning gets you the app; it
cannot get you the character.

| | Carried by |
|---|---|
| Code, docs, `package-lock.json`, `.env.example` | **git** |
| `data/` — refs, places, bodies, state, `eve1.db` | **`scripts/sync_data.sh`** |
| `FAL_KEY`, `ANTHROPIC_API_KEY` | **you, by hand** |

`data/` is gitignored (11 GB) and `eve1.db` has never been in git on any branch.
That is deliberate: it is binary, it churns on every generation, and it indexes
images git should not be carrying.

### 1. On the NEW machine — clone and install

```bash
git clone git@github.com:Ktechss/Throughline.git
cd Throughline
./setup.sh
```

Needs **Python 3.11 specifically** — not 3.12+, not 3.14; `onnxruntime` has no
wheels beyond it and `setup.sh` refuses rather than half-installing. Node 20+ too.

### 2. On the OLD machine — send her

```bash
./scripts/sync_data.sh user@newbox:~/Throughline     # ~750 MB
```

No SSH between them? Write to a drive and carry it:

```bash
./scripts/sync_data.sh /mnt/d/throughline-backup     # then on the new box:
                                                     #   cp -r /mnt/d/throughline-backup/data ~/Throughline/
```

⚠ **Migrate before you generate anything on the new box.** The sync overwrites
`DEST/data/eve1.db` wholesale, so any runs made there first are silently replaced.

### 3. On the NEW machine — keys, then go

`.env` is never copied by the sync. Read the two keys off the old box (`cat .env`)
and paste them into the new one's `.env`, which `setup.sh` has already created
from the template.

```bash
./run.sh          # http://localhost:5173
```

The first gate check downloads ArcFace (`buffalo_l`, ~290 MB) into
`~/.insightface`. One-off, needs network.

### What you land with

| Tab | State |
|---|---|
| **Bio** | Complete. Her part tree with your edits, every face reference, both body types, all 10 home corners, nails, timeline. |
| **Calibrate** | Works immediately — gallery loads at its stored threshold, so the gate answers with a number from the first shot rather than `ungated`. |
| **Shoot** | Generates normally. *The outfit picker is empty* — see below. |
| **Review** | Every run, with prompt, seed, verdict, yaw, face_px, confounds and your marks. *Thumbnails are broken* — see below. |

Two deliberate gaps, both by the definition above:

- **No past generations.** `images/` is skipped, so review rows show their numbers
  without their pictures. `--with-images` sends them (7.2 GB instead of 750 MB).
- **Empty wardrobe.** Dropped entirely — images *and* db rows — so the far side
  gets a clean wardrobe rather than a list of garments whose files aren't there.
  Your source db is never modified. There is no flag to include it.

### Verify it arrived

```bash
.venv/bin/python -c "
from backend import gate, config
n = lambda p: len([f for f in p.iterdir() if f.is_file()])
print('gallery:', len(gate.load_gallery()), 'entries')
print('refs:   ', n(config.REFS))
print('bodies: ', n(config.BODIES))
print('places: ', n(config.PLACES))
"
```

A gallery of `0` means `state/gallery.npz` did not cross and every run will come
back `ungated` — the number this whole project is built around would silently
stop existing.

---

## Status & notes

- Active WIP. "Zero drift" is the design goal (the gate *measures* drift), not a
  guarantee.
- She is entirely fictional — no real person's likeness, anywhere. Never put a real
  person's name in a prompt.
- ⚠ Keep secrets out of git: `.env` is gitignored (only `.env.example` is
  committed). Rotate the fal key to a plain, non-admin API key.
- `data/` is regenerable and huge — it is not tracked.
