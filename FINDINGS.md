# What we already measured

Carried over by hand from the previous build, which was deleted on 2026-07-17 at
the owner's instruction. **The raw data behind these numbers no longer exists** —
the calibration pairs, the sample sheets and the experiment outputs are gone. So
treat every figure here as a prior worth designing around, not as a citation you
can re-check. Where a number matters enough to bet on, re-measure it.

Kept because these are facts about *the models*, not about the deleted code, and
several of them cost weeks to learn the first time. Delete this file if you'd
rather rediscover them.

## The ones that shape this rebuild

**ArcFace similarity tracks head angle.** `corr(|yaw|, similarity) = -0.761`. A
true profile of the same woman scored ~0.45 against a frontal reference and
would auto-reject. Consequences: never score a face against a single frontal
reference, never use one flat threshold across poses, and never compare faces at
different yaws and call the difference "drift". This confound cost the previous
project three weeks, twice.

**Describing a face makes identity worse, not better.** Reciting bone structure /
pore texture / asymmetries reads as a spec to *render*, and the model renders a
plausible stranger matching the spec. Measured on sheet re-dressing:

| references + prompt | identity |
|---|---|
| reference image + terse "don't change her" prompt | **0.860** |
| reference image + long descriptive prompt | 0.834 |
| no face crop, long descriptive prompt | 0.531 |

Say what must not change. Never describe her. This is why the part editor
separates *identity* parts (which should stay terse and off by default once a
reference exists) from *scene* parts (which carry the real work).

**More references are worse.** Three face crops (front + side + 3q) scored
**0.547** against one crop's **0.811**. More references don't give the model more
identity, they give it more to blend. **Relevant to the skeleton-as-reference
plan:** a pose image would be a second or third reference, and this is the
measurement that says it might cost identity. Measure it before trusting it.

**Face pixels are not a cliff, they're a gradient.** A gate that abstains below
160px is not saying 161px is reliable. Two club shots, same pipeline, yaw within
2° of each other:

| framing | face px | identity |
|---|---|---|
| waist-up | 660 | 0.635 |
| full body | 298 | 0.450 |

Same woman, same prompt family. Face size alone moved identity by 0.185. Any
full-body shot is carrying much weaker identity signal than its number suggests.

**Text pose control does not work on nano-banana-pro/edit.** Asked for a profile,
got yaw **-1.3°**. Asked for a look-down, got **-0.6°**. Three of four pose
probes returned frontal. This is the entire reason the skeleton editor exists —
and the reason it must be verified by *measuring returned yaw*, not by reading a
similarity score. A pose control that silently does nothing still produces
high-scoring frontal images.

**Never read a similarity score before checking the yaw it came back at.** The
two findings above combine into a trap: a model that ignores your pose request
returns a frontal image, which scores *high* precisely because it's frontal. The
previous build shipped a "successful" pose experiment that was four frontal
photos.

## Numbers to re-derive, not reuse

These were calibrated against a face that no longer exists here. Recorded for
order-of-magnitude only:

- **0.326** — stranger ceiling. Two unrelated faces scored at or below this.
- **0.431** — "is this a stranger?", from 595 human-verified pairs. **Too
  permissive to gate on**: a shot at 0.450 passed it and read as a different
  woman to the eye. If you calibrate a threshold this way again, do not reuse it
  as a quality bar.
- **0.80 / 0.76 / 0.65** — per-pose "is this good?" floors (front / 3q / side).
  Per-pose, never flat — see the yaw confound.
- **~0.888** — how well one woman's own curated sheets agree front-to-front. A
  practical ceiling: nothing generated beat how much her references agreed with
  each other.

## Scenes don't break identity. Briefs do.

The most useful measurement this project has. Same stadium, same crowd, same
floodlights, same references, same generator — only the brief changed:

| brief | similarity | |
|---|---|---|
| mid-shout, off-frontal, backlit, small face | **0.550** | REJECTED |
| the same, generated in ChatGPT instead | 0.558 | tied — the tool is not the variable |
| **quiet beat: mouth closed, near-frontal, close framing, face lit** | **0.817** | KEPT |
| *studio close-up, no scene at all* | *0.813* | |

**0.817 in a packed night stadium beats the studio close-up.** The location, the
crowd and the floodlights cost nothing. Removing four confounds bought back
**0.267** — larger than the gap between any two generators we tested.

The four, each independently measured elsewhere in this file:

1. **Off-frontal** — corr(|yaw|, sim) = -0.761.
2. **Small face** — same woman, same yaw: 660px scored 0.635, 298px scored 0.450.
3. **Backlight** — floodlights behind, eye sockets in shadow, which is where
   ArcFace reads identity.
4. **Extreme expression** — a mouth wide open mid-shout deforms the geometry the
   embedding is built on.

Stack all four and you get ~0.55 from *every* generator, including ChatGPT.
That is not a pipeline failure, it is four known confounds compounding.

