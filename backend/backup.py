"""Take a character off this machine, and put one back.

WHY IT EXISTS. `data/` is gitignored and runs 1-11 GB, so a clone gives you a
working app and an empty studio. Recovering Kiara from a hand-made `kiara.tar`
took: reading the tar listing, noticing the backend held `eve1.db` open in WAL
mode and stopping it, extracting, `pragma integrity_check`, counting gallery
entries, and hand-verifying that bio.json's three pointers resolved. Every one of
those is something this module does better than a person with `tar -tvf`.

`scripts/sync_data.sh` is the domain authority on WHAT A CHARACTER IS — bio +
body + home, with wardrobe and images as dressing — and this reuses its taxonomy
rather than inventing a second one. The script stays as the machine-to-machine
path; this is the same judgement behind a button.

THREE THINGS THAT ARE NOT OBVIOUS AND COST REAL DATA IF FORGOTTEN:

  * The db is copied through sqlite's own backup API, never as a file. A running
    backend in WAL mode can hand a plain `cp` a torn database, and a torn db is
    silently a DIFFERENT character — rows missing, no error anywhere. This is
    also why a backup no longer requires stopping the server, which was the worst
    part of the manual recovery.

  * `runs.id` is UNIQUE across the WHOLE database, not per character. Restoring
    an archive alongside the character it came from therefore collides on every
    single run id. Side-by-side restore re-mints them (and renames the image file
    to match, because `file` == `id` + ext holds for every row we have).

  * Wardrobe FILES and wardrobe ROWS travel together or not at all. Rows without
    images is a wardrobe of broken thumbnails; images without rows is a folder
    the app cannot see. One part governs both, so neither can be chosen alone.

ARCHIVE LAYOUT (schema 1). The manifest is the FIRST member so `inspect()` reads
one small entry instead of scanning 11 GB:

    throughline-backup.json     manifest: what is in here, and how much
    db.sqlite                   staged, filtered to the chosen characters
    characters/<cid>/...        her files

Archives made by hand (`tar cf kiara.tar data/`) have no manifest and put things
under `data/characters/<cid>/`. `inspect()` and `restore()` read those too — the
one that prompted this feature is exactly that shape, and refusing it would have
failed the only real test case available.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tarfile
import tempfile
import time
import uuid
from pathlib import Path

from . import config, db

SCHEMA = 1
MANIFEST = "throughline-backup.json"
DB_MEMBER = "db.sqlite"

# Derived caches. They are regenerated on demand from the files that ARE in the
# archive, and they are big — shipping them doubles some backups to carry nothing
# a first page view would not rebuild.
SKIP_DIRS = {".thumbs", ".hires", ".outfitcrops"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}

# WHAT A CHARACTER IS, as data rather than branches. Sizes are from the live
# 1.0 GB character, as a sense of scale for whoever edits this next.
#
# `rows` names the db tables whose rows are INSEPARABLE from those files.
PARTS: dict[str, dict] = {
    "identity": {
        "label": "Identity — bio, body, home",
        # state/ carries bio.json and parts.json. Without parts.json the code
        # silently falls back to default_parts() and her written identity is
        # replaced by a stranger's defaults, with no error — which is why the
        # part tree is identity, not settings. gallery.npz is here too: without
        # it every run comes back `ungated` and "is this still her?" has no
        # answer at all.
        "dirs": ["state", "refs", "bodies", "places", "nails", "poses",
                 "pose-refs", "gold"],
        "rows": [],
        # Not optional. An archive without it is not a character.
        "required": True,
        "note": "her face, her build, her rooms, and the gate's yardstick",
    },
    "wardrobe": {
        "label": "Wardrobe",
        "dirs": ["wardrobe"],
        "rows": ["wardrobe"],
        "required": False,
        "note": "outfits — what she wears, not who she is",
    },
    "images": {
        "label": "Generated images",
        "dirs": ["images"],
        "rows": [],
        "required": False,
        "note": "past output; the run ledger travels either way",
    },
}

PRESETS: dict[str, list[str]] = {
    "identity": ["identity"],
    "all": list(PARTS),
}


class BackupError(RuntimeError):
    """Anything that should reach the user as a sentence rather than a stack."""


# --------------------------------------------------------------------- helpers

def normalise(parts) -> list[str]:
    """Accept a preset name or an explicit list; always return a valid list.

    `identity` is forced in rather than validated out: every caller wants it,
    and an archive that omits it is a folder of outfits with nobody in it.
    """
    if isinstance(parts, str):
        if parts not in PRESETS:
            raise BackupError(f"unknown preset {parts!r} — have {sorted(PRESETS)}")
        parts = PRESETS[parts]
    unknown = [p for p in parts if p not in PARTS]
    if unknown:
        raise BackupError(f"unknown part(s) {unknown} — have {sorted(PARTS)}")
    out = [p for p in PARTS if p in set(parts) or PARTS[p].get("required")]
    return out


def _walk(root: Path):
    """Every real file under root, skipping derived caches and OS litter.

    Dotfiles are skipped wholesale, which matters more than it looks. `state/`
    holds `.avatar-<stem>.jpg`, a cache validated by MTIME
    (`main.py:1272`: `cache.stat().st_mtime < src.stat().st_mtime`). tar restores
    the ORIGINAL mtime, so shipping the cache means a restored face can arrive
    older than a cache already on the machine — the check then says "fresh" and
    she keeps the wrong face permanently. That is verbatim the bug the comment at
    that line was written about. Leaving every derived cache out of the archive
    makes it unreachable by construction.
    """
    if not root.exists():
        return
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        if p.name in SKIP_FILES or p.name.startswith("."):
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        yield p


def _dir_stats(root: Path) -> tuple[int, int]:
    n = b = 0
    for p in _walk(root):
        n += 1
        b += p.stat().st_size
    return n, b


def _state_json(cid: str, name: str) -> dict | None:
    p = config.char_base(cid) / "state" / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:                                       # noqa: BLE001
        return None


def plan(cids: list[str], parts) -> dict:
    """What a backup WOULD contain, without copying a byte.

    Powers both the size readout in the UI and the manifest itself, so the two
    can never disagree about what was in an archive.
    """
    parts = normalise(parts)
    known = {c["id"]: c for c in db.chars_all()}
    missing = [c for c in cids if c not in known]
    if missing:
        raise BackupError(f"no such character: {', '.join(missing)}")

    chars, files, size = [], 0, 0
    for cid in cids:
        base = config.char_base(cid)
        info: dict = {"id": cid, "name": known[cid].get("name") or cid,
                      "files": 0, "bytes": 0, "dirs": {}}
        for part in parts:
            for d in PARTS[part]["dirs"]:
                n, b = _dir_stats(base / d)
                if n:
                    info["dirs"][d] = {"files": n, "bytes": b}
                info["files"] += n
                info["bytes"] += b

        # The ledger always travels: 359 rows is under 2 MB and it carries the
        # `mark` verdicts, which are the ONLY record of the one axis the gate is
        # blind to. Losing them is unrecoverable in a way images are not.
        info["runs"] = len(db.runs_all(character_id=cid))
        info["wardrobe"] = (len(db.wardrobe_meta(character_id=cid))
                            if "wardrobe" in parts else 0)

        # Stated up front because the manual recovery had to work all three out
        # by hand before it could trust the archive.
        g = _state_json(cid, "gallery.json")
        info["gallery_entries"] = len(g) if isinstance(g, dict) else 0
        t = _state_json(cid, "threshold.json")
        info["threshold"] = (t or {}).get("threshold")

        # An images-less backup keeps the rows; say how many will have no file
        # behind them so /api/runs/missing is a follow-up, not a surprise.
        info["runs_without_files"] = 0 if "images" in parts else info["runs"]

        chars.append(info)
        files += info["files"]
        size += info["bytes"]

    return {"schema": SCHEMA, "parts": parts, "characters": chars,
            "files": files, "bytes": size}


# ---------------------------------------------------------------------- create

def preflight_disk(need: int, where: Path) -> None:
    """Refuse with a NUMBER rather than dying at 97%.

    A restore peaks at roughly archive + staging + snapshot, so it asks for
    noticeably more than the archive's own size.
    """
    free = shutil.disk_usage(where).free
    if free < need:
        raise BackupError(
            f"not enough space on {where}: need ~{need / 1e9:.1f} GB, "
            f"{free / 1e9:.1f} GB free")


def _staged_db(tmp: Path, cids: list[str], parts: list[str]) -> Path:
    """A copy of the global db holding ONLY the chosen characters.

    Through sqlite's backup API, never a file copy: the backend may be mid-write
    in WAL mode, and a torn db restores as a quietly different character. The
    filtering happens on the COPY, so the live database is never touched — the
    same guarantee scripts/sync_data.sh gives.
    """
    out = tmp / DB_MEMBER
    src = sqlite3.connect(f"file:{db.DB_PATH}?mode=ro", uri=True)
    dst = sqlite3.connect(out)
    try:
        with dst:
            src.backup(dst)
        keep = ",".join("?" * len(cids))
        with dst:
            dst.execute(f"DELETE FROM runs WHERE character_id NOT IN ({keep})", cids)
            dst.execute(f"DELETE FROM characters WHERE id NOT IN ({keep})", cids)
            if "wardrobe" in parts:
                dst.execute(f"DELETE FROM wardrobe WHERE character_id NOT IN ({keep})",
                            cids)
            else:
                # Rows without their images would be a wardrobe of broken
                # thumbnails on the far side.
                dst.execute("DELETE FROM wardrobe")
        dst.execute("VACUUM")
    finally:
        dst.close()
        src.close()
    return out


def default_name(cids: list[str], parts: list[str]) -> str:
    who = cids[0] if len(cids) == 1 else f"{len(cids)}-characters"
    tag = "identity" if parts == ["identity"] else "full"
    return f"{who}-{time.strftime('%Y%m%d-%H%M')}-{tag}.tar"


def create(dest: str | Path, cids: list[str], parts, job: dict | None = None) -> dict:
    """Write one archive. Returns {path, bytes, files, manifest}.

    UNCOMPRESSED on purpose. Measured on the 1.0 GB character: tar 5.5s,
    tar.gz 14.1s. The tree is 510 webp + 263 jpg — already compressed — so gzip
    costs 2.6x the wall clock to save almost nothing.
    """
    parts = normalise(parts)
    man = plan(cids, parts)
    man["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    dest = Path(dest).expanduser()
    if dest.is_dir() or not dest.suffix:
        dest = dest / default_name(cids, parts)
    dest.parent.mkdir(parents=True, exist_ok=True)
    preflight_disk(int(man["bytes"] * 1.05) + 64 * 1024 * 1024, dest.parent)

    total = man["files"]
    done = 0
    # Build beside the destination and rename at the end, so an interrupted
    # backup never leaves a half-written .tar that looks like a real one.
    tmp_out = dest.with_suffix(dest.suffix + ".part")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        if job is not None:
            job["stage"] = "staging database"
        staged = _staged_db(tmp, cids, parts)

        if job is not None:
            job["stage"] = "writing archive"
        with tarfile.open(tmp_out, "w") as tar:
            # FIRST member, so inspect() is one small read.
            mpath = tmp / MANIFEST
            mpath.write_text(json.dumps(man, indent=2) + "\n")
            tar.add(mpath, arcname=MANIFEST)
            tar.add(staged, arcname=DB_MEMBER)

            for cid in cids:
                base = config.char_base(cid)
                for part in parts:
                    for d in PARTS[part]["dirs"]:
                        for p in _walk(base / d):
                            tar.add(p, arcname=f"characters/{cid}/{d}/"
                                               f"{p.relative_to(base / d)}")
                            done += 1
                            if job is not None and done % 25 == 0:
                                job["step"] = f"{done}/{total} files"
    tmp_out.replace(dest)
    if job is not None:
        job["step"] = None
    return {"path": str(dest), "bytes": dest.stat().st_size,
            "files": total, "manifest": man}


# --------------------------------------------------------------------- inspect

def _members_layout(names: list[str]) -> tuple[str, str | None]:
    """(character prefix, db member) for either archive shape.

    Ours is characters/<cid>/…; a hand-rolled `tar cf x.tar data/` is
    data/characters/<cid>/… with the db at data/eve1.db. Supporting both is not
    generosity — the archive that prompted this feature is the second kind.
    """
    if any(n.startswith("characters/") for n in names):
        return "characters/", (DB_MEMBER if DB_MEMBER in names else None)
    if any(n.startswith("data/characters/") for n in names):
        return "data/characters/", ("data/eve1.db" if "data/eve1.db" in names
                                    else None)
    raise BackupError("no characters/ folder in this archive — "
                      "is it a Throughline backup?")


def _legacy_manifest(tar: tarfile.TarFile, names: list[str], prefix: str,
                     db_member: str | None) -> dict:
    """Reconstruct a manifest for an archive that has none, by reading it."""
    chars: dict[str, dict] = {}
    for m in tar.getmembers():
        if not m.isfile() or not m.name.startswith(prefix):
            continue
        rest = m.name[len(prefix):].split("/")
        if len(rest) < 2:
            continue
        cid, top = rest[0], rest[1]
        c = chars.setdefault(cid, {"id": cid, "name": cid, "files": 0,
                                   "bytes": 0, "dirs": {}})
        c["files"] += 1
        c["bytes"] += m.size
        d = c["dirs"].setdefault(top, {"files": 0, "bytes": 0})
        d["files"] += 1
        d["bytes"] += m.size

    # The db is small; extracting just that member to count rows is far cheaper
    # than making the user guess whether the ledger came along.
    if db_member:
        with tempfile.TemporaryDirectory() as td:
            src = tar.extractfile(db_member)
            if src is not None:
                p = Path(td) / "eve1.db"
                with open(p, "wb") as fh:
                    shutil.copyfileobj(src, fh)
                try:
                    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
                    for cid, c in chars.items():
                        c["runs"] = con.execute(
                            "select count(*) from runs where character_id=?",
                            (cid,)).fetchone()[0]
                        c["wardrobe"] = con.execute(
                            "select count(*) from wardrobe where character_id=?",
                            (cid,)).fetchone()[0]
                        row = con.execute(
                            "select name from characters where id=?",
                            (cid,)).fetchone()
                        if row:
                            c["name"] = row[0]
                    con.close()
                except sqlite3.DatabaseError as exc:
                    raise BackupError(f"the database in this archive is not "
                                      f"readable: {exc}") from exc

    for c in chars.values():
        c.setdefault("runs", 0)
        c.setdefault("wardrobe", 0)
        c["gallery_entries"] = None
        c["threshold"] = None

    parts = [p for p, spec in PARTS.items()
             if any(d in c["dirs"] for c in chars.values() for d in spec["dirs"])]
    return {"schema": None, "parts": parts, "legacy": True,
            "characters": sorted(chars.values(), key=lambda c: c["id"]),
            "files": sum(c["files"] for c in chars.values()),
            "bytes": sum(c["bytes"] for c in chars.values())}


def inspect(path: str | Path) -> dict:
    """What is in this archive, and what would collide — without extracting.

    Everything the manual recovery had to derive by hand (which character, how
    many runs, how many gallery entries, what threshold) is answered here,
    before anything is written.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise BackupError(f"no such file: {p}")
    if not tarfile.is_tarfile(p):
        raise BackupError(f"{p.name} is not a tar archive")

    with tarfile.open(p, "r:*") as tar:
        names = tar.getnames()
        if MANIFEST in names:
            src = tar.extractfile(MANIFEST)
            man = json.loads(src.read().decode())
            man["legacy"] = False
        else:
            prefix, db_member = _members_layout(names)
            man = _legacy_manifest(tar, names, prefix, db_member)

    have = {c["id"] for c in db.chars_all()}
    for c in man["characters"]:
        c["conflict"] = c["id"] in have
    man["path"] = str(p)
    man["archive_bytes"] = p.stat().st_size
    man["conflicts"] = [c["id"] for c in man["characters"] if c["conflict"]]
    return man


