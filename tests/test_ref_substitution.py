"""A queued job must survive its reference being replaced underneath it.

main.py's _promote deletes any same-stem image before copying, so picking a
calibration face as her master writes "<cid>-identity.webp" and removes the
".jpg" that was there. Jobs already queued still hold the old path.

The window always existed and was near-zero. The provider concurrency cap
widened it to ~700s, and four of ten calibration angles were then lost to
FileNotFoundError — the cap did not create the bug, it made it reachable.

Her identity reference genuinely changed, so the run should use the new one and
record the substitution, not die on a stale filename.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def char(tmp_path, monkeypatch):
    from backend import config, generate
    base = tmp_path / "characters" / "kiara"
    (base / "refs").mkdir(parents=True)
    (base / "state").mkdir(parents=True)
    (base / "images").mkdir(parents=True)
    monkeypatch.setattr(config, "CHARACTERS", tmp_path / "characters")
    new = base / "refs" / "kiara-identity.webp"
    new.write_bytes(b"new")
    (base / "state" / "bio.json").write_text(
        json.dumps({"reference": "kiara-identity.webp"}))
    return base


def _resolve(refs, owner, meta=None):
    """Run just the substitution block by calling generate with a stub chain."""
    from backend import config, generate
    seen = {}

    def fake_reserve(rid, cid, doc):
        seen["doc"] = doc
        raise _Stop()

    class _Stop(Exception):
        pass

    from backend import db
    orig = db.runs_reserve
    db.runs_reserve = fake_reserve
    try:
        generate.generate(prompt="p", refs=refs, character=owner, meta=meta)
    except _Stop:
        pass
    except Exception:
        pass
    finally:
        db.runs_reserve = orig
    return seen.get("doc")


def test_a_replaced_reference_is_swapped_for_the_current_one(char):
    gone = char / "refs" / "kiara-identity.jpg"        # deleted by _promote
    doc = _resolve([gone], "kiara")
    assert doc is not None, "generate never reached the reserve step"
    assert doc["refs"] == ["kiara-identity.webp"], (
        f"expected the current reference, got {doc['refs']}")
    sub = (doc.get("meta") or {}).get("ref_substituted")
    assert sub and sub[0]["was"] == "kiara-identity.jpg", (
        "the substitution must be recorded — a run records its refs by name, "
        f"so an unrecorded swap makes the row lie. got {sub}")


def test_a_surviving_reference_is_left_alone(char):
    ok = char / "refs" / "kiara-identity.webp"
    doc = _resolve([ok], "kiara")
    assert doc["refs"] == ["kiara-identity.webp"]
    assert "ref_substituted" not in (doc.get("meta") or {}), (
        "nothing was replaced; the row must not claim otherwise")


def test_it_refuses_when_nothing_can_be_recovered(char):
    """If the bio's reference is gone too there is nothing honest to send."""
    (char / "state" / "bio.json").write_text(json.dumps({"reference": "nope.webp"}))
    from backend import generate
    with pytest.raises(Exception) as e:
        generate.generate(prompt="p",
                          refs=[char / "refs" / "missing.jpg"],
                          character="kiara")
    assert "replaced or deleted" in str(e.value) or "reference" in str(e.value).lower()


def test_deleting_the_master_face_is_refused(char, monkeypatch):
    """A one-line unlink with no guard made a character unusable.

    Deleting her master face left bio.json pointing at a file that no longer
    existed: has_reference went false, the studio's mandatory face gate fired,
    and there was no way back except re-uploading. Observed on vamika, whose
    bio still read reference=vamika-identity.webp after the DELETE.

    Refusing beats deleting-and-clearing: clearing would leave her equally
    faceless, just consistently so. The reference is the one load-bearing file
    here — every shot attaches it and every past run records it by name.
    """
    from fastapi import HTTPException
    from backend import main

    monkeypatch.setattr(main, "REFS", char / "refs")
    monkeypatch.setattr(main, "_bio_cfg",
                        lambda *a, **k: {"reference": "kiara-identity.webp"})

    with pytest.raises(HTTPException) as e:
        main.delete_ref("kiara-identity.webp")
    assert e.value.status_code == 409
    assert "master face" in str(e.value.detail)
    assert (char / "refs" / "kiara-identity.webp").exists(), (
        "it refused but deleted the file anyway")


def test_an_ordinary_reference_still_deletes(char, monkeypatch):
    from backend import main
    spare = char / "refs" / "calib-smile.png"
    spare.write_bytes(b"x")
    monkeypatch.setattr(main, "REFS", char / "refs")
    monkeypatch.setattr(main, "_bio_cfg",
                        lambda *a, **k: {"reference": "kiara-identity.webp"})
    main.delete_ref("calib-smile.png")
    assert not spare.exists()
