"""The rules this project keeps re-learning, written down where they can fail.

Every case here is a bug that actually shipped. Three of them were re-treads of
problems the codebase had already solved and documented in a comment — which is
the point: a comment records a lesson, it does not enforce one.

    "casual clothing"   397f3ab narrowed the rule for product CATEGORIES and left
                        the colour, so a saree's styling reached fal as
                        "Lipstick: soft casual clothing pink"
    recalibration       /api/gallery/from-run was fixed with a comment reading
                        "Only ADD was missing it"; /api/gallery/from-ref still
                        changed the gallery without re-deriving its floor
    unlabelled refs     _copy_body_from's docstring names the hazard exactly, and
                        it was live on the shot path regardless: 0.7838 -> 0.1473

Nothing here calls fal, loads a model, or touches the gate's ONNX runtime. These
are pure-function checks over the composer, so they run in a second and can be
run before every commit.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import prompt as promptlib  # noqa: E402


# ---------------------------------------------------------------- sanitiser
#
# The line the sanitiser is drawing is EXPOSURE, not vocabulary. A word that
# names a colour, a fabric or a retail category is not an undress cue, and
# rewriting it corrupts text the user wrote and never sees again.

@pytest.mark.parametrize("text", [
    "soft nude pink lipstick",
    "blush-nude satin footbed",
    "a nude manicure",
    "nude-toned heels",
    "nude lace bodysuit",
    # the categories 397f3ab restored — regression guard, these must stay whole
    "Studio catalogue photograph for a lingerie brand campaign.",
    "swimwear editorial",
    "a underwear advertisement",
    "loungewear set",
])
def test_sanitise_leaves_colours_and_categories_alone(text):
    out, changes = promptlib.sanitise(text)
    assert out == text, f"rewrote {text!r} -> {out!r}"
    assert changes == []


@pytest.mark.parametrize("text", [
    "she is nude",
    "she was completely nude",
    "they are nude",
    "posing nude on the bed",
    "in the nude",
    "a nude photoshoot",
    "a nude photo",
    "topless",
    "naked",
    "bare-chested",
])
def test_sanitise_still_guards_undress(text):
    out, changes = promptlib.sanitise(text)
    assert "casual clothing" in out, f"undress cue survived: {text!r} -> {out!r}"
    assert changes, "a rewrite happened but was not reported"


def test_sanitise_keeps_the_verb():
    """"she is nude" must not become "she wearing casual clothing"."""
    out, _ = promptlib.sanitise("she is nude")
    assert out == "she is wearing casual clothing"


def test_sanitise_reports_every_change():
    """Silent rewriting is the failure mode, not rewriting itself.

    A real run recorded sanitised=[] while its text was being altered, because
    four call sites dropped the report into `_`.
    """
    out, changes = promptlib.sanitise("a topless naked shot")
    assert out != "a topless naked shot"
    assert len(changes) >= 2
    assert all({"was", "now", "why"} <= set(c) for c in changes)


def test_sanitise_is_idempotent():
    """Sanitising twice must not compound. 'a full a full chest' shipped once."""
    once, _ = promptlib.sanitise("she is nude and topless, seductive mood")
    twice, _ = promptlib.sanitise(once)
    assert once == twice


# ------------------------------------------------------------ identity lock
#
# Words cannot specify a person, they specify a TYPE. Measured: reference +
# terse 0.860, reference + description 0.834, description alone 0.531.

def test_reference_drops_every_identity_part():
    parts = promptlib.default_parts()
    with_ref = promptlib.compose(parts, has_reference=True)
    ident = [p for p in parts if p.identity and p.enabled]
    assert ident, "fixture is wrong: no identity parts to drop"
    for p in ident:
        assert p.text not in with_ref, (
            f"identity part {p.id!r} survived into a referenced prompt")


def test_no_reference_keeps_the_description():
    parts = promptlib.default_parts()
    without = promptlib.compose(parts, has_reference=False)
    ident = [p for p in parts if p.identity and p.enabled]
    assert any(p.text in without for p in ident), (
        "with no reference the description is all there is — it must survive")


# ------------------------------------------------------------- body defaults
#
# The build picker writes body.frame; these defaults sit underneath it. When
# they carried damping negations they contradicted the picker on every shot.

@pytest.mark.parametrize("part_id,forbidden", [
    ("body.bust", ["not exaggerated", "not lifted"]),
    ("body.waist", ["not cinched", "NOT cinched", "not corseted"]),
])
def test_body_defaults_carry_no_size_damping(part_id, forbidden):
    part = next(p for p in promptlib.default_parts() if p.id == part_id)
    for phrase in forbidden:
        assert phrase.lower() not in part.text.lower(), (
            f"{part_id} still damps size with {phrase!r}: {part.text!r}")
