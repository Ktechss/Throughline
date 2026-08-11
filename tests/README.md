# Tests

    ./.venv/bin/python -m pytest tests/ -q      # ~0.4s, no generation

Nothing here calls fal, downloads a model, or spends a credit. Every assertion
is a pure-function check over the composer, so the whole suite runs before a
commit rather than after a bad image.

## Why these exist

Each case is a bug that actually shipped, and three of them were re-treads of
problems this codebase had *already* solved and written a comment about:

| shipped bug | the comment that did not stop it |
|---|---|
| `"Lipstick: soft casual clothing pink"` reached fal | `397f3ab` narrowed the same rule for product categories and left the colour |
| `/api/gallery/from-ref` changed the gallery without recalibrating | `/api/gallery/from-run` was fixed with a comment reading *"Only ADD was missing it"* |
| an unlabelled body reference replaced her face, 0.7838 → 0.1473 | `_copy_body_from`'s docstring names the hazard exactly |

A comment records a lesson. It does not enforce one. That is the whole argument
for this directory.

## What is actually asserted

**The sanitiser draws its line at exposure, not vocabulary.** `nude pink`,
`nude-toned`, `lingerie` and `swimwear` are colours and retail categories and
must survive intact; `she is nude`, `in the nude` and `topless` must not. Every
rewrite must be reported — a run once recorded `sanitised=[]` while its text was
being altered, because four call sites dropped the report into `_`.

**No image reaches the model unexplained.** Every attached reference's `@imageN`
tag must appear in the final prompt, including when a verbatim `prompt_override`
is used — that path used to discard every role line while the references stayed
attached, which is how a nightclub scene came back with nine faces.

**The budget is symmetric.** Charging outfits against a running count walked the
cast in order, so the first woman kept her dress and the second silently lost
hers. Reported from the UI as *"I chose the image from Soni's wardrobe but it did
not take"*.

**The brief is not drowned.** A street brief once came out 4,517 characters with
3,631 of wardrobe and grooming boilerplate — 80% — and the scene it described
never rendered.

## These have teeth

Verified against the pre-fix source rather than assumed:

    pre-fix sanitiser   'soft nude pink lipstick' -> 'soft casual clothing pink lipstick'   test FAILS
    pre-fix budget      {'kiara': 'image', 'soni-singh': 'text'}                            test FAILS

## Data dependency

`test_reference_invariants.py` runs the real composer against the real
characters, because the composer's job *is* to agree with what the pickers spent.
It skips itself when fewer than two characters have references, so a fresh
checkout is not a failure.
