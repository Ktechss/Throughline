"""References must not be re-uploaded, and must not be uploaded one at a time.

Measured against kie: an upload takes ~77 SECONDS REGARDLESS OF SIZE. 0.30MB
and 16.37MB both took 77s, so it is a fixed per-call cost at their end, not
bandwidth — this machine does 1.3 MB/s up and 1.7 MB/s down, both healthy.

That made a 4-reference scene spend ~308s uploading before kie saw a task at
all, against a 78.6s render. The owner asked whether kie was slow; it is, but
in its UPLOAD endpoint, not its renderer, and the sequential loop multiplied it.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend import providers


@pytest.fixture(autouse=True)
def _clean_cache():
    providers._UPLOAD_CACHE.clear()                      # noqa: SLF001
    yield
    providers._UPLOAD_CACHE.clear()                      # noqa: SLF001


@pytest.fixture()
def fake_upload(monkeypatch, tmp_path):
    """Count real uploads without touching the network."""
    calls = []

    def fake_post(url, payload, key, timeout=60):
        calls.append(payload.get("fileName"))
        time.sleep(0.05)                                  # stand in for the 77s
        return {"data": {"downloadUrl": f"https://x/{payload.get('fileName')}"}}

    monkeypatch.setattr(providers, "_post", fake_post)
    monkeypatch.setattr(providers, "kie_key", lambda: "test")
    return calls


def _ref(tmp_path, name="face.webp"):
    p = tmp_path / name
    p.write_bytes(b"\x00" * 2048)
    return p


def test_the_same_reference_uploads_once(fake_upload, tmp_path):
    p = _ref(tmp_path)
    a = providers.kie_upload(p)
    b = providers.kie_upload(p)
    assert a == b
    assert len(fake_upload) == 1, (
        f"uploaded {len(fake_upload)} times; her face reference goes up on "
        "every shot and kie hosts it for 3 days")


def test_an_edited_reference_uploads_again(fake_upload, tmp_path):
    """The cache keys on (path, mtime, size). A changed file MUST NOT serve a
    stale URL — a run records the reference by name, and provenance depends on
    that name pointing at those bytes."""
    p = _ref(tmp_path)
    providers.kie_upload(p)
    time.sleep(0.01)
    p.write_bytes(b"\x01" * 4096)                         # different size + mtime
    providers.kie_upload(p)
    assert len(fake_upload) == 2


def test_uploads_run_concurrently(fake_upload, tmp_path):
    """Four independent HTTP calls have no reason to queue. At 77s each that is
    the difference between 308s and 77s."""
    refs = [_ref(tmp_path, f"r{i}.webp") for i in range(4)]
    t = time.time()
    urls = providers.kie_upload_many(refs)
    el = time.time() - t
    assert len(urls) == 4 and len(set(urls)) == 4
    assert el < 0.15, f"took {el:.2f}s — looks sequential, not parallel"


def test_order_is_preserved(fake_upload, tmp_path):
    """@image1 is her FACE and @image2 is the outfit. Reordering the URLs would
    silently swap which reference carries identity."""
    refs = [_ref(tmp_path, f"{n}.webp") for n in ("face", "outfit", "nails")]
    urls = providers.kie_upload_many(refs)
    assert [u.rsplit("/", 1)[-1] for u in urls] == ["face.webp", "outfit.webp", "nails.webp"]
