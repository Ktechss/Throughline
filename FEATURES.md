# Throughline — Frontend Features

## Project description

Throughline is a character-asset pipeline for producing hundreds of
photorealistic images of the *same* fictional person over time, without identity drift. It is a multi-character studio: each character has
its own identity fingerprint, calibration, body library, wardrobe, poses and
images.

The spine of the system is a measured identity check, not a human eyeball. Every
generated image is embedded with ArcFace and scored against the character's
gallery ("is this still her?" is a *number*). The image generator is a swappable
box; the identity gate is model-agnostic. Two consequences show up throughout the
UI:

- Identity is carried by **reference images**, never by describing the face in
  words. When a reference exists, face-describing prompt parts are dropped.
- Every verdict is shown with its **yaw** (head angle) and **face pixel size**
  alongside the similarity score — because a frontal image scores high whether or
  not a pose request was honoured, so the score is never read alone.

The one axis the gate is blind to is her **body** (clothing varies, so re-ID
can't key on it); for that there is a manual approve/reject verdict.

The frontend is a single-page React app (Vite) that talks to a FastAPI backend
under `/api`. Long operations run as backend jobs that the UI polls.

---

## Global / navigation

- Two top-level views: a **character picker** (landing) and a **studio** for the
  active character.
- Studio has four tabs: **shoot**, **bio**, **calibrate**, **review**.
- The review tab shows a live count of shot images (excludes wardrobe/body/calibration runs).
- "Switch character" returns to the landing picker; if a generation is still in
  progress, a confirmation warns that the in-progress preview will be lost.
- Switching characters wipes all per-character client state so nothing bleeds
  between profiles, and cancels any in-flight polling.
- Dismissible error banner for any failed action.

## Character management (landing / picker)

- View all characters as selectable profiles; each shows an avatar (or initials
  fallback), name, and an **identity status** indicator (`identity set` vs
  `needs calibration`).
- Enter a character to open its studio; the active character is highlighted.
- **Create a character** via a form:
  - Name (required).
  - Free-text description (optional; left blank, Claude invents a coherent person).
  - Face shape picker (oval / round / square / heart / diamond / oblong; optional).
  - Body type picker (slim / athletic / curvy / voluptuous / full-figured; optional).
  - Height slider (148–190 cm, shown in both cm and ft/in).
  - Optional reference face image upload (with preview + remove); her face is
    built as a real human based on it, or generated fresh from the description.
  - On submit: Claude writes her bio → generates her first face → sets the seed,
    with a live build-progress label. New character lands on the calibrate tab.
- **Delete a character** (and all her images, wardrobe, generations) with
  confirmation. Deletion is blocked for the last remaining/active character.

## Shoot tab (generate images)

- **Bio banner**: shows the active identity reference thumbnail, identity-lock
  status, reference name, face pixel size, and gallery angle count; clicking it
  jumps to the bio tab.
- **Shot brief**: free-text description of place/moment/mood.
- **AI prompt**: generate a Claude-written prompt from the brief + selected
  outfit/pose; the result is shown in an editable box, and can be cleared to fall
  back to the template. If left empty, the template prompt is used.
- **Resolution**: choose 1K / 2K / 4K.
- **Face-accessories toggle**: render face-worn outfit items (sunglasses/hats) or
  keep the face clear for the best identity score.
- **Outfit selection**:
  - Pick a saved outfit from the wardrobe panel, filterable by category, or clear
    to none. Upload a new outfit image directly. Delete an outfit (confirmed).
  - Inline outfit builder: type an outfit description and **create outfit**
    (generates a turnaround), or open the full **outfit designer** drawer.
  - Outfit preview after creation: **save to a category** (auto-named
    `<Category><n>`, unique so it never overwrites another) with an option to add
    a new category, or **discard**.
- **Pose selection**:
  - Browse the pose library by category tabs; select/deselect a pose preset.
  - Selected pose text is shown; **clear** resets the pose.
  - Optional **pose-reference image** override (select from saved pose refs,
    upload a new one, or use none).
  - Notice shown when reusing a saved pose whose id is no longer in the library.
- **Generate**: fires a shot. Requires a bio reference plus at least one of
  brief / outfit / pose ref. Multiple generations can be fired in parallel.
- **Generations queue**: one card per generation, showing live stage, elapsed
  time, and moderation-retry state while running; on completion, the image plus
  its gate verdict (status, similarity, yaw, face px). Click a finished card to
  open its full origin/detail.

## Bio tab (identity, body, parts)

Four sub-views: **overview**, **advanced · face**, **advanced · body**,
**advanced · parts**.

- **Overview** (read-only): identity reference image, identity-lock text, gate
  threshold, gallery angle count and per-angle chips with yaw, and the character's
  body-part text grouped by section.
- **Advanced · face**:
  - Import a face by filesystem path, or upload a face image.
  - Reference grid; each card shows the image, face px, yaw, and any
    "no face"/unusable flag, plus a BIO marker.
  - **Set BIO** (make a reference the active identity; disabled if unusable or
    already the BIO), **→ gallery** (add to the identity gallery under a chosen
    view), and **delete**.
- **Advanced · body**:
  - Saved **body-type library**: click to make a body active, delete a body,
    active one is marked.
  - Optional body-shape reference image upload (with remove).
  - Figure-text field driving body proportions.
  - **Generate body reference**, then preview → **save as a named body type**
    (which becomes active) or **discard**.
- **Advanced · parts**:
  - Per body/identity part: enable/disable checkbox and editable text (saved on
    blur); identity / load-bearing markers and notes shown.
  - **Reset to defaults** (confirmed).

## Calibrate tab (lock identity consistency)

A three-step character-origin flow:

- **Step 1 — seed**: upload a base/seed face image (setting the calibration seed,
  which does *not* change the BIO identity); edit bio text; shows seed name and
  seed face metrics (px, pose class, yaw).
- **Step 2 — generate & approve**:
  - Choose how many faces to generate (1–12) and **generate faces**.
  - Candidate cards show running stage/angle, errors, or the finished face with
    angle, face px and yaw.
  - Click faces to select them; **add N to fingerprint** adds selected on-model
    faces to the gallery; the **identity ★** button promotes a face to the
    primary identity reference.
- **Step 3 — lock**:
  - Shows fingerprint face count, gate threshold, and gallery angle chips with yaw.
  - **Recalibrate threshold** (needs ≥3 faces) — shows resulting threshold,
    self-agreement mean/min, and face count.
  - **Reset** the fingerprint (confirmed).

## Review tab (curate & export)

- Header count of shot images.
- Collapsible **learning stats**: total shots, gate keep-rate %, approved and
  rejected counts, gold-set size; expanded view shows keep-rate broken down by
  pose and by outfit (top recipes).
- **Export gold set** (writes approved shots to the LoRA dataset; gallery stays frozen).
- **Delete N rejected** images from disk (confirmed), reporting count and space freed.
- Gallery grid of shots; per image: open detail, delete (confirmed),
  **approve / reject** (the body verdict the gate can't measure), and a verdict
  dot (status color + similarity).

## Outfit designer (shared drawer)

- Slide-in drawer to build one outfit; closes via button or backdrop.
- Upload a reference outfit photo → Claude reads it and fills the description.
- Editable outfit-description text.
- **Key-detail fields** (colour, lower garment, shoes, hair, jewellery, bag,
  outerwear, belt, sunglasses, watch, hair accessory, hosiery, nails, lipstick),
  with a count of what the reference photo didn't show.
- **Attribute pickers** (occasion, style/aesthetic, fabric, silhouette,
  formality, season) plus a short "tweak" idea.
- **Enrich / write outfit** (Claude expands the idea + picks into a full
  garment-only description).
- **Generate outfit** turnaround.

## Image detail (origin modal)

Opened from any finished shot:

- Full image with **approve / reject** buttons.
- Save the image **→ wardrobe** or **→ pose ref** (named).
- Verdict chips (status, similarity, yaw, face px), gate reason, and a
  scene-model (weaker identity) notice when a moderation fallback was used.
- Metadata: model, prompt source (AI/Claude vs template), body type, seed,
  aspect, generation time, created timestamp.
- The shot brief, and the **pose used** (id + category or "not in current
  library", pose text, pose-reference image) with a **use this pose** button that
  loads it back into the shoot tab.
- The **full prompt sent**, and a list of any **sanitised** phrases
  (`was → now`).
- The **reference images used** (face / outfit / pose) and the exact order they
  were attached.

## Verdict chips (shared display)

- Reused wherever a gate result is shown: status (kept / rejected / other /
  ungated), similarity score (struck through on a pose mismatch), signed yaw in
  degrees, and face pixel size.

---

## Present but not wired into the UI

- **PoseEditor** (`src/PoseEditor.jsx`) — an interactive OpenPose-18 skeleton rig
  editor (drag joints, nudge by ±0.01, select, toggle joint visibility, grouped
  joint list). It is implemented but **not imported anywhere**, so it is not
  currently reachable in the running app.
