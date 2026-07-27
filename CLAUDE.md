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
| `backend/skeleton.py` | OpenPose-18 rig + renderer. The rendered PNG *is* the reference image |
| `backend/gate.py` | ArcFace. Gallery, abstain floor, calibration |
| `backend/generate.py` | fal calls + run bookkeeping. Every run records its exact prompt |
| `backend/main.py` | FastAPI |
| `frontend/src/pages/Studio.jsx` | Shoot / bio / calibrate / video / review tabs (UI) |
| `frontend/src/api/useStudio.js` | Frontend orchestration hub (data + all actions) |
| `data/` | Generated images, poses, part tree, gallery. Gitignored |

## Running it

    .venv-win\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
    cd frontend && npm run dev        # http://localhost:5173

Python **3.11** (`.venv-win`) — not 3.14, which has no onnxruntime wheels. The
old WSL `.venv` is gone; this is native Windows.

## Open questions

- **Does the pose image actually work?** The skeleton is passed to
  nano-banana as an ordinary reference and the model is *asked* to match it.
  That is suggestion, not conditioning. Verify by reading back **yaw**, never
  similarity. If it's too weak, the same renderer feeds a real ControlNet
  endpoint unchanged.
- **What does the pose reference cost in identity?** It spends a reference slot,
  and three references measured 0.547 against one's 0.811. Unmeasured here.
- **No face is chosen yet.** The gallery is empty, so runs come back `ungated`.
  That is the correct state for a seed hunt — there is no "her" yet.

## Hard rules

- She is entirely fictional. No real person's likeness, anywhere, ever.
- Never put a real actress's name in a prompt.
- ⚠ The fal key in `.env` is **admin-scoped** — rotate it to a plain API key.
  Generated images land on public, unauthenticated `v3b.fal.media` URLs.
