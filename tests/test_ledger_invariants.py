"""The run ledger must not lose a human verdict.

`mark` is the only record of the axis the gate is blind to — her BODY, which
person re-ID cannot judge because it keys on clothing and clothing varies by
design (CLAUDE.md, "The spine"). The gate's numbers are reproducible; the marks
are not. Nothing else in this project has that property.

They were nearly lost twice, both times to the same shape of bug: a writer that
held a whole run document, went away to do slow work, and wrote the stale copy
back over whatever a human had done meanwhile.

  * `_sweep_missing` (main.py) snapshots EVERY row, then does network I/O per
    row for minutes, then writes each document back.
  * `generate.mark` itself loaded every run, edited one dict, and wrote the
    whole document — so it could equally be the loser or the clobberer.

`db.runs_patch` closes both by re-reading the row inside BEGIN IMMEDIATE and
merging only the named fields. These tests hold that line: they fail loudly on
`runs_update`, which is what the code used to do.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

import pytest

from backend import db


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    """A throwaway eve1.db with one run, wired through db's module constants."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(db, "DATA", data)
    monkeypatch.setattr(db, "DB_PATH", data / "eve1.db")

    con = sqlite3.connect(data / "eve1.db")
    con.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE runs (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                           id TEXT UNIQUE NOT NULL, doc TEXT NOT NULL,
                           character_id TEXT);
    """)
    con.execute("INSERT INTO runs (id, character_id, doc) VALUES (?,?,?)",
                ("r1", "kiara", json.dumps(
                    {"id": "r1", "file": "r1.webp", "mark": None,
                     "source_url": None, "meta": {"pose_id": "front"}})))
    con.commit()
    con.close()
    return data / "eve1.db"


def _doc(path, rid="r1"):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return json.loads(con.execute(
            "SELECT doc FROM runs WHERE id=?", (rid,)).fetchone()[0])
    finally:
        con.close()


def test_patch_touches_only_the_named_fields(ledger):
    db.runs_patch("r1", source_url="https://x/y.png", credits=24)
    d = _doc(ledger)
    assert d["source_url"] == "https://x/y.png"
    assert d["credits"] == 24
    # everything it did not name survives untouched
    assert d["file"] == "r1.webp"
    assert d["meta"] == {"pose_id": "front"}


def test_a_stale_sweeper_cannot_revert_a_mark(ledger):
    """THE bug. The sweeper reads a row, goes away for minutes, writes back.

    Reproduced in the order it actually happens: snapshot -> human marks ->
    sweeper writes. With the old whole-document write the approval is gone.
    """
    stale = _doc(ledger)                    # sweeper's snapshot, mark=None
    assert stale["mark"] is None

    db.runs_patch("r1", mark="approve")     # the human, mid-sweep

    # the sweeper finishes its network call and records what it healed
    db.runs_patch("r1", source_url="https://x/healed.png", pending_tasks=None)

    d = _doc(ledger)
    assert d["mark"] == "approve", "the sweeper reverted a human verdict"
    assert d["source_url"] == "https://x/healed.png", "the heal was lost"

    # and prove the old form is what broke it, so this test cannot be
    # satisfied by quietly reintroducing runs_update here
    stale["source_url"] = "https://x/healed.png"
    db.runs_update("r1", stale)
    assert _doc(ledger)["mark"] is None, (
        "runs_update no longer clobbers — this test's premise is stale")


def test_concurrent_patches_do_not_lose_each_other(ledger):
    """Two threads, two fields, both must survive.

    FastAPI runs `def` endpoints in a threadpool and the sweeper is its own
    daemon thread, so this genuinely happens rather than being theoretical.
    """
    errors: list[BaseException] = []

    def hammer(field, value, n=25):
        try:
            for i in range(n):
                db.runs_patch("r1", **{field: f"{value}{i}"})
                time.sleep(0.001)
        except BaseException as e:          # noqa: BLE001 — surface in the test
            errors.append(e)

    a = threading.Thread(target=hammer, args=("mark", "approve"))
    b = threading.Thread(target=hammer, args=("source_url", "url"))
    a.start(); b.start(); a.join(); b.join()

    assert not errors, f"a concurrent patch raised: {errors[0]!r}"
    d = _doc(ledger)
    assert d["mark"] == "approve24"
    assert d["source_url"] == "url24"


def test_patch_on_a_missing_run_raises_rather_than_inserting(ledger):
    with pytest.raises(KeyError):
        db.runs_patch("nope", mark="approve")
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        assert con.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
    finally:
        con.close()
