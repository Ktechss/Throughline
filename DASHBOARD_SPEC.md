# Throughline dashboard — build spec / AI-UI prompt

A copy-paste build prompt for recreating the Throughline frontend in another UI tool
(v0, Lovable, Bolt, Figma Make, or hand-built). It captures the layout, every
feature, the interaction model, the design system, and the backend API contract
so the rebuilt UI can wire straight to the existing FastAPI backend.

---

**Build a single-page dashboard called "Throughline" — a control panel for a
photorealistic AI character-image pipeline. It's a client-side SPA that talks to
an existing REST backend (all endpoints under `/api`, proxied to
`http://localhost:8000`). Dark theme, dense but clean, desktop-first.**

## Design system
- **Theme (dark):** bg `#0c0c0f`, panel `#14141a`, border `#24242e`, text `#e6e6ea`, dim `#8a8a99`. Accent blue `#4ea1ff`, ok green `#33c07f`, bad red `#e2564a`, warn amber `#d99a2b`.
- **Type:** system sans for UI; monospace (`ui-monospace`) for prompts, IDs, code. Uppercase micro-labels with letter-spacing for section headers.
- **Cards:** panel bg, 1px border, 8px radius. Selected/active state = accent border + 1px accent glow. Images use `aspect-ratio: 4/5; object-fit: cover`.
- Max content width ~1180px, centered. Small "tag" chips (10px) for statuses.

## Global shell
- **Header:** title "Throughline" · nav tabs `shoot | bio | review` (review shows a count) · right-aligned "gallery: …" status text.
- **Error banner:** dismissible red bar under the header (click to clear).

## Screen 1 — SHOOT (default)
The generation workspace. Top to bottom:
1. **BIO chip:** a bordered accent strip showing the locked identity — thumbnail + filename + "face px · N angles · attached to every shot", and a "change" button that jumps to Bio → Face. If none set, show an amber warning.
2. **Brief textarea:** free-text "what's the shot? place, moment, mood".
3. **Outfit strip (→ @image2):** a horizontal scroll of outfit thumbnails (selectable, one active). Prepended by a "brief / default" (none) card and appended by a "+ outfit" upload card. Above the strip, a row with: a text input to describe an outfit, a **"describe from image"** file-upload button (uploads an image, an AI vision endpoint returns a garment description into the input), and a **"create outfit"** button (kicks off an async job that generates a 4-panel turnaround and adds it to the strip — show inline "creating… {stage}").
4. **Pose-reference strip (→ @image3):** same pattern (none card + thumbnails + "+ pose" upload).
5. **Action row:** a primary **generate** button, a **"✦ AI prompt"** button (calls an endpoint where Claude rewrites the brief into a full scene prompt), and a live summary "outfit X · pose ref Y".
6. **AI-prompt box (conditional):** when AI prompt returns, show an editable textarea with the generated prompt + a "clear · use template" button. If present, this text is sent verbatim on generate; if empty, the backend uses its template.
7. **Lint (conditional):** if the brief mentions clothing words but no outfit is selected, show an amber hint.
8. **Generations grid — the core feature:** a responsive grid of cards, newest first.
   - **Non-blocking + multi:** clicking generate immediately appends a new card and starts polling that job independently. The user can fire many; they run in parallel and never lose state or navigate away.
   - **Card states:** *running* (spinner + human-readable stage label + "moderation retry N" chip if retrying + elapsed seconds + label); *done* (the image + a status chip + similarity score + "scene-model" chip if it used the fallback model — clickable); *failed* (red card + error text).
   - Clicking a done card opens the **Origin modal** (below).

## Screen 2 — BIO
Sub-navigation: `overview | advanced · face | advanced · parts`.
- **Overview:** the locked identity reference image + the "identity lock" text + the gate summary (gallery angles as chips with yaw, threshold). Below, read-only sections (subject/face/body/hair/skin/camera/constraints) rendered as dashed "locked" cards showing each part's label + text.
- **Advanced · Face:** import (by path) / upload identity reference images. A grid of reference cards; each shows the image, a "★ BIO" badge if it's the active identity, a usability chip (pose class / "no face"), face-px, yaw. Actions per card: **set as BIO** (makes it the locked identity for every shot), **→ gallery** (adds it to the identity gate under a chosen view), **delete**.
- **Advanced · Parts:** an editable list of every prompt fragment, grouped by section. Each part: enable checkbox, label, "load-bearing"/"identity" tags, an editable textarea (saves on blur), and a note. A "reset to defaults" button.

