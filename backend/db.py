"""SQLite persistence for the list-shaped ledgers: runs, wardrobe meta,
and (phase 4) the character registry.

WHY IT EXISTS — not speed. The real fix is a concurrency bug: record_run ran
read-whole-file -> append -> write-whole-file from a daemon thread, and the queue
runs jobs in parallel, so two simultaneous finishes could clobber each other and
silently lose a run. An atomic single-row INSERT makes that impossible.

PHASE 4 — multi-character. runs / wardrobe now carry a character_id, and
every read/write is scoped to the ACTIVE character (config.get_active()). The DB
itself is GLOBAL (data/eve1.db) so listing characters and their ledgers is one
query; each character's FILES live under data/characters/<id>/ (see config.py).

init_db() is idempotent and also performs the one-time migration of the old
single-character layout (data/images, data/state/…, and the old
data/state/eve1.db) into data/characters/kiara/ + the global db.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import config
from .config import CHARACTERS, DATA, DEFAULT_CHARACTER

DB_PATH = DATA / "eve1.db"          # GLOBAL — not per character


@contextmanager
def _conn():
    """A fresh connection per call — the only thread-safe pattern for the daemon
    workers, since a sqlite3 connection must not cross threads. busy_timeout makes
    a concurrent writer wait for the lock instead of raising 'database is locked'."""
    con = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    con.execute("PRAGMA busy_timeout=30000")
    try:
        yield con
    finally:
        con.close()


# ============================================================ init + migration
def init_db() -> None:
    _migrate_files_to_multichar()
    with _conn() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""CREATE TABLE IF NOT EXISTS runs (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id  TEXT UNIQUE NOT NULL,
            character_id TEXT,
            doc TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS wardrobe (
            character_id TEXT NOT NULL,
            key TEXT NOT NULL,
            doc TEXT NOT NULL,
            PRIMARY KEY (character_id, key))""")
        con.execute("""CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created TEXT,
            doc TEXT)""")
    _migrate_schema_add_character()
    _seed_characters()


def _move_children(src: Path, dest: Path) -> None:
    """Move every entry of src into dest (dest is a freshly-created empty dir), so
    an existing empty dest doesn't cause shutil.move to nest the source inside it."""
    dest.mkdir(parents=True, exist_ok=True)
    for child in list(src.iterdir()):
        target = dest / child.name
        if not target.exists():
            shutil.move(str(child), str(target))


def _migrate_files_to_multichar() -> None:
    """One-time: relocate the old single-character layout into characters/kiara/
    and lift the global db out of state/. Guarded by a marker file."""
    marker = DATA / ".multichar_v1"
    if marker.exists():
        return
    kiara = CHARACTERS / DEFAULT_CHARACTER
    config.ensure_char_dirs(DEFAULT_CHARACTER)

    # 1) lift the global db out of the old per-character state/ folder
    for suf in ("", "-wal", "-shm"):
        old_db = DATA / "state" / f"eve1.db{suf}"
        new_db = DATA / f"eve1.db{suf}"
        if old_db.exists() and not new_db.exists():
            shutil.move(str(old_db), str(new_db))

    # 2) the per-character asset folders
    for name in ("images", "refs", "wardrobe", "pose-refs", "poses",
                 "bodies", "gold"):
        old = DATA / name
        if old.exists() and old.is_dir():
            _move_children(old, kiara / name)

    # 3) the per-character state files (gallery.npz/json, bio, parts, threshold,
    #    bodies, and the JSON backups) — everything in state/ except the db
    old_state = DATA / "state"
    if old_state.exists():
        dest_state = kiara / "state"
        dest_state.mkdir(parents=True, exist_ok=True)
        for f in list(old_state.iterdir()):
            if f.name.startswith("eve1.db"):
                continue
            target = dest_state / f.name
            if not target.exists():
                shutil.move(str(f), str(target))

    marker.write_text("migrated to per-character layout\n")


def _has_column(con, table: str, col: str) -> bool:
    return any(r[1] == col for r in con.execute(f"PRAGMA table_info({table})"))


