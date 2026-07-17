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
