"""A scene must read the camera out of its brief, the way a shot does.

THE BUG. A night-club brief that said "selfie" in plain words rendered as a
third-person photograph OF two women taking a selfie — one frame with the phone
visible in shot, one framed head-to-shoes at a reach no arm has. Both prompts
described the ACT of taking a selfie ("holding her phone up to take a selfie",
"sits at the front of a small nightclub table taking a phone selfie") and never
said where the lens was.

WHY IT HAPPENED. `_infer_capture` reads the camera holder out of a brief and has
since it was written, but only the shot path called it. `holder` is wired into
the Collaborate page and was left unset — the norm, not the exception: measured
over the first 607 runs it was set 7 times. So CAMERA_HOLDERS' selfie entry, the
only place in the project that says where the lens actually is, never loaded.

These tests pin the two halves of the fix: the inference now runs on the scene
path, and the AI-prompt path — which throws the assembled prose away and asks
Claude to write the prompt — is handed the camera position as a requirement
rather than losing it.
"""
from __future__ import annotations

import pytest

from backend import prompt as promptlib
from backend.main import SceneReq, _build_scene


SELFIE_BRIEF = ("@kiara and @vamika are a night club in pune l7 club it is not a "
                "clear picture but a glared on since it is taken from phone both "
                "looking at camera @kiara is taking selfie")


def _scene(**kw):
    return _build_scene(SceneReq(**kw))


def test_selfie_in_the_brief_sets_the_camera_holder():
    """The whole bug in one line: nobody touches the picker, so the brief has
    to carry it."""
    s = _scene(prompt=SELFIE_BRIEF)
    assert s["capture"]["holder"] == "selfie", s["capture"]


def test_an_arms_length_selfie_is_not_a_full_body_frame():
    """The second failure: no framing picked, so it came back head-to-shoes."""
    s = _scene(prompt=SELFIE_BRIEF)
    assert s["capture"]["framing"] == "chest_up", s["capture"]


def test_an_explicit_choice_still_wins():
    """A floor, never a ceiling. If the owner asks for full body, they get it —
    this must not become the framing override that was deliberately removed on
    2026-08-02."""
    s = _scene(prompt=SELFIE_BRIEF, framing="full_body", holder="stranger")
    assert s["capture"]["framing"] == "full_body"
    assert s["capture"]["holder"] == "stranger"


def test_a_non_selfie_brief_is_left_alone():
    """The inference must not decide every scene is a selfie."""
    s = _scene(prompt="@kiara walks through a Pune market in the afternoon")
    assert s["capture"]["holder"] != "selfie"
    assert s["capture"]["framing"] == ""


def test_the_assembled_prompt_says_where_the_lens_is():
    """CAMERA_HOLDERS' text is the payload; reaching it is the point."""
    s = _scene(prompt=SELFIE_BRIEF)
    a = s["assembled"].lower()
    assert "front camera" in a
    assert "phone itself is not in the picture" in a, (
        "the selfie holder must state the POV — the mirror entry always did "
        "('the real camera is not in the frame') and the selfie entry did not, "
        "which is why the model drew someone holding a phone")


def test_the_selfie_holder_rules_out_photographing_the_act():
    """Not a scene test — a data test. This sentence is the fix; if someone
    trims it, both call sites silently regress."""
    txt = promptlib.CAMERA_HOLDERS["selfie"]["text"].lower()
    assert "not" in txt and "phone itself" in txt
    assert "frame is what that front camera sees" in txt


def test_every_inference_is_reported():
    """'Whatever is inferred is recorded so the run says what it did rather than
    doing it invisibly' — the doctrine _infer_capture was written under."""
    s = _scene(prompt=SELFIE_BRIEF)
    joined = " ".join(s["capture_notes"])
    assert "camera_holder=selfie" in joined
    assert "framing=chest_up" in joined


@pytest.mark.parametrize("brief,expect", [
    ("@kiara takes a selfie on the rooftop", "selfie"),
    ("@kiara in a mirror selfie in her bedroom", "mirror"),
    ("@kiara photographed by a friend at dinner", ""),
])
def test_the_brief_decides(brief, expect):
    s = _scene(prompt=brief)
    assert s["capture"]["holder"] == expect, (brief, s["capture"])