def _table_exists(con, table: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (table,)).fetchone() is not None


def _migrate_schema_add_character() -> None:
    """Backfill character_id on ledgers created before phase 4, stamping the
    pre-existing rows as the default character. Idempotent."""
    with _conn() as con:
        for t in ("runs",):
            if _table_exists(con, t) and not _has_column(con, t, "character_id"):
                con.execute(f"ALTER TABLE {t} ADD COLUMN character_id TEXT")
                con.execute(f"UPDATE {t} SET character_id=? WHERE character_id IS NULL",
                            (DEFAULT_CHARACTER,))
        # older runs rows may still be NULL even if the column exists
        for t in ("runs",):
            if _table_exists(con, t) and _has_column(con, t, "character_id"):
                con.execute(f"UPDATE {t} SET character_id=? WHERE character_id IS NULL",
                            (DEFAULT_CHARACTER,))
        # wardrobe: old schema had PK(key) with no character_id — rebuild it
        if _table_exists(con, "wardrobe") and not _has_column(con, "wardrobe", "character_id"):
            con.execute("BEGIN")
            con.execute("ALTER TABLE wardrobe RENAME TO _wardrobe_old")
            con.execute("""CREATE TABLE wardrobe (
                character_id TEXT NOT NULL, key TEXT NOT NULL, doc TEXT NOT NULL,
                PRIMARY KEY (character_id, key))""")
            con.execute("INSERT INTO wardrobe (character_id, key, doc) "
                        "SELECT ?, key, doc FROM _wardrobe_old", (DEFAULT_CHARACTER,))
            con.execute("DROP TABLE _wardrobe_old")
            con.execute("COMMIT")


def _seed_characters() -> None:
    """Ensure a characters row exists for the default character and for any folder
    already present under data/characters/."""
    folders = [p.name for p in CHARACTERS.iterdir() if p.is_dir()] if CHARACTERS.exists() else []
    want = set(folders) | {DEFAULT_CHARACTER}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _conn() as con:
        existing = {r[0] for r in con.execute("SELECT id FROM characters")}
        for cid in want:
            if cid not in existing:
                name = cid.replace("-", " ").replace("_", " ").title()
                con.execute("INSERT OR IGNORE INTO characters (id, name, created, doc) "
                            "VALUES (?, ?, ?, ?)", (cid, name, now, "{}"))


# =================================================================== runs
def runs_all(newest_first: bool = False, character_id: str | None = None) -> list[dict]:
    """Every run for a character. `character_id` names one explicitly — the
    roster asks about characters that are not the active one, and a listing that
    silently answered for whoever happened to be active would be worse than an
    error."""
    order = "DESC" if newest_first else "ASC"
    cid = character_id or config.get_active()
    with _conn() as con:
        rows = con.execute(f"SELECT doc FROM runs WHERE character_id=? ORDER BY seq {order}",
                           (cid,)).fetchall()
    return [json.loads(d) for (d,) in rows]


def runs_insert(row: dict, character_id: str | None = None) -> dict:
    """Atomic single-row append. character_id is pinned by the caller (the
    character the generation STARTED under) so switching the active character
    mid-render can never misfile the result; falls back to the active one."""
    cid = character_id or config.get_active()
    with _conn() as con:
        con.execute("INSERT INTO runs (id, character_id, doc) VALUES (?, ?, ?)",
                    (row["id"], cid, json.dumps(row)))
    return row


def runs_all_everywhere(newest_first: bool = True) -> list[dict]:
    """Every run for EVERY character. Deliberately unscoped.

    runs_all() answers for one character, which is right for listing and wrong
    for maintenance: a missing download belongs to whoever generated it, not to
    whoever is on screen now, and the refetch sweeper must not lose a parked
    image because the user clicked another character.
    """
    order = "DESC" if newest_first else "ASC"
    with _conn() as con:
        rows = con.execute(f"SELECT doc FROM runs ORDER BY seq {order}").fetchall()
    # _conn() sets no row_factory, so rows are plain tuples — index, don't key.
    return [json.loads(r[0]) for r in rows]


