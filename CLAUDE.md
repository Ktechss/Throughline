# Project context for Claude Code

Read this and `FINDINGS.md` before changing anything.

## What this is

A character asset pipeline for a fictional South Delhi fashion stylist. Goal:
hundreds of photorealistic images of the *same woman* over a year, without
identity drift.

Rebuilt from scratch 2026-07-17. The previous build was deleted at the owner's
instruction; `FINDINGS.md` is what was carried out by hand, and it is the most
valuable file here — those numbers cost weeks and the raw data behind them is
gone.

## The spine

**"Is this still her?" is a number, not a judgement.** `backend/gate.py` embeds
every generated image with ArcFace and scores it against a gallery. The
generator is a swappable box in the middle; the gate is model-agnostic and
outlives whatever we generate with.

**Corollary: never add a "does this look like her?" step a human eyeballs.**
If you want one, you want a number instead.

The one exception, and it is real: **her body**. Person re-ID keys on clothing,
which varies by design, so there is no automated body-consistency check. The
`mark` field on each run (stored in the `runs` table of `data/eve1.db`) is a
human verdict, and it exists precisely for the axis the gate is blind to.

## Two rules the code enforces so nobody has to remember them

**1. Never describe her face when a reference image exists.**
`prompt.compose(has_reference=True)` drops every `identity=True` part
automatically and substitutes a terse identity lock. Measured: reference + terse
0.860, reference + description 0.834, description alone 0.531. Words cannot
specify a person — they specify a *type*, and the model returns a different
member of that type every seed.

**2. Never read a similarity score without its yaw.** `corr(|yaw|, sim) =
-0.761`. Every verdict carries `yaw` and `face_px`, and the UI shows them next
to the number. A model that ignores a pose request returns a frontal image, and
frontal images score high — so a broken pose control looks like success.

## Layout

| Path | What |
|---|---|
| `FINDINGS.md` | **Read first.** Measurements carried over; raw data gone |
| `backend/prompt.py` | The part tree + `compose()`. Every prompt fragment is editable data, not code |
| `backend/gate.py` | ArcFace. Gallery, abstain floor, calibration |
| `backend/generate.py` | fal calls + run bookkeeping. Every run records its exact prompt |
| `backend/main.py` | FastAPI |
| `frontend/src/pages/Studio.jsx` | Shoot / bio / calibrate / review tabs (UI) |
| `frontend/src/api/useStudio.js` | Frontend orchestration hub (data + all actions) |
| `data/` | Generated images, poses, part tree, gallery. Gitignored |

## Running it

The code is **cross-platform** (Linux server / WSL + native Windows). Paths are
all `pathlib`-relative; nothing branches on the OS except the `.venv-gen`
interpreter location in `config.py`.

**Linux / WSL** (the deploy target):

    ./setup.sh          # one-time: venv + deps + frontend + .env
    ./run.sh            # backend :8000 + frontend :5173  (open :5173)

**Windows** (native dev, still supported):

    .venv-win\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
    cd frontend && npm run dev        # http://localhost:5173

Python **3.11** either way — not 3.14, which has no onnxruntime wheels. On Linux
the venv is `.venv` (`bin/python`); on Windows it's `.venv-win`
(`Scripts\python.exe`). Two portability notes baked into `setup.sh`:
`python-multipart` is required for the upload endpoints, and the headless
`opencv-python` build must win over the full one insightface drags in (the full
one links `libGL`, absent on a GUI-less server).

## Open questions

- **How does she hold up off-frontal and full-body?** Every generator row in
  `FINDINGS.md` is a frontal studio close-up. The two places both previous
  generators collapsed are still untested here.

## Measured here (was an open question)

- **A reference slot costs ~0.04.** Comparing only shots at a matched 400-600px
  face size, so framing can't explain it: 2 refs scored **0.622** (n=54), 3 refs
  **0.579** (n=23) — and only ~0.006 of that gap is their yaw difference. Same
  direction as FINDINGS' 0.547-vs-0.811. `config.REF_BUDGET` holds a shot to two
  references and demotes the rest to their text form; observational, not a
  controlled trial, so re-measure before raising it.
- **Face size plateaus at ~400px.** Over 207 shots: <250px 0.472, 250-400px
  0.548, 400-600px **0.612**, 600+ 0.608. Steep below, flat above. This is why
  `gate.FACE_PLATEAU_PX` exists and why the prompter frames tight by default.
- **Most rejections are framing, not drift.** Of 67 shot rejections: 23
  small-face, 22 off-frontal, 12 tilted, and only **10** with no confound to
  explain them. `Verdict.diagnosis` names which, so the distinction stops being
  a judgement call.
- **A wardrobe turnaround cannot be gated.** The sheet holds four faces, the gate
  embeds the largest, and in a full-body panel that lands near 200px — 116 of 118
  rejected, every one for face size. They generate `gated=False` now: a garment
  swatch is not a photo of her.

## Still true

- **The gallery is Kiara's**, 13 entries, threshold **0.646**. The seed hunt is over;
  `ungated` now means a swatch or an empty gallery, not "no her yet".

## Hard rules

- She is entirely fictional. No real person's likeness, anywhere, ever.
- Never put a real actress's name in a prompt.
- ⚠ The fal key in `.env` is **admin-scoped** — rotate it to a plain API key.
  Generated images land on public, unauthenticated `v3b.fal.media` URLs.