# --------------------------------------------------------------------- restore

def _guard_jobs(exclude: str | None = None) -> None:
    """Refuse while anything is still running.

    Deliberately blunt: JOBS entries carry no character id, so there is no honest
    way to ask "is a job running for HER". A restore that swaps a folder out from
    under a generation mid-write is the kind of corruption that shows up days
    later as a missing file, so the conservative guard is the correct one.

    `exclude` is the restore's OWN job. Without it the guard sees the job that is
    running this very function and refuses itself — which it did, on the first
    end-to-end run.
    """
    from . import generate
    live = [j for j in generate.all_jobs()
            if not j["done"] and j["id"] != exclude]
    if live:
        what = ", ".join(f"{j['label']} ({j['stage']})" for j in live[:3])
        raise BackupError(f"{len(live)} job(s) still running — wait for them to "
                          f"finish before restoring: {what}")


def _safe_extract(tar: tarfile.TarFile, prefix: str, cid: str, into: Path) -> int:
    """Extract one character's files under `into`, rejecting anything strange.

    tarfile will happily write outside the destination given `../` or an absolute
    name. Restore takes a file the user was handed by someone else, so every
    member is checked rather than trusted.
    """
    root = prefix + cid + "/"
    n = 0
    for m in tar.getmembers():
        if not m.isfile() or not m.name.startswith(root):
            continue
        rel = Path(m.name[len(root):])
        if rel.is_absolute() or ".." in rel.parts:
            raise BackupError(f"refusing suspicious path in archive: {m.name}")
        dest = into / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = tar.extractfile(m)
        if src is None:
            continue
        with open(dest, "wb") as fh:
            shutil.copyfileobj(src, fh)
        n += 1
    return n