def runs_owner(run_id: str) -> tuple[dict, str] | None:
    """One run by id, ACROSS characters, with the character that owns it.

    Every other read here is scoped to the active character, which is right for
    listing but wrong for acting on a specific run. "Save this outfit" arrives
    minutes after the image was generated, and if the active character moved in
    between — another tab, another window — the lookup found nothing and the
    endpoint returned 404 for a run that plainly exists. A run id is globally
    unique, so resolve it globally and let the caller act on its real owner.
    """
    with _conn() as con:
        r = con.execute("SELECT doc, character_id FROM runs WHERE id=?", (run_id,)).fetchone()
    return (json.loads(r[0]), r[1]) if r else None


def runs_update(run_id: str, row: dict) -> dict:
    """Blind whole-document write. Prefer `runs_patch` for anything that ran
    concurrently with a human — see the note there."""
    with _conn() as con:
        cur = con.execute("UPDATE runs SET doc=? WHERE id=?", (json.dumps(row), run_id))
        if cur.rowcount == 0:
            raise KeyError(run_id)
    return row


def runs_patch(run_id: str, **fields) -> dict:
    """Merge FIELDS into one run, re-reading it inside the write lock.

    `runs_update` writes back a whole document the caller has been holding, and
    the missing-file sweeper (main.py `_sweep_missing`) holds one for MINUTES —
    it snapshots every row, then does network I/O per row, then writes. A mark
    clicked inside that window is silently reverted to whatever it was when the
    sweep began: no error, no trace, and `mark` is the one field in this project
    that cannot be regenerated. It is the only record of the axis the gate is
    blind to (her body), which is exactly why it is a human verdict at all.

    BEGIN IMMEDIATE takes the write lock before the SELECT, so the read and the
    write are one atomic step and a concurrent patch waits on busy_timeout
    rather than interleaving. Callers pass only what they changed, so nothing
    they never looked at can be clobbered.
    """
    with _conn() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            r = con.execute("SELECT doc FROM runs WHERE id=?", (run_id,)).fetchone()
            if r is None:
                raise KeyError(run_id)
            doc = json.loads(r[0])
            doc.update(fields)
            con.execute("UPDATE runs SET doc=? WHERE id=?",
                        (json.dumps(doc), run_id))
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    return doc


def runs_delete(ids: set[str]) -> list[dict]:
    if not ids:
        return []
    cid = config.get_active()
    marks = ",".join("?" * len(ids))
    with _conn() as con:
        con.execute("BEGIN")
        rows = con.execute(
            f"SELECT doc FROM runs WHERE character_id=? AND id IN ({marks})",
            (cid, *ids)).fetchall()
        removed = [json.loads(d) for (d,) in rows]
        if removed:
            con.execute(f"DELETE FROM runs WHERE character_id=? AND id IN ({marks})",
                        (cid, *ids))
        con.execute("COMMIT")
    return removed


# ================================================================ wardrobe
def wardrobe_meta(character_id: str | None = None) -> dict:
    """{stem: {description, created}} for a character — the active one unless
    named. Promoting a run must write to the character that OWNS the run, which
    is not always the one on screen."""
    cid = character_id or config.get_active()
    with _conn() as con:
        rows = con.execute("SELECT key, doc FROM wardrobe WHERE character_id=?",
                           (cid,)).fetchall()
    return {k: json.loads(d) for k, d in rows}


def wardrobe_save_all(meta: dict, character_id: str | None = None) -> None:
    """Replace one character's wardrobe meta (writes are serial + user-driven)."""
    cid = character_id or config.get_active()
    with _conn() as con:
        con.execute("BEGIN")
        con.execute("DELETE FROM wardrobe WHERE character_id=?", (cid,))
        con.executemany("INSERT INTO wardrobe (character_id, key, doc) VALUES (?, ?, ?)",
                        [(cid, k, json.dumps(v)) for k, v in meta.items()])
        con.execute("COMMIT")


# =============================================================== characters
def chars_all() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT id, name, created FROM characters ORDER BY created").fetchall()
    return [{"id": i, "name": n, "created": c} for i, n, c in rows]


