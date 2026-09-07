"""The clip path must at least RUN before it is asked to spend anything.

WHY THIS EXISTS. `generate_video` carried a copy of the still path's
reference-substitution block, which refers to a local named `refs`. This
function has no `refs` — its inputs are `still` and `end_still` — so the very
first statement to touch it raised UnboundLocalError. Every call died before
reaching a provider, and nothing noticed: the app booted, 139 tests passed, and
no test drove this function at all.

That is the same shape as the bug that killed a character build earlier in this
project (a lazily-imported module hoisted to where it was undefined): an
unexercised path, a NameError-class failure, and a green suite.

These tests do not need a provider or a key. They only require that the function
gets far enough to make a decision about its inputs.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from backend import generate


def test_generate_video_does_not_reach_for_the_still_paths_variables():
    """The exact mistake, named.

    A correct general check here would be a scope analyser, and a bad one is
    worse than none — the first version of this test flagged `dict` and `p` and
    taught nobody anything. So this asserts the specific thing that went wrong:
    `generate_video` animates `still`/`end_still` and must never mention the
    still path's `refs`. The two tests below cover the general case the only way
    that is actually reliable — by calling the function.
    """
    src = inspect.getsource(generate.generate_video)
    fn = ast.parse(src).body[0]
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "refs" not in names, (
        "generate_video refers to `refs`, which belongs to the still path. It "
        "has `still` and `end_still`; reading `refs` here is an "
        "UnboundLocalError on the first call.")


def test_a_missing_still_fails_with_a_readable_error(tmp_path):
    """The dynamic version: the function must RUN, and it must refuse a frame
    that is not there rather than substituting a different image.

    Substitution is correct on the still path and wrong here — /api/video
    refuses an ungated still so that a clip inherits identity from an APPROVED
    frame. Animating a fallback image would void exactly that.
    """
    with pytest.raises(RuntimeError) as exc:
        generate.generate_video(still=tmp_path / "not-here.webp", prompt="she blinks")
    msg = str(exc.value)
    assert "not-here.webp" in msg
    assert "approved frame" in msg, msg
    # The failure that was actually happening must not come back.
    assert "refs" not in msg


def test_it_is_not_an_unbound_local(tmp_path):
    """Name the regression directly: any NameError/UnboundLocalError out of this
    function is the bug, whatever else changes around it."""
    try:
        generate.generate_video(still=tmp_path / "gone.webp", prompt="x")
    except (NameError, UnboundLocalError) as exc:      # pragma: no cover
        pytest.fail(f"generate_video died on an undefined name: {exc}")
    except Exception:
        pass


def test_the_video_provider_is_chosen_by_key_not_by_name(monkeypatch):
    """A default that names a vendor is a guess about the deployment.

    VideoReq.provider was the literal "poyo" while POYO_API_KEY was still the
    shipped placeholder, so the Motion tab's one button could only fail on auth
    — the same shape as the character build that died on a placeholder FAL_KEY
    while a paid, configured provider sat unused.
    """
    from backend import providers

    monkeypatch.setenv("KIE_API_KEY", "k" * 32)
    monkeypatch.setenv("POYO_API_KEY", "your-poyo-key")
    assert providers.video_provider_default() == "kie"

    monkeypatch.setenv("KIE_API_KEY", "your-kie-key")
    monkeypatch.setenv("POYO_API_KEY", "p" * 32)
    assert providers.video_provider_default() == "poyo"


def test_every_video_provider_has_a_runner():
    """A catalogue entry with no runner is a model the UI can offer and the
    backend cannot render."""
    from backend import providers
    for name in ("kie", "poyo"):
        assert name in providers.VIDEO_RUNNERS, f"{name} has no video runner"