def _archive_rows(tar: tarfile.TarFile, db_member: str | None, cid: str):
    """(character row, run docs, wardrobe meta) for one character in an archive."""
    if not db_member:
        return None, [], {}
    src = tar.extractfile(db_member)
    if src is None:
        return None, [], {}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "eve1.db"
        with open(p, "wb") as fh:
            shutil.copyfileobj(src, fh)
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            crow = con.execute(
                "select id, name, created, doc from characters where id=?",
                (cid,)).fetchone()
            runs = [json.loads(d) for (d,) in con.execute(
                "select doc from runs where character_id=? order by seq", (cid,))]
            ward = {k: json.loads(d) for k, d in con.execute(
                "select key, doc from wardrobe where character_id=?", (cid,))}
        finally:
            con.close()
    return crow, runs, ward


def snapshot(cid: str, job: dict | None = None) -> str:
    """Full backup of one character into data/.snapshots/, before replacing her.

    A replace is the only irreversible thing here, so it is never the only copy.
    """
    out = config.DATA / ".snapshots"
    out.mkdir(parents=True, exist_ok=True)
    if job is not None:
        job["stage"] = f"snapshotting {cid}"
    return create(out, [cid], "all", job=job)["path"]


def restore(path: str | Path, decisions: list[dict],
            job: dict | None = None) -> dict:
    """Put characters from an archive onto this machine.

    `decisions` is [{archive_id, mode: "replace"|"new", name?}] — one per
    character the caller chose. Nothing is written until every decision has been
    validated, and each character's files land in a staging directory on the same
    filesystem and are swapped in by rename, so a failure halfway leaves the
    machine exactly as it was.
    """
    _guard_jobs(exclude=(job or {}).get("id"))
    man = inspect(path)
    by_id = {c["id"]: c for c in man["characters"]}
    p = Path(path).expanduser()

    for d in decisions:
        if d.get("archive_id") not in by_id:
            raise BackupError(f"{d.get('archive_id')!r} is not in this archive")
        if d.get("mode") not in ("replace", "new"):
            raise BackupError(f"mode must be 'replace' or 'new', got {d.get('mode')!r}")
        if d["mode"] == "replace" and not db.chars_get(d["archive_id"]):
            raise BackupError(f"cannot replace {d['archive_id']!r} — no such "
                              f"character here; use mode 'new'")

    from . import main as _main          # for _unique_char_id; imported late to
                                         # keep this module importable on its own
    # Peak usage is the extracted copy plus, for a replace, a full snapshot of
    # what is being overwritten.
    need = int(man["bytes"] * 1.05)
    if any(d["mode"] == "replace" for d in decisions):
        need += sum(_dir_stats(config.char_base(d["archive_id"]))[1]
                    for d in decisions if d["mode"] == "replace")
    preflight_disk(need, config.DATA)

    results = []
    staging = config.DATA / f".restoring-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(p, "r:*") as tar:
            prefix, db_member = _members_layout(tar.getnames())
            for d in decisions:
                acid = d["archive_id"]
                src_info = by_id[acid]
                if job is not None:
                    job["stage"] = f"restoring {acid}"

                if d["mode"] == "replace":
                    target = acid
                    snap = snapshot(target, job=job)
                else:
                    name = (d.get("name") or src_info.get("name") or acid).strip()
                    target = _main._unique_char_id(name)
                    snap = None

                pen = staging / target
                pen.mkdir(parents=True, exist_ok=True)
                n = _safe_extract(tar, prefix, acid, pen)

                crow, runs, ward = _archive_rows(tar, db_member, acid)
                if d["mode"] == "new":
                    runs = _remint(runs, pen)

                # WHAT THIS ARCHIVE ACTUALLY CARRIES. Everything below is scoped
                # to it, because an identity-only archive restored over a live
                # character must not take her images and wardrobe with it. The
                # first version of this function moved the whole folder into
                # place and deleted the rest — 573 images and 141 outfits the
                # archive never claimed to hold.
                carried = {p.name for p in pen.iterdir() if p.is_dir()}

                # Files first, then the db, so a crash leaves files with no rows
                # (invisible, recoverable) rather than rows with no files
                # (broken thumbnails everywhere).
                live = config.char_base(target)
                live.mkdir(parents=True, exist_ok=True)
                # The displaced originals stay on disk until the ledger commits,
                # so a failure below is a rename back rather than a restore from
                # the snapshot.
                displaced = staging / f"displaced-{target}"
                displaced.mkdir(parents=True, exist_ok=True)
                moved: list[tuple[Path, Path]] = []
                try:
                    for sub in sorted(carried):
                        src_dir, live_dir = pen / sub, live / sub
                        if live_dir.exists():
                            live_dir.rename(displaced / sub)
                            moved.append((displaced / sub, live_dir))
                        src_dir.rename(live_dir)
                    config.ensure_char_dirs(target)
                    _write_rows(target, crow, runs, ward,
                                name=(d.get("name") or (crow[1] if crow else target)),
                                # Not `bool(db_member)`: the db member is in
                                # EVERY archive, so that replaced the ledger on
                                # an identity-only restore and rewound `mark`.
                                # The ledger describes images, so only an
                                # archive carrying images may replace it.
                                carries_runs=bool(db_member) and "images" in carried,
                                carries_wardrobe="wardrobe" in carried)
                except Exception:
                    # Put back exactly what was moved, newest first.
                    for was, now in reversed(moved):
                        if now.exists():
                            shutil.rmtree(now, ignore_errors=True)
                        was.rename(now)
                    raise

                # Caches are keyed on mtime and are NOT in the archive; a stale
                # one beside a restored source is how she keeps the wrong face.
                _drop_caches(live)
                results.append({"archive_id": acid, "restored_as": target,
                                "mode": d["mode"], "files": n,
                                "restored": sorted(carried),
                                "kept": sorted(
                                    {p.name for p in live.iterdir() if p.is_dir()}
                                    - carried - SKIP_DIRS),
                                "runs": len(runs), "wardrobe": len(ward),
                                "snapshot": snap})
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if job is not None:
        job["step"] = None
    return {"restored": results, "source": str(p)}