**So: write briefs that let the gate see her.** Face toward the camera-ish,
framed close enough for a 350px+ face, lit on the face rather than behind it,
and not mid-scream. A hard shot is not forbidden — just expect the number to
fall and don't read it as drift.

⚠ **The gate is blind to her body.** ArcFace embeds a face crop. The 0.558
ChatGPT stadium shot has a visibly inflated bust versus her references —
spherical and lifted, the exact default `body.bust` pushes back on — and scored
the same as ours. Body drift is a human judgement, by design and by necessity.

## Which generator holds her — measured 2026-07-17, THIS project

One face reference (`Kiara.png`, 429px frontal), the same close-up prompt, every
result scored against the same 5-angle gallery. Every row is a fair comparison:
yaw deltas 0.3-4.2, faces 300-600px, no confound to explain any of it away.

| generator | similarity | |
|---|---|---|
| **openai/gpt-image-2/edit** | **0.813** | **above her own sheets** |
| *her own ChatGPT reference sheets* | *0.797* | *the bar* |
| fal-ai/ideogram/character | 0.750 | |
| FLUX LoRA @1000, 52 real refs | 0.742 | |
| fal-ai/flux-pulid | 0.713 | |
| fal-ai/nano-banana-pro/edit | 0.678 | |
| fal-ai/gpt-image-1/edit, medium | 0.591 | |
| fal-ai/instant-character | 0.485 | below the stranger floor |
| fal-ai/gpt-image-1/edit, high | 0.466 | below the stranger floor |

**gpt-image-2 holds her better than her own references agree with each other.**
Identity transfer is, for frontal close-ups, solved. Use it.

Notes that cost something to learn:

- **gpt-image-1 is not gpt-image-2.** The 0.47-0.59 rows above led to a
  confident, wrong conclusion — that ChatGPT's consistency came from its
  conversation context and could not be scripted. It was just the old model.
  If a model name has a version number, check the version before theorising.
- **`quality: high` scored WORSE than `medium`** on gpt-image-1 (0.466 vs
  0.591). More compute went into redrawing her, not preserving her. Don't
  assume the expensive tier is the faithful one.
- **Schema differs across versions**: gpt-image-1 wants `image_size` as an enum
  (`'1024x1536'`), gpt-image-2 wants an object. The bare call — prompt +
  image_urls — is what scored 0.813.
- **`instant-character` produced a different woman** at a 599px face and 2.1
  yaw delta. Nothing to blame but the model.

⚠ **Every row above is a frontal studio close-up.** Off-frontal, full-body and
real scenes are UNMEASURED for gpt-image-2. The gap that killed the LoRA
(full body: 108px face, 43.9 off-angle, abstain) has not been tested here.

⚠ **n=1 per row.** The 0.05 spread between neighbours is inside the re-roll
variance measured this morning (four rolls of one config: 0.704-0.756). The
*tiers* are real; the exact ordering of adjacent rows is not.

## LoRA: the old finding was wrong, and why

`FINDINGS` originally carried "LoRA @4000 steps = 0.517, the worst approach".
Trained on 52 crops of real reference sheets it scored **0.742** — competitive
with the best identity-transfer model available.

The old LoRA had been trained on **the pipeline's own generations**. It learned
the drift and compounded it. The correct lesson is *"a LoRA trained on your own
output is worthless"*, not *"LoRA is worthless"*.

Its failure mode was predicted before the run, from the training set alone: 63%
frontal, **zero** body images (the body sheets' faces are 24-66px, under even a
relaxed 100px training floor). Result: close-up 0.742, full body 0.522/abstain.
It learned her face and knows nothing about her body.

## Approach comparison (previous project, its own measurement)

| approach | front-to-front | floor |
|---|---|---|
| turnaround sheets, 4 views in ONE generation | **0.854** | 0.583 |
| reference conditioning, shot-by-shot | 0.564 | 0.315 |
| LoRA @ 4000 steps | 0.517 | 0.401 |

The sheets won because four views resolved in one forward pass share one latent
commitment to bone structure — drift becomes structurally impossible rather than
detectable afterward. If this rebuild generates shots independently, expect the
0.564 column.

**Portrait → sheet transfer ceilings around 0.756.** Four attempts from a single
frontal portrait scored 0.756 / 0.704 / 0.713 / 0.715. That spread is too tight
to be a tail — re-rolling buys the same number again. A single frontal portrait
is a weak anchor: it carries no body, and it can only ever verify one of three
panels.

## Infrastructure

- 8GB RTX 5070 Laptop. Cannot run FLUX.2 (32B) or klein 4B (~13GB). **Local
  inference is off the table** — everything goes through hosted APIs.
- fal.ai. `fal-ai/nano-banana-pro` (text→image), `fal-ai/nano-banana-pro/edit`
  (image refs → image). `/edit` takes a separate `system_prompt` field.
- ⚠ The fal key in `.env` is **admin-scoped**. Rotate it to a plain API key.
  Generated images land on public, unauthenticated `v3b.fal.media` URLs.
- Python **3.11** (`.venv-win`), not 3.14 — no onnxruntime wheels on 3.14.
