"""The realism doctrine must actually reach the model.

Every case here is a bug that shipped 607 times before it was noticed, which is
what makes this file worth more than the comments it defends. `prompt.py` argued
for its camera and skin rules at length, marked them `critical=True` so the UI
warns before you switch them off, and never once put them in a prompt —
`compose_tagged` pulled only the `body` and `grooming` sections out of the part
tree. Measured across the whole run history on 2026-08-24:

    "sensor noise"                 0 runs      (camera.body)
    "no bokeh"                     0 runs      (constraints.main)
    "never a professional camera"  0 runs      (camera.body)
    "not a model on a shoot"       0 runs      (subject.energy)
    flaws set                      0 runs
    camera_holder set              7 runs

    "85mm"                        51 runs      <- what filled the vacuum
    "shallow depth"               40 runs

A comment records a lesson. These enforce one.

Nothing here calls a provider, loads ONNX or touches the gate — pure functions
over the composer and the inference, so they run in a second.
"""
from __future__ import annotations

from backend import prompt as promptlib
from backend.main import _infer_capture, _is_selfie_pose


def _parts():
    """The default part tree, so this does not depend on a character's edits."""
    return promptlib.default_parts()


# ── the doctrine reaches the prompt ──────────────────────────────────────────

def test_capture_clause_carries_the_camera_and_the_constraints():
    text = promptlib.capture_clause(_parts())
    for phrase in ("sensor noise", "no bokeh", "never a professional camera",
                   "not a model on a shoot", "peach fuzz"):
        assert phrase.lower() in text.lower(), f"{phrase!r} missing from capture_clause"


def test_compose_tagged_ships_the_capture_clause():
    cap = promptlib.capture_clause(_parts())
    text, _ = promptlib.compose_tagged("in a cafe", capture_text=cap)
    assert "no bokeh" in text
    assert "never a professional camera" in text.lower()


def test_capture_clause_respects_disabled_parts():
    """The checkboxes stay real — a disabled part must not ship anyway."""
    parts = [p for p in _parts() if p.id != "camera.body"]
    assert "24mm" not in promptlib.capture_clause(parts)


def test_capture_clause_drops_identity_parts():
    """skin.tone describes her and is identity=True; a reference carries that.

    Same rule compose() applies, for the same measured reason: describing her
    scored 0.531 against 0.860 for a terse lock.
    """
    text = promptlib.capture_clause(_parts())
    tone = next(p for p in _parts() if p.id == "skin.tone")
    assert tone.identity, "precondition: skin.tone is an identity part"
    assert tone.text not in text


def test_flaws_land_after_the_realism_line():
    """A contradiction is resolved by whichever the model read last.

    "crisp focus on the eyes" and "mild motion blur" cannot both hold, and the
    flaw is the one that was asked for.
    """
    text, _ = promptlib.compose_tagged("in a bar", flaws="snapshot")
    assert text.index("motion blur") > text.index("Crisp focus on the eyes")


# ── the knobs are reached at all ─────────────────────────────────────────────

def test_wake_up_brief_infers_every_axis():
    """Run 15e2298957: the brief asked for a selfie and an imperfect one, and
    every selfie rule in the pipeline sat the shot out because no pose was
    picked."""
    brief = ("she just woke up yawning she still in her bed took her phone and "
             "captured imperfect selfie to post it to instagram.")
    holder, flaws, optics, groom, notes = _infer_capture(brief, None, "", "")
    assert holder == "selfie"
    assert flaws == "subtle"
    assert optics == "phone-front"
    assert groom == "just-woken"
    assert notes, "an inference must say that it happened"


def test_explicit_values_always_win():
    brief = "imperfect selfie"
    holder, flaws, optics, groom, _ = _infer_capture(
        brief, None, "friend", "snapshot", "portrait", "end-of-day")
    assert (holder, flaws, optics, groom) == (
        "friend", "snapshot", "portrait", "end-of-day")


def test_a_studio_brief_keeps_its_professional_optics():
    """The phone default must not overrule a brief that asked for a studio."""
    _, _, optics, _, _ = _infer_capture(
        "photo shoot in the studio, dark and light room effect", None, "", "")
    assert optics == "", "a studio brief must not be forced onto phone optics"


def test_editorial_register_also_stands_down():
    _, _, optics, _, _ = _infer_capture(
        "on a rooftop at dusk", None, "", "", shot_type="editorial")
    assert optics == ""


# ── every selfie category is a selfie ────────────────────────────────────────

def test_all_three_selfie_groups_are_selfies():
    """This tested "Selfie (Handheld)" alone, so the 50 car and 25 mirror poses
    got the 600-char outfit cap meant for a photograph someone else took."""
    for group in ("Selfie (Handheld)", "Selfie (Mirror)", "Selfie (Car)"):
        pose_id = next(iter(promptlib.POSE_GROUPS[group]))
        assert _is_selfie_pose(pose_id), f"{group} not recognised as a selfie"


def test_a_brief_alone_can_make_it_a_selfie():
    assert _is_selfie_pose(None, "taking a selfie on the balcony")
    assert _is_selfie_pose(None, "selfi in a car")      # the typo people type
    assert not _is_selfie_pose(None, "walking through the market")


# ── the vocabulary is well-formed ────────────────────────────────────────────

def test_new_vocabularies_have_an_empty_default():
    """"" must exist and emit nothing, or an unset picker changes the prompt."""
    for table in (promptlib.OPTICS, promptlib.EXPOSURE, promptlib.GROOMING_STATE):
        assert "" in table
        assert table[""]["text"] == ""


def test_grooming_state_that_costs_similarity_says_so():
    """just-woken moves the landmarks ArcFace reads. A low score there is the
    intended outcome, and the row has to know that before it is read as drift."""
    assert promptlib.GROOMING_STATE["just-woken"]["expected_low"] is True
