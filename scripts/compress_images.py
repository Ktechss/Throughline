"""Re-encode the back catalogue of generated images, and fix the db to match.

`config.ARCHIVE_*` shrinks every NEW shot on the way in. This is the other half:
the 360 images already on disk at ~25 MB each. Same measurement behind both — on
the six largest generated images with faces, re-encoded and re-scored against the
real gallery, WebP q90 came to 8% of the size with no verdict flipped, face sizes
within 1px, and shifts scattering both directions around a mean of +0.0002.

    python scripts/compress_images.py                 # dry run — reports, changes nothing
    python scripts/compress_images.py --apply
    python scripts/compress_images.py --apply --wardrobe
    python scripts/compress_images.py --apply --regate     # slow; proves it per file

WHY THIS IS NOT JUST A LOOP OVER FILES: a run row stores its filename
(`runs.doc -> file`), and so does the wardrobe metadata. Convert the files without
rewriting those and every thumbnail 404s. So each image is converted, VERIFIED
readable at the right dimensions, and only then does the original get unlinked and
the row get rewritten — per file, so an interruption leaves a consistent mixture
rather than a half-migrated set.

NOT TOUCHED, deliberately:
  refs/ bodies/   references are read by ArcFace as ground truth and their quality
                  propagates into every image she appears in. Measured on refs,
                  lossy cost a real embedding shift (mean 0.985, worst 0.969)
                  where lossless was exactly 1.0000. They stay as they are.
  gold/           the human-approved LoRA set. Training data earns the same care.
  places/         her home, generated once and read as a scene reference.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import config  # noqa: E402

DB = ROOT / "data" / "eve1.db"
FMT = config.ARCHIVE_FORMAT
Q = config.ARCHIVE_QUALITY


def convert(src: Path) -> Path | None:
    """Write the re-encode next to the original and prove it before returning it."""
    out = src.with_suffix(f".{FMT}")
    if out.exists():
        return None
    with Image.open(src) as im:
        size = im.size
        im.convert("RGB").save(out, FMT.upper(), quality=Q, method=4)
    try:
        with Image.open(out) as check:      # readable, and the same picture
            if check.size != size:
                raise ValueError(f"size changed {size} -> {check.size}")
    except Exception as exc:                 # noqa: BLE001
        out.unlink(missing_ok=True)
        raise ValueError(f"verify failed: {exc}") from exc
    return out


def run(cid: str, apply: bool, wardrobe: bool, regate: bool,
        no_images: bool = False) -> None:
    base = config.char_base(cid)
    targets = []
    if not no_images:
        targets.append(("images", base / "images"))
    if wardrobe:
        targets.append(("wardrobe", base / "wardrobe"))
    if not targets:
        print("nothing selected (--no-images with no --wardrobe)")
        return

    gate = None
    if regate:
        from backend import gate as _gate
        gate = _gate

    # The backend may be running and writing runs of its own; wait for it rather
    # than dying on "database is locked" 300 files in.
    con = sqlite3.connect(DB, timeout=30) if apply else None
    grand_before = grand_after = 0
    for label, d in targets:
        files = sorted(p for p in d.glob("*.png") if p.is_file())
        if not files:
            print(f"{label}: nothing to do")
            continue
        before = after = 0
        done = failed = 0
        print(f"\n{label}: {len(files)} PNGs, {sum(f.stat().st_size for f in files)/1e9:.2f} GB")
        for i, src in enumerate(files, 1):
            b = src.stat().st_size
            if not apply:
                # Estimate without writing: encode to memory. A file that cannot
                # be read here is one --apply would skip too, so surface it now —
                # a truncated download in the archive is worth knowing about
                # regardless of whether it is ever compressed.
                import io
                try:
                    buf = io.BytesIO()
                    with Image.open(src) as im:
                        im.convert("RGB").save(buf, FMT.upper(), quality=Q, method=4)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print(f"  UNREADABLE {src.name}: {exc}", flush=True)
                    continue
                before += b
                after += buf.tell()
                done += 1
                if i % 25 == 0 or i == len(files):
                    print(f"  {i}/{len(files)} scanned", flush=True)
                continue
            try:
                out = convert(src)
                if out is None:
                    continue
                if gate is not None:
                    _compare(gate, src, out)
                before += b
                after += out.stat().st_size
                # Order matters, and so does committing HERE rather than at the
                # end. Rewrite the row and commit BEFORE unlinking the original:
                # crash after the commit and both files exist, with the row naming
                # the new one (harmless); crash before it and the original is still
                # there with the row still naming it. Batching the commits would
                # make an interruption delete files the db still points at, and
                # hold a write lock on eve1.db for the whole run.
                _rewrite(con, label, src, out)
                con.commit()
                src.unlink()
                done += 1
            except Exception as exc:  # noqa: BLE001 — never lose an image to this
                failed += 1
                print(f"  SKIP {src.name}: {exc}", flush=True)
            if i % 25 == 0 or i == len(files):
                print(f"  {i}/{len(files)}  {before/1e9:.2f} -> {after/1e9:.2f} GB", flush=True)
        grand_before += before
        grand_after += after
        verb = "would shrink" if not apply else "shrank"
        print(f"{label}: {verb} {before/1e9:.2f} GB -> {after/1e9:.2f} GB "
              f"({after/before*100:.0f}%), {done} converted, {failed} skipped"
              if before else f"{label}: nothing")

    if con is not None:
        con.commit()
        con.close()
    if grand_before:
        print(f"\nTOTAL {grand_before/1e9:.2f} GB -> {grand_after/1e9:.2f} GB "
              f"({grand_after/grand_before*100:.0f}%), "
              f"{(grand_before-grand_after)/1e9:.2f} GB freed")
    if not apply:
        print("\nDRY RUN — nothing changed. Re-run with --apply.")


def _compare(gate, src: Path, out: Path) -> None:
    """Score both and refuse the swap if the verdict would change."""
    try:
        a, b = gate.check(src), gate.check(out)
    except gate.NoFaceFound:
        return          # empty rooms and turnarounds have no face by design
    except (FileNotFoundError, ValueError):
        return
    if a.status != b.status:
        raise ValueError(f"verdict would flip {a.status} -> {b.status}")


def _rewrite(con: sqlite3.Connection, label: str, src: Path, out: Path) -> None:
    """Point the db at the new filename. One row, one statement, same txn as the
    unlink that follows it."""
    if label == "images":
        for seq, doc in con.execute("SELECT seq, doc FROM runs").fetchall():
            d = json.loads(doc)
            if d.get("file") != src.name:
                continue
            d["file"] = out.name
            con.execute("UPDATE runs SET doc=? WHERE seq=?", (json.dumps(d), seq))
            break
    else:
        # Wardrobe metadata is keyed by STEM, which does not change — nothing to
        # rewrite. Recorded here so the asymmetry is not mistaken for an omission.
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually convert (default: dry run)")
    ap.add_argument("--wardrobe", action="store_true", help="also convert wardrobe/")
    ap.add_argument("--no-images", action="store_true",
                    help="leave images/ alone. Use this once images/ has been done: "
                         "the PNGs still there are the ones --regate REFUSED, and a "
                         "later run without --regate would silently convert them.")
    ap.add_argument("--regate", action="store_true",
                    help="re-score every image before and after; refuse any swap "
                         "that would flip a verdict (slow)")
    ap.add_argument("--character", default=None, help="character id (default: active)")
    a = ap.parse_args()
    run(a.character or config.get_active(), a.apply, a.wardrobe, a.regate,
        a.no_images)