def _drop_caches(live: Path) -> None:
    """Remove derived caches under a freshly restored character.

    They are excluded from archives, so anything here predates the restore and is
    keyed on an mtime that no longer means what it did. All of it rebuilds on the
    next request.
    """
    for d in live.rglob("*"):
        if d.is_dir() and d.name in SKIP_DIRS:
            shutil.rmtree(d, ignore_errors=True)
    for p in (live / "state").glob(".avatar-*.jpg"):
        p.unlink(missing_ok=True)


def _remint(runs: list[dict], folder: Path) -> list[dict]:
    """New run ids for a side-by-side restore.

    `runs.id` is UNIQUE across the whole database, so restoring an archive next
    to the character it came from collides on EVERY row — not an edge case, the
    guaranteed outcome of the main use case. `INSERT OR IGNORE` would be the
    quiet disaster here: it inserts nothing and reports success, leaving a
    character with a gigabyte of images and an empty ledger.

    The image file is renamed too: `file` == `id` + extension holds for every row
    in this project, and a restored copy that silently broke the invariant would
    be a trap for whoever next relied on it.
    """
    # Two passes: the map has to be complete before rewriting, because a video
    # row's meta.from_run (generate.py:894) can point at a run that appears later
    # in the file.
    remap = {r["id"]: uuid.uuid4().hex[:10] for r in runs if r.get("id")}
    out = []
    for r in runs:
        r = dict(r)
        old = r.get("id")
        new = remap.get(old, old)
        r["id"] = new
        # Provenance, in the house style: where this row came from.
        if old and old != new:
            r["restored_from"] = old
        meta = r.get("meta")
        if isinstance(meta, dict) and meta.get("from_run") in remap:
            r["meta"] = {**meta, "from_run": remap[meta["from_run"]]}
        f = r.get("file") or ""
        if old and f.startswith(old):
            src = folder / "images" / f
            renamed = new + f[len(old):]
            if src.exists():
                src.rename(folder / "images" / renamed)
            r["file"] = renamed
        out.append(r)
    return out


