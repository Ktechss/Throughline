"""No image reaches the model without the prompt saying what it is for.

This is the rule the project keeps breaking, and it is expensive every time —
an unexplained image does not get ignored, it gets BLENDED:

    body reference, unlabelled   0.7838 -> 0.1473   (a stranger)
    scene, two unnamed outfits   9 faces in frame, Kiara 0.5093 rejected

_copy_body_from's docstring already states it — an unlabelled body image "has no
role line for it, so nothing tells the model whose face to ignore" — and the
shot path shipped exactly that anyway. Hence a test rather than a sentence.

These exercise the real composer against the real characters, because the
composer's job IS to agree with what the pickers spent. Nothing generates.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import main  # noqa: E402


def _chars() -> list[str]:
    try:
        return [c["id"] for c in main.db.chars_all()]
    except Exception:                                   # noqa: BLE001
        return []


CHARS = _chars()
PAIR = [c for c in ("kiara", "soni-singh") if c in CHARS]
needs_pair = pytest.mark.skipif(len(PAIR) < 2,
                                reason="needs two characters with references")


def image_tags(ledger) -> list[str]:
    return [l["tag"] for l in ledger if l.get("mode") == "image" and l.get("tag")]


def outfits_for(cids):
    """A real saved outfit per character, or skip — this is data, not a fixture.

    Files only, and no dot-entries: the wardrobe directory also holds an
    `.outfitcrops` cache, and globbing "*.*" happily returned that as an outfit.
    """
    out = {}
    for cid in cids:
        d = main.config.char_base(cid) / "wardrobe"
        if not d.exists():
            continue
        names = sorted(p.stem for p in d.iterdir()
                       if p.is_file() and not p.name.startswith("."))
        if names:
            out[cid] = names[0]
    return out


# ------------------------------------------------------------------ the rule

@needs_pair
def test_every_attached_image_is_named_in_the_prompt():
    req = main.SceneReq(prompt=f"@{PAIR[0]} and @{PAIR[1]} at a bar",
                        wardrobe=outfits_for(PAIR))
    s = main._build_scene(req)
    missing = [t for t in image_tags(s["ledger"]) if t not in s["prompt"]]
    assert not missing, f"attached but never named: {missing}"


@needs_pair
def test_prompt_override_cannot_drop_the_role_lines():
    """The documented happy path is a verbatim draft. It used to discard every
    role line, the distinctness clause and the crowd constraint while the
    references stayed attached — which is how a nightclub scene got nine faces."""
    o = outfits_for(PAIR)
    req = main.SceneReq(
        prompt=f"@{PAIR[0]} and @{PAIR[1]} at a bar", wardrobe=o,
        # a draft that names ONLY the first face, as a real one did
        prompt_override="@image1 stands at a bar counter, warm light.")
    s = main._build_scene(req)
    missing = [t for t in image_tags(s["ledger"]) if t not in s["prompt"]]
    assert not missing, f"override dropped the role lines for: {missing}"


@needs_pair
def test_distinctness_and_crowd_clauses_survive_an_override():
    req = main.SceneReq(prompt=f"@{PAIR[0]} and @{PAIR[1]} at a bar",
                        prompt_override="@image1 and @image2 at a bar.")
    s = main._build_scene(req)
    assert "DIFFERENT women" in s["prompt"]
    assert "No other faces" in s["prompt"]


@needs_pair
def test_allow_crowd_is_the_only_way_to_get_a_crowd():
    base = dict(prompt=f"@{PAIR[0]} and @{PAIR[1]} at a bar")
    off = main._build_scene(main.SceneReq(**base, allow_crowd=False))["prompt"]
    on = main._build_scene(main.SceneReq(**base, allow_crowd=True))["prompt"]
    assert "No other faces" in off
    assert "No other faces" not in on


# --------------------------------------------------------------- the budget

@needs_pair
def test_outfits_are_symmetric_across_the_cast():
    """Charging outfits against a running count walked the cast in order, so the
    first woman kept her dress and the second silently lost hers. Reported from
    the UI as "I chose the image from Soni's wardrobe but it did not take"."""
    o = outfits_for(PAIR)
    if len(o) < 2:
        pytest.skip("both characters need a saved outfit")
    s = main._build_scene(main.SceneReq(
        prompt=f"@{PAIR[0]} and @{PAIR[1]} shopping", wardrobe=o))
    modes = {l["key"]: l["mode"] for l in s["ledger"] if l["kind"] == "outfit"}
    assert len(set(modes.values())) == 1, (
        f"one outfit got a slot and the other did not: {modes}")


@needs_pair
def test_reference_count_stays_bounded():
    """2 refs 0.622, 3 refs 0.579. A two-hander with outfits and manicures on
    both once reached five."""
    o = outfits_for(PAIR)
    s = main._build_scene(main.SceneReq(
        prompt=f"@{PAIR[0]} and @{PAIR[1]} out", wardrobe=o,
        nails={PAIR[0]: "nail5"}))
    assert len(s["refs"]) <= 2 * len(PAIR), (
        f"{len(s['refs'])} references for a cast of {len(PAIR)}")


@needs_pair
def test_nothing_demoted_disappears():
    """A demotion is only a demotion if the text actually goes; otherwise it
    quietly means dropped."""
    o = outfits_for(PAIR)
    s = main._build_scene(main.SceneReq(
        prompt=f"@{PAIR[0]} and @{PAIR[1]} out", wardrobe=o,
        nails={PAIR[0]: "nail5"}))
    for l in s["ledger"]:
        if l["mode"] == "text":
            assert l["tag"] is None
            assert l.get("label"), "a demoted item must still say what it was"


# -------------------------------------------------------- the brief's share

@pytest.mark.skipif(not CHARS, reason="needs a character")
def test_the_brief_is_not_drowned_by_boilerplate():
    """A street brief came out 4,517 characters with 3,631 of wardrobe and
    grooming — 80% — and the scene it described never rendered."""
    cid = PAIR[0] if PAIR else CHARS[0]
    main.config.set_active(cid)
    brief = ("walking along a residential street near a park on a cloudy day, "
             "families and children blurred behind her")
    text, _ = main.promptlib.compose_tagged(brief, build_text="", shot_type="candid")
    assert len(brief) / max(len(text), 1) > 0.15, (
        f"brief is {100 * len(brief) // len(text)}% of a {len(text)}-char prompt")
