"""The gate must never score an upscaled file.

Measured 2026-08-12, topaz x2 on the 5-pro rooftop shot:

    face_px      169 -> 338      (x2.00)
    similarity   0.6417 -> 0.6363  (-0.0055)

The pixels double and the identity signal does not, because insightface detects
at a fixed det_size=(640,640) and ArcFace embeds a 112x112 aligned crop — a
169px face is already downsampled twice before it is read. So an upscaled file
scored by the gate clears MIN_FACE_PX (160) and the FACE_PLATEAU_PX (400) band
on manufactured confidence, and silently joins a corpus of 207 shots calibrated
at native resolution.

These tests are cheap structural guards, not a re-measurement. They exist so the
quarantine survives a refactor by someone who does not know the above.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "backend" / "main.py").read_text()
GENERATE = (ROOT / "backend" / "generate.py").read_text()
PROVIDERS = (ROOT / "backend" / "providers.py").read_text()

HIRES_DIR = ".hires"


def test_upscale_is_never_called_from_the_generation_path():
    """kie_upscale belongs to export. generate() must not reach it."""
    assert "kie_upscale" not in GENERATE, (
        "generate.py calls kie_upscale — upscaling in the generation path puts an "
        "inflated face_px behind row['file'] and corrupts the verdict ledger")


def test_hires_cache_dir_is_not_the_images_dir():
    """The derivative caches in a hidden sibling, like .thumbs/ and .outfitcrops/.

    If it ever landed in IMAGES itself, the sweeper and every grid would treat an
    upscaled export as a generated run.
    """
    assert f'IMAGES / "{HIRES_DIR}"' in MAIN, (
        "the hires cache must live in a hidden sibling dir under IMAGES")


def test_no_gate_call_shares_a_line_with_the_hires_cache():
    """A crude but load-bearing check: no gate.check on a hires path."""
    for i, line in enumerate(MAIN.splitlines(), 1):
        if HIRES_DIR in line or "image_hires" in line:
            assert "gate.check" not in line, (
                f"main.py:{i} scores a hires path — the gate must only ever see "
                f"the native image")


def test_hires_endpoint_reads_the_stored_file_not_the_source_url():
    """source_url is the raw CDN PNG (~20MB) and exceeds topaz's 10MB cap.

    Reading the archived copy is also what keeps the original authoritative.
    """
    m = re.search(r"def image_hires\(.*?\n(.*?)(?=\n@app\.|\ndef )", MAIN, re.S)
    assert m, "image_hires not found"
    body = m.group(1)
    assert "IMAGES / Path(name).name" in body
    assert "source_url" not in body, (
        "hires must upscale the stored archive copy, not the provider URL")


def test_upscale_rejects_factors_outside_the_topaz_enum():
    from backend import providers
    with pytest.raises(providers.ProviderError):
        providers.kie_upscale(ROOT / "backend" / "main.py", "3")


def test_upscale_refuses_inputs_over_the_topaz_cap(tmp_path):
    """A 4K PNG off the CDN is ~20MB; topaz refuses over 10MB.

    Caught here with a named error rather than an opaque provider failure.
    """
    from backend import providers
    big = tmp_path / "big.png"
    big.write_bytes(b"\0" * (11 * 1024 * 1024))
    with pytest.raises(providers.ProviderError, match="cap"):
        providers.kie_upscale(big, "2")


def test_runs_record_measured_dimensions():
    """The row must carry the size that ARRIVED, not the size requested.

    config.py records the incident this closes: a 1024x768 landscape master face
    with a 306px subject, where "the run row recorded aspect 3:4 / 4K, so nothing
    looked wrong".
    """
    assert '"width": img_w, "height": img_h,' in GENERATE, (
        "run rows must record measured pixel dimensions")
    assert "_PILImage.open(dest)" in GENERATE, (
        "dimensions must be measured from the downloaded file, not derived from "
        "the requested aspect/resolution")


def test_upscale_documents_why_it_is_quarantined():
    """The numbers are the reason this design is shaped this way.

    If someone deletes the rationale they will re-litigate it with a generation.
    """
    assert "112x112" in PROVIDERS and "det_size" in PROVIDERS, (
        "keep the measured reason kie_upscale is export-only next to the code")
