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

---

## Status & notes

- Active WIP. "Zero drift" is the design goal (the gate *measures* drift), not a
  guarantee.
- She is entirely fictional — no real person's likeness, anywhere. Never put a real
  person's name in a prompt.
- ⚠ Keep secrets out of git: `.env` is gitignored (only `.env.example` is
  committed). Rotate the fal key to a plain, non-admin API key.
- `data/` is regenerable and huge — it is not tracked.
