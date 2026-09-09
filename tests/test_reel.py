"""A reel pipeline must know its own dependency order, and admit what it cannot do.

TWO THINGS THIS PINS.

1. VOICE COMES BEFORE LIPSYNC. The first vlog rendered audio LAST, laid over a
   finished cut. That works right up until you want lipsync, which consumes the
   audio to make the clip — so a pipeline with voice at the end can never grow
   that stage. The order here is the dependency order, not the order the parts
   happened to get built in.

2. BLOCKED IS NOT TODO. Todo is work waiting to be paid for. Blocked is work
   that cannot be done at all: probed against kie on 2026-09-08, every lipsync
   model (omnihuman, latentsync, wav2lip, musetalk, sync, kling, hedra, sonic,
   infinitetalk, wan-s2v, sadtalker, echomimic and more) returns 422. Folding
   the two together is how a talking-head reel ships with a still mouth.
"""
from __future__ import annotations

import json

import pytest

from backend import reel


def _script(tmp_path, scenes):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"title": "t", "character": "kiara",
                             "wardrobe": "DayOut16", "scenes": scenes}))
    return p


FRONT = {"slug": "a", "camera": "front", "seconds": 5,
         "still": "her face", "motion": "she smiles", "line": "hello there"}
BACK = {"slug": "b", "camera": "back", "seconds": 5,
        "still": "a street", "motion": "the camera walks"}


def test_lipsync_depends_on_both_the_clip_and_the_voice():
    """The invariant that forces voice to be stage 1."""
    assert set(reel.DEPENDS["lipsync"]) == {"clip", "voice"}
    assert reel.STAGES.index("voice") < reel.STAGES.index("lipsync")
    assert reel.STAGES.index("clip") < reel.STAGES.index("lipsync")


def test_only_a_talking_head_needs_lipsync(tmp_path):
    """A line over b-roll is voice-over. Lipsyncing a street would be paying to
    animate a pavement's mouth."""
    doc, scenes = reel.load(_script(tmp_path, [
        FRONT,                                   # front + line  -> yes
        {**FRONT, "slug": "c", "line": ""},      # front, silent -> no
        {**BACK, "line": "over the street"},     # back + line   -> no
        BACK,                                    # back, silent  -> no
    ]))
    assert [s.needs_lipsync for s in scenes] == [True, False, False, False]


def test_front_beats_are_gated_and_back_beats_are_not(tmp_path):
    doc, scenes = reel.load(_script(tmp_path, [FRONT, BACK]))
    assert [s.gated for s in scenes] == [True, False]


def test_lipsync_is_reported_blocked_not_merely_todo(tmp_path):
    """THE HONESTY INVARIANT. With no provider, the stage must surface as
    blocked, with the effect spelled out."""
    doc, scenes = reel.load(_script(tmp_path, [FRONT]))
    st = reel.status(doc, scenes, lipsync_available=False)
    blocked = [b for b in st["blocked"] if b["stage"] == "lipsync"]
    assert blocked, "a lipsync scene with no provider must be reported blocked"
    assert blocked[0]["scenes"] == 1
    assert "422" in blocked[0]["why"] or "not supported" in blocked[0]["why"]
    assert blocked[0]["effect"]
    assert blocked[0]["options"]


def test_nothing_is_blocked_once_a_provider_exists(tmp_path):
    doc, scenes = reel.load(_script(tmp_path, [FRONT]))
    st = reel.status(doc, scenes, lipsync_available=True)
    assert not [b for b in st["blocked"] if b["stage"] == "lipsync"]


def test_actions_come_back_in_dependency_order(tmp_path):
    doc, scenes = reel.load(_script(tmp_path, [FRONT, BACK]))
    order = [a["stage"] for a in reel.next_actions(scenes)]
    assert order.index("voice") < order.index("still")
    assert order.index("still") < order.index("clip")
    assert order.index("clip") < order.index("lipsync")


def test_scene_start_times_accumulate(tmp_path):
    doc, scenes = reel.load(_script(tmp_path, [
        {**FRONT, "seconds": 5}, {**BACK, "seconds": 4}, {**FRONT, "slug": "d", "seconds": 6}]))
    assert [s.at for s in scenes] == [0.0, 5.0, 9.0]


def test_a_malformed_scene_is_refused_with_the_field_named(tmp_path):
    with pytest.raises(reel.ReelError) as e:
        reel.load(_script(tmp_path, [{"slug": "x", "camera": "front"}]))
    assert "still" in str(e.value) and "motion" in str(e.value)


def test_an_unknown_camera_is_refused(tmp_path):
    with pytest.raises(reel.ReelError):
        reel.load(_script(tmp_path, [{**FRONT, "camera": "drone"}]))


def test_an_empty_script_is_refused(tmp_path):
    with pytest.raises(reel.ReelError):
        reel.load(_script(tmp_path, []))


def test_cost_is_a_floor_when_the_clip_price_is_unknown(tmp_path, monkeypatch):
    """Same contract as vlog.estimate: never invent the expensive half."""
    monkeypatch.setattr(reel.vlog, "measured_clip_cost",
                        lambda *a, **k: {"usd": None, "n": 0, "by_model": {}})
    doc, scenes = reel.load(_script(tmp_path, [FRONT, BACK]))
    c = reel.status(doc, scenes)["cost"]
    assert c["clips_usd"] is None and c["complete"] is False
