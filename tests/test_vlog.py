"""A vlog plan must be honest about money and about which half can fail.

Three things here are load-bearing and none of them is obvious from the code:

1. THE PLAN IS PRICED BEFORE IT IS SPENT, and the price says what it does not
   know. Video prices are unpublished — providers.py says "Read credits_amount
   off the status response; do not assume", and poyo's own page was wrong by
   2.5x. So an estimate with no measured clip behind it reports the STILLS ONLY
   and flags itself incomplete. A total that silently invents the expensive half
   is worse than no total, because that half is what decides affordability.

2. FRONT AND BACK ARE NOT THE SAME KIND OF SPEND. A front beat has her in it,
   so its still has to clear the gate and can fail. A back beat is a photograph
   of a street — there is no face to score, the same reasoning that makes a
   wardrobe turnaround gated=False. Confusing the two would either gate a
   picture of a pavement or let an unverified face through.

3. THE SHAPES AND THE BEATS ARE TWO HAND-MAINTAINED DICTS. This project has
   been bitten by exactly that before (see test_body_axes.py, which exists
   because a preset and a ladder drifted apart). A shape naming a beat that does
   not exist would silently render a shorter vlog than the owner planned.
"""
from __future__ import annotations

import subprocess

import pytest

from backend import vlog, vlog_data


# ---------------------------------------------------------------- vocabulary
def test_every_shape_names_real_beats():
    """The two-dicts trap, closed. A missing id is dropped silently by
    vlog_data.shape(), so without this the vlog just comes out short."""
    known = {b["id"] for b in vlog_data.all_beats()}
    for name, spec in vlog_data.SHAPES.items():
        missing = [b for b in spec["beats"] if b not in known]
        assert not missing, f"shape {name!r} names unknown beats: {missing}"


@pytest.mark.parametrize("name", list(vlog_data.SHAPES))
def test_a_shape_resolves_to_the_beats_it_lists(name):
    assert len(vlog_data.shape(name)) == len(vlog_data.SHAPES[name]["beats"])


def test_a_vlog_cuts_between_the_two_cameras():
    """All talking heads is not a vlog; all b-roll has no author. Every shipped
    shape must contain both."""
    for name in vlog_data.SHAPES:
        cams = {b["camera"] for b in vlog_data.shape(name)}
        assert cams == {"front", "back"}, f"{name} only has {cams}"


def test_every_beat_declares_both_halves_of_its_spend():
    """A beat is a still AND a clip. One without the other is unbuildable."""
    for b in vlog_data.all_beats():
        assert b["still"].strip(), f"{b['id']} has no still"
        assert b["motion"].strip(), f"{b['id']} has no motion"
        assert b["camera"] in ("front", "back"), b["id"]
        assert isinstance(b["subject"], bool), b["id"]
        assert b["seconds"] > 0, b["id"]


def test_no_beat_describes_her():
    """The measured rule the whole project rests on: reference plus terse prompt
    0.860, description alone 0.531. These strings say what the CAMERA does; her
    face comes from the reference, and a beat that describes it would specify a
    type rather than a person."""
    banned = ("her eyes are", "almond", "cheekbone", "jawline", "complexion",
              "skin tone", "her nose", "her lips are", "years old", "ethnicity")
    for b in vlog_data.all_beats():
        blob = (b["still"] + " " + b["motion"]).lower()
        hit = [w for w in banned if w in blob]
        assert not hit, f"{b['id']} describes her: {hit}"


# --------------------------------------------------------------------- plan
def test_front_beats_are_gated_and_back_beats_are_not():
    """The distinction the whole design turns on."""
    for s in vlog.plan("walk"):
        assert s["gated"] == (s["camera"] == "front"), s
        assert s["gated"] == s["subject"], s


def test_every_beat_is_vertical():
    """No kie video model takes an aspect ratio, so the clip is the shape of its
    start frame. Vertical is decided here or not at all."""
    assert vlog.ASPECT == "9:16"
    assert all(s["aspect"] == "9:16" for s in vlog.plan("cafe"))