def chars_get(cid: str) -> dict | None:
    with _conn() as con:
        r = con.execute("SELECT id, name, created FROM characters WHERE id=?", (cid,)).fetchone()
    return {"id": r[0], "name": r[1], "created": r[2]} if r else None


def chars_create(cid: str, name: str) -> dict:
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _conn() as con:
        con.execute("INSERT INTO characters (id, name, created, doc) VALUES (?, ?, ?, ?)",
                    (cid, name, now, "{}"))
    return {"id": cid, "name": name, "created": now}


def chars_doc(cid: str) -> dict:
    with _conn() as con:
        r = con.execute("SELECT doc FROM characters WHERE id=?", (cid,)).fetchone()
    try:
        return json.loads(r[0]) if r and r[0] else {}
    except ValueError:
        return {}


def chars_set_doc(cid: str, **fields) -> dict:
    """Merge fields into a character's doc.

    The doc is where a character's own bookkeeping lives — currently the id of
    the build job that created her. That has to be DURABLE: the job registry is
    in memory, so a page reload (or a backend restart) used to lose all track of
    a creation in flight, leaving a half-built character with no way to tell
    whether anything was still working on her.
    """
    doc = chars_doc(cid) | {k: v for k, v in fields.items() if v is not None}
    for k, v in fields.items():
        if v is None:
            doc.pop(k, None)
    with _conn() as con:
        con.execute("UPDATE characters SET doc=? WHERE id=?", (json.dumps(doc), cid))
    return doc


def chars_update(cid: str, name: str) -> bool:
    """Rename a character (display name only; the id/folder stay). Returns False
    if no such character."""
    with _conn() as con:
        cur = con.execute("UPDATE characters SET name=? WHERE id=?", (name, cid))
    return cur.rowcount > 0


def chars_delete(cid: str) -> None:
    """Remove a character and all of its ledger rows (files are handled by caller)."""
    with _conn() as con:
        con.execute("BEGIN")
        con.execute("DELETE FROM runs WHERE character_id=?", (cid,))
        con.execute("DELETE FROM wardrobe WHERE character_id=?", (cid,))
        con.execute("DELETE FROM characters WHERE id=?", (cid,))
        con.execute("COMMIT")


def runs_reserve(run_id: str, character_id: str, doc: dict) -> bool:
    """Claim a run id BEFORE the money is spent. True if we claimed it.

    The ledger row used to be written only after the provider returned, the
    image downloaded, the gate scored it and the archive re-encoded it —
    minutes after the spend. Everything in between was a hole: kill the server
    (run.sh uses --reload, so an edit is enough) and the provider still renders
    and still bills, but there is no row, no task id and no file, and nothing
    can ever find it again. main.py's own comment records this happening:
    "five /api/shot calls, four rows, one finished and billed poyo image
    reachable only by hand."

    So the row goes in first, `status='pending'`, and every later stage patches
    it. A crash now leaves evidence the sweeper can act on instead of silence.

    INSERT OR IGNORE, not INSERT: the id may already be claimed by an
    idempotent retry of the same request, and stepping on it would be the very
    duplicate-spend this exists to prevent.
    """
    with _conn() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO runs (id, character_id, doc) VALUES (?, ?, ?)",
            (run_id, character_id, json.dumps(doc)))
        return cur.rowcount == 1


def runs_find_by_token(character_id: str, token: str) -> dict | None:
    """The row a previous identical submission already created, if any.

    Idempotency for a generation that costs real money. Without it a double
    click, a refresh-resubmit or a proxy retry each start their own provider
    call and each get billed — and the UI makes that likely, because a browser
    refresh mid-shot loses the job id and the obvious response is to press
    Generate again.
    """
    if not token:
        return None
    with _conn() as con:
        r = con.execute(
            "SELECT doc FROM runs WHERE character_id=? "
            "AND json_extract(doc,'$.client_token')=? "
            "ORDER BY seq DESC LIMIT 1", (character_id, token)).fetchone()
    return json.loads(r[0]) if r else None
