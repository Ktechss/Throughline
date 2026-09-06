"""Who renders what, and why the exceptions are exceptions.

Routing is normally "cheapest model that can do the job", which is right: the
measured quality spread between providers is 0.016, inside this project's own
seed-to-seed variance. FACE_SEED is the one place that reasoning fails, and it
failed silently — faces rendered on nano-banana-2 because it is $0.09 against
nano-banana-pro's $0.12. Three cents, on the single image every later shot is
scored against. The owner noticed the quality difference before the code did.
"""
from __future__ import annotations

import pytest

from backend import vendors  # noqa: F401 — registers providers and models
from backend.registry import REGISTRY, Mode, Purpose


def _first(purpose, has_refs, order=("kie", "poyo", "fal")):
    c = REGISTRY.candidates(purpose, has_refs=has_refs, order=list(order))
    return (c[0][0].name, c[0][1].key) if c else (None, None)


def test_faces_prefer_quality_over_price():
    """THE INVARIANT the owner asked for. Whatever else changes, the master
    face must not be routed by price."""
    prov, model = _first(Purpose.FACE_SEED, has_refs=False)
    assert model == "nano-banana-pro", (
        f"faces are rendering on {prov}/{model}, not nano-banana-pro")


def test_faces_still_have_a_fallback():
    """Preference must not become a single point of failure — the whole reason
    the registry exists is that a hardcoded model killed a build."""
    c = REGISTRY.candidates(Purpose.FACE_SEED, has_refs=False,
                            order=["kie", "poyo", "fal"])
    assert len(c) > 1, "no fallback behind the preferred face model"


@pytest.mark.parametrize("purpose", [Purpose.ROOM, Purpose.SHOT])
def test_everything_else_still_takes_the_cheapest(purpose):
    """The exception must stay an exception. A room is not worth a premium."""
    c = REGISTRY.candidates(purpose, has_refs=False, order=["kie"])
    prices = [s.usd_4k for _, s in c]
    assert prices == sorted(prices), (
        f"{purpose.value} is no longer price-ordered: {prices}")


def test_settings_order_outranks_preference():
    """Provider precedence is the user's setting and must win over any
    purpose's opinion — that is the bug this whole registry was built to fix."""
    c = REGISTRY.candidates(Purpose.FACE_SEED, has_refs=False,
                            order=["poyo", "kie", "fal"])
    if c and any(p.name == "poyo" for p, _ in c):
        assert c[0][0].name == "poyo", "a purpose preference jumped the Settings order"


def test_a_preferred_model_that_cannot_do_the_job_is_not_chosen():
    """gpt-image-2 is preferred for faces but is TEXT2IMG only. Asking with
    references must not select it."""
    c = REGISTRY.candidates(Purpose.FACE_SEED, has_refs=True,
                            order=["kie", "poyo", "fal"])
    for _, spec in c:
        assert Mode.EDIT in spec.modes, f"{spec.key} cannot edit but was offered"