def test_the_place_rides_on_the_still_not_the_motion():
    """The video model is animating a frame that already contains the street.
    Telling it about a location it can see is how a clip grows a second one."""
    shots = vlog.plan("walk", place="a busy street in Pune")
    assert any("Pune" in s["needs_still"] for s in shots)
    assert not any("Pune" in s["motion"] for s in shots)


def test_an_explicit_beat_list_keeps_its_order():
    ids = ["reaction-face", "street-ahead", "walk-and-talk"]
    assert [s["id"] for s in vlog.plan(None, ids)] == ids


def test_an_empty_plan_is_empty_rather_than_a_default():
    assert vlog.plan(None, []) == []
    assert vlog.plan("no-such-shape") == []


# ----------------------------------------------------------------- estimate
def test_an_estimate_with_no_measured_clip_is_marked_incomplete():
    """THE MONEY INVARIANT. With no clip ever run, total_usd is the stills only
    and `complete` is False. If this ever reports complete=True off zero
    samples, someone has started guessing at the expensive half."""
    e = vlog.estimate(vlog.plan("quick"))
    if e["clip_samples"] == 0:
        assert e["clip_usd_each"] is None
        assert e["clips_usd"] is None
        assert e["complete"] is False
        assert e["total_usd"] == e["stills_usd"], (
            "with no measured clip cost the total must be the stills alone")


def test_the_estimate_counts_both_spends_per_beat():
    shots = vlog.plan("walk")
    e = vlog.estimate(shots)
    assert e["stills"] == len(shots)
    assert e["clips"] == len(shots)
    assert e["gated_stills"] + e["ungated_stills"] == e["stills"]
    assert e["seconds"] == sum(s["seconds"] for s in shots)


def test_the_still_price_comes_from_the_registry():
    """Not a constant in this file — the registry is the one price table."""
    assert vlog.still_cost("seedream-5-lite") == pytest.approx(0.0275)
    assert vlog.still_cost("nano-banana-pro") == pytest.approx(0.12)
    assert vlog.still_cost("no-such-model") is None


def test_a_credit_is_half_a_cent():
    """Confirmed against the ledger, not a pricing page: seedream-5-lite charged
    5.5 credits against a listed usd_4k of 0.0275, and nano-banana-pro charged
    24.0 against 0.12. Both exact."""
    assert vlog.KIE_CREDIT_USD == 0.005
    assert 5.5 * vlog.KIE_CREDIT_USD == pytest.approx(0.0275)
    assert 24.0 * vlog.KIE_CREDIT_USD == pytest.approx(0.12)


# ------------------------------------------------------------------- stitch
def _clip(path, size, rate, seconds=1):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"testsrc=size={size}:rate={rate}:duration={seconds}", str(path)],
        check=True, timeout=120)
    return path


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"),
                    reason="ffmpeg is not installed")
def test_stitch_normalises_mismatched_clips(tmp_path):
    """Clips come back from different models at whatever size and frame rate
    that model returns. The concat DEMUXER fails or produces a broken file when
    they differ, which is why stitch() re-encodes onto one canvas — including a
    LANDSCAPE input, which is the case that would otherwise ruin a vertical cut.
    """
    clips = [_clip(tmp_path / "a.mp4", "540x960", 30),
             _clip(tmp_path / "b.mp4", "360x640", 24),
             _clip(tmp_path / "c.mp4", "960x540", 25)]     # landscape
    out = vlog.stitch(clips, tmp_path / "joined.mp4", width=540, height=960)
    assert out.is_file() and out.stat().st_size > 0

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, timeout=120)
    assert probe.stdout.strip().startswith("540,960"), probe.stdout


def test_stitch_refuses_a_missing_clip(tmp_path):
    with pytest.raises(RuntimeError) as e:
        vlog.stitch([tmp_path / "gone.mp4"], tmp_path / "out.mp4")
    assert "not on disk" in str(e.value)


def test_stitch_refuses_nothing(tmp_path):
    with pytest.raises(RuntimeError):
        vlog.stitch([], tmp_path / "out.mp4")
