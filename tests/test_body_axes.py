"""The silhouette, the sentence and the bio must all read the same rung.

The body builder makes a promise the rest of the app has to keep: the figure
you drag is the figure that gets written. It broke immediately, twice, in ways
no existing test could see — both were agreements between two hand-maintained
dicts, and nothing compared them.

  1. A preset wrote only bust/waist/hips, while the silhouette DREW all six
     axes from BUILD_AXIS_DEFAULTS. So thighs, leg length and shoulders were
     drawn from the preset and written from prompt.py's defaults. Four of the
     five presets diverged; only "curvy" agreed, and only by coincidence.
  2. The Fine-tune panel showed BODY_AXES text while creation wrote
     _BUILD_PARTS text. Eight of fifteen cells had already drifted, so the
     sentence labelled verbatim was not the sentence stored.

Both are now derived from one ladder. These tests exist so a future edit that
reintroduces a second source fails here rather than in someone's bio.
"""
from __future__ import annotations

import pytest

from backend.main import (BODY_AXES, BUILD_AXIS_DEFAULTS, BUILDS,
                          _body_axis_parts, _build_axes)
from backend import prompt as promptlib


def test_every_build_word_has_a_ladder_position():
    """A build the picker offers but the ladder cannot place would silently
    fall back to defaults — which is bug 1 in a new costume."""
    assert set(BUILDS) == set(BUILD_AXIS_DEFAULTS), (
        f"offered {sorted(BUILDS)} but placed {sorted(BUILD_AXIS_DEFAULTS)}")


@pytest.mark.parametrize("build", BUILDS)
def test_a_preset_places_every_axis(build):
    """Any axis a preset omits is one the silhouette draws and the bio does not
    record."""
    missing = set(BODY_AXES) - set(BUILD_AXIS_DEFAULTS[build])
    assert not missing, f"{build} leaves {sorted(missing)} unplaced"


@pytest.mark.parametrize("build", BUILDS)
def test_drawn_equals_written(build):
    """THE INVARIANT. For every axis, the rung the diagram draws is the rung
    whose sentence lands in her bio."""
    resolved = _build_axes(build)
    written = _body_axis_parts(resolved)
    for axis, rung in resolved.items():
        part = BODY_AXES[axis]["part"]
        drawn = BODY_AXES[axis]["steps"][rung][1]
        assert written[part] == drawn, (
            f"{build}/{axis}: diagram shows {drawn!r}, bio gets {written[part]!r}")


@pytest.mark.parametrize("build", BUILDS)
def test_a_dialled_axis_overrides_its_preset(build):
    """'Curvy, but with thicker thighs' has to be expressible, and the edit has
    to win — while every axis the user did NOT touch keeps the preset's rung
    rather than reverting to a default nobody chose."""
    resolved = _build_axes(build, {"thighs": 4})
    assert resolved["thighs"] == 4
    for axis in BODY_AXES:
        if axis != "thighs":
            assert resolved[axis] == BUILD_AXIS_DEFAULTS[build][axis]


def test_axes_point_at_real_parts():
    """An axis naming a part that does not exist writes into nothing, and
    build_clause would never see it."""
    known = {p.id for p in promptlib.default_parts() if p.section == "body"}
    for axis, spec in BODY_AXES.items():
        assert spec["part"] in known, f"{axis} -> {spec['part']} is not a body part"


def test_every_rung_survives_the_sanitiser():
    """These sentences reach a provider's moderation. sanitise() leaves size
    and shape alone and guards exposure, so a rung it rewrites is one whose
    wording drifted toward the boundary — and the panel would then be showing
    text that is not what gets sent."""
    for axis, spec in BODY_AXES.items():
        for label, text in spec["steps"]:
            clean, hits = promptlib.sanitise(text)
            assert clean == text, (
                f"{axis}/{label} is rewritten to {clean!r} by {hits}")


def test_defaults_are_in_range():
    for axis, spec in BODY_AXES.items():
        assert 0 <= spec["default"] < len(spec["steps"]), axis
        for build, rungs in BUILD_AXIS_DEFAULTS.items():
            assert 0 <= rungs[axis] < len(spec["steps"]), f"{build}/{axis}"