def _write_rows(cid: str, crow, runs: list[dict], ward: dict, name: str,
                carries_runs: bool, carries_wardrobe: bool) -> None:
    """Land one character's ledger, touching ONLY the tables the archive carries.

    Deliberately not `db.chars_delete()`, which drops runs and wardrobe and the
    character row unconditionally. Using it here would mean restoring an
    identity-only archive over a live character destroyed 359 `mark` verdicts and
    109 outfit rows the archive never claimed to hold — and the marks are the only
    record of the one axis the gate is blind to, so they are not regenerable.
    """
    created = (crow[2] if crow else None) or time.strftime("%Y-%m-%dT%H:%M:%S")
    doc = (crow[3] if crow else None) or "{}"
    # Written directly rather than through chars_create so she keeps her real
    # creation date and doc instead of being born again on restore.
    with db._conn() as con:                                 # noqa: SLF001
        # IMMEDIATE takes the write lock up front, so the missing-file sweeper's
        # runs_update waits on busy_timeout instead of colliding halfway through.
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM characters WHERE id=?", (cid,))
        con.execute("INSERT INTO characters (id, name, created, doc) "
                    "VALUES (?, ?, ?, ?)", (cid, name, created, doc))
        if carries_runs:
            # REPLACE — only when the archive actually carries the images these
            # rows describe. Rolling the ledger back is then what was asked for.
            con.execute("DELETE FROM runs WHERE character_id=?", (cid,))
            con.executemany(
                "INSERT INTO runs (id, character_id, doc) VALUES (?, ?, ?)",
                [(r["id"], cid, json.dumps(r)) for r in runs])
        elif runs:
            # ADDITIVE — the run ledger rides in every archive ("the run ledger
            # travels either way", PARTS["images"]), but an identity-only
            # restore did not ask to roll back the ledger. Replacing it here
            # rewound `mark` to whatever it was at backup time: measured on this
            # machine, restoring a 2026-09-04 identity archive over the live db
            # dropped 186 approvals to 18. The marks are the only record of the
            # one axis the gate is blind to and are not regenerable.
            #
            # INSERT OR IGNORE keeps both cases right: a fresh machine (the
            # recovery case this feature was built for) still gets the whole
            # ledger, and an existing character keeps every verdict she has.
            con.executemany(
                "INSERT OR IGNORE INTO runs (id, character_id, doc) "
                "VALUES (?, ?, ?)",
                [(r["id"], cid, json.dumps(r)) for r in runs])
        if carries_wardrobe:
            con.execute("DELETE FROM wardrobe WHERE character_id=?", (cid,))
            con.executemany(
                "INSERT INTO wardrobe (character_id, key, doc) VALUES (?, ?, ?)",
                [(cid, k, json.dumps(v)) for k, v in ward.items()])
        con.execute("COMMIT")
