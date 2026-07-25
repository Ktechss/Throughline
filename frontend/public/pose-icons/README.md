# Pose icons (optional)

Drop SVG (or PNG, if you rename the code to look for `.png`) icons here and the
pose picker uses them automatically, falling back to the built-in line
silhouettes when a file is missing.

Two levels — the picker tries them in this order per pose:

1. **Per-pose** — `<poseId>.svg` (most specific), e.g. `hip-pop.svg`, `walking.svg`,
   `seated-crossed.svg`. Pose ids are the labels shown on the cards.
2. **Per-stance** — one icon covers a whole stance type. Filenames:

   `portrait.svg` `stand.svg` `walk.svg` `hip.svg` `cross.svg` `reach.svg`
   `lean.svg` `back.svg` `selfie.svg` `sit.svg` `floor.svg` `kneel.svg`
   `crouch.svg` `recline.svg`

Start with the 14 per-stance icons — that covers every pose. Add per-pose files
later only where you want finer detail.

Icons are rendered as **white silhouettes** (a `brightness(0) invert(1)` filter in
`PoseIcon.jsx`) so they read on the dark theme — so monochrome / lineal icons
work best. Using coloured icons? Remove that `style={{ filter: ... }}` line.

## Licensing

These are YOUR assets to add under their own license. Flaticon's free icons
require attribution — if you use them, keep the required credit (e.g. in an
About/credits page). Or use a permissive set (MIT / CC0) to avoid attribution.