## Screen 3 — REVIEW
The permanent archive of every generation, grouped by session (newest first). Each session header shows label · image count · best score · timestamp. Each run card: image (click → Origin modal), verdict chips (status, similarity struck-through if pose-mismatched, yaw, face-px, tilt), a provenance line (model · "scene-model"/"AI prompt" flags), and approve / reject / origin buttons.

## Origin modal (shared by shoot + review)
A centered overlay. Left: the large image + approve / reject / → wardrobe / → pose-ref actions. Right: title, verdict chips, a key-value grid (model, fallback flag, "prompt by": Claude vs template, seed, aspect, time, created), the brief, the **full prompt sent to the model** (monospace block), any moderation "sanitised" substitutions, and a **references-used** row of thumbnails (face + outfit + pose-ref, each labeled) plus the ordered ref list. Click backdrop or ✕ to close.

## Verdict chips (reused)
`status` chip (kept=green, rejected=red, abstain/ungated/no_face=amber) · similarity (bold, struck-through when `pose_mismatch`) · "yaw ±N°" · "Npx" · "tilt ±N°" · optional "low signal" / "pose mismatch" tags.

## Backend API contract (wire to these exactly)
- `GET /api/bio` → `{ reference, body_reference, reference_face:{face_px,yaw,pose_class}, identity_lock, dropped_identity_parts, sections:{section:[{id,label,text,critical,note}]}, gallery:{entries,meta,threshold} }`
- `PUT /api/bio/reference` `{reference}` — set locked identity
- `GET /api/refs` → `{refs:[{name,face_px,yaw,pose_class,usable,reason?}]}`; `POST /api/refs/import {path}`; `POST /api/refs/upload` (multipart `file`); `DELETE /api/refs/{name}`; `GET /api/refs/{name}/file`
- `POST /api/gallery/from-ref {name,view}`; `GET /api/gallery`
- `GET /api/parts` → `{parts:[{id,section,label,text,enabled,identity,critical,note}],sections}`; `PUT /api/parts {parts}`; `POST /api/parts/reset`
- `GET /api/wardrobe` → `{wardrobe:[{id,file}]}`; `POST /api/wardrobe/upload` (multipart); `POST /api/wardrobe/describe` (multipart `file`) → `{outfit}`; `POST /api/wardrobe/create {name,outfit}` → `{job}`; `POST /api/wardrobe/from-run {run_id,name}`; `GET /api/wardrobe/{file}/file`
- `GET /api/pose-refs` → `{pose_refs:[{id,file}]}`; `POST /api/pose-refs/upload` (multipart); `POST /api/pose-refs/from-run {run_id,name}`; `GET /api/pose-refs/{file}/file`
- `POST /api/shot` `{brief, prompt?, aspect, wardrobe_id?, pose_ref_id?, shot_type}` → `{job, sanitised}`
- `POST /api/shot/ai-prompt` `{brief, wardrobe_id?, pose_id?, pose_ref_id?, shot_type}` → `{prompt, sanitised}`
- `GET /api/jobs/{id}` → `{id,label,stage,done,error,retry,elapsed,run}` — **poll every 1.5s until `done`**
- `GET /api/runs` → `{runs:[run]}`; `POST /api/runs/{id}/mark {decision}` (`approve|reject|null`); `GET /api/images/{file}`
- **run object:** `{id, session:{id,label,started}, file, endpoint, moderation_fallback, prompt, seed, aspect, seconds, created, mark, refs:[names], meta:{brief,bio_references,wardrobe,pose_ref,ai_prompt,sanitised}, verdict:{status,similarity,yaw,face_px,roll,tilted,pose_mismatch,low_confidence,reason}}`

## Behaviors that matter
- Job polling is **per-card and independent** — never a single global "busy" that blocks the UI or forces navigation.
- Stage labels map raw job stages to friendly text (e.g. `generating → "Generating…"`, `scene-model fallback → "Refused — trying scene model…"`).
- After a job finishes, refresh the runs/gallery/refs lists so the archive and gate stay current.
- All uploads are `multipart/form-data` with field name `file`.
- `@image1` = face/identity (always), `@image2` = outfit, `@image3` = pose reference. The prompt refers to these tags; the frontend just attaches the images in that order.

## Domain notes (so the UI copy is accurate)
- Identity is carried by a **reference image**, never described in words — the app deliberately drops face-description fields once a reference exists.
- The "gate" is an automated face-similarity check; scores come with **yaw / face-px**, and a full-body shot legitimately scores lower (small face) — that's framing, not drift.
- The **scene-model fallback**: if the primary image model refuses on content policy, the backend retries on a second model automatically and flags it (`moderation_fallback`), which the UI surfaces as a "scene-model" chip (weaker identity).
