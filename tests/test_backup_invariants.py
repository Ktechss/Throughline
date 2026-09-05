"""Backup must not be able to lose what it was asked to protect.

Every case here is a way this feature can destroy data while reporting success —
which is the only failure mode that matters for a backup tool, because a loud
failure just means you run it again.

Three of them were real bugs in the first draft of `backend/backup.py`:

  * restoring an identity-only archive over a live character moved the whole
    folder into place and deleted the rest, taking 573 images and 141 wardrobe
    files the archive never claimed to carry.
  * the same restore dropped every `runs` and `wardrobe` row for that character,
    including 359 `mark` verdicts — the only record of the axis the gate is
    blind to, and the one thing here that is not regenerable.
  * side-by-side restore reused the archive's run ids, which are UNIQUE across
    the whole database, so restoring a character next to herself collided on
    every row.

The suite builds a small synthetic character in a tmp dir; nothing touches the
real data/, no network, no models.
"""
import json
import sqlite3
import tarfile
from pathlib import Path

import numpy as np
import pytest

from backend import backup


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """A throwaway data/ with one character, wired through both modules.

    config and db each bind their own module-level path constants at import, so
    both have to be redirected or the test writes into the real studio.
    """
    from backend import config, db

    data = tmp_path / "data"
    chars = data / "characters"
    chars.mkdir(parents=True)

    for mod, name, val in ((config, "DATA", data), (config, "CHARACTERS", chars),
                           (db, "DATA", data), (db, "CHARACTERS", chars),
                           (db, "DB_PATH", data / "eve1.db")):
        monkeypatch.setattr(mod, name, val)
    monkeypatch.setattr(config, "_active_id", "kiara", raising=False)
    monkeypatch.setattr(config, "get_active", lambda: "kiara")

    base = chars / "kiara"
    for d in ("state", "refs", "bodies", "places", "nails", "wardrobe", "images"):
        (base / d).mkdir(parents=True)

    (base / "state" / "bio.json").write_text(json.dumps(
        {"reference": "face.webp", "body_reference": "body.webp"}))
    (base / "state" / "parts.json").write_text(json.dumps({"parts": ["her"]}))
    (base / "state" / "threshold.json").write_text(json.dumps({"threshold": 0.58}))
    (base / "state" / "gallery.json").write_text(json.dumps(
        {"front": {}, "tq-left": {}}))
    np.savez(base / "state" / "gallery.npz", front=np.zeros(512))
    # A derived cache that must never travel: it is validated by mtime, and tar
    # restores the original, so a stale copy would out-rank a restored face.
    (base / "state" / ".avatar-face.jpg").write_bytes(b"cache")
    (base / "refs" / "face.webp").write_bytes(b"face")
    (base / "bodies" / "body.webp").write_bytes(b"body")
    (base / "places" / "kitchen.webp").write_bytes(b"kitchen")
    (base / "wardrobe" / "saree.webp").write_bytes(b"saree")
    for rid in ("aaaa000001", "bbbb000002"):
        (base / "images" / f"{rid}.webp").write_bytes(b"shot")

    con = sqlite3.connect(data / "eve1.db")
    con.executescript("""
        CREATE TABLE runs (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                           id TEXT UNIQUE NOT NULL, doc TEXT NOT NULL,
                           character_id TEXT);
        CREATE TABLE wardrobe (character_id TEXT NOT NULL, key TEXT NOT NULL,
                               doc TEXT NOT NULL, PRIMARY KEY (character_id, key));
        CREATE TABLE characters (id TEXT PRIMARY KEY, name TEXT NOT NULL,
                                 created TEXT, doc TEXT);
    """)
    con.execute("INSERT INTO characters VALUES ('kiara','Kiara','2026-07-24','{}')")
    con.execute("INSERT INTO runs (id, character_id, doc) VALUES (?,?,?)",
                ("aaaa000001", "kiara",
                 json.dumps({"id": "aaaa000001", "file": "aaaa000001.webp",
                             "mark": "approve"})))
    # A video row pointing at the run above — the reference that must be rewritten
    # when ids are re-minted.
    con.execute("INSERT INTO runs (id, character_id, doc) VALUES (?,?,?)",
                ("bbbb000002", "kiara",
                 json.dumps({"id": "bbbb000002", "file": "bbbb000002.webp",
                             "mark": None, "meta": {"from_run": "aaaa000001"}})))
    con.execute("INSERT INTO wardrobe VALUES ('kiara','saree','{\"desc\":\"a saree\"}')")
    con.commit()
    con.close()
    return {"data": data, "base": base, "out": tmp_path / "out"}


def _rows(sandbox, sql, args=()):
    con = sqlite3.connect(sandbox["data"] / "eve1.db")
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


# ------------------------------------------------------------------ taxonomy

def test_wardrobe_rows_and_images_are_inseparable():
    """Rows without images is broken thumbnails; images without rows is a folder
    the app cannot see. One part must govern both."""
    assert "wardrobe" in backup.PARTS["wardrobe"]["dirs"]
    assert "wardrobe" in backup.PARTS["wardrobe"]["rows"]
    for key, spec in backup.PARTS.items():
        if key != "wardrobe":
            assert not spec["rows"], f"{key} carries rows without owning its files"


def test_identity_is_never_optional():
    """An archive without bio + part tree is a folder of outfits with nobody in
    it, so identity is forced in rather than validated out."""
    assert backup.normalise(["images"]) [0] == "identity"
    assert backup.PARTS["identity"]["required"] is True
    dirs = backup.PARTS["identity"]["dirs"]
    for must in ("state", "refs", "bodies", "places"):
        assert must in dirs


# -------------------------------------------------------------- archive shape

def test_manifest_is_the_first_member(sandbox):
    """Inspect must be one small read, not a scan of 11 GB."""
    r = backup.create(sandbox["out"], ["kiara"], "all")
    with tarfile.open(r["path"]) as tar:
        assert tar.next().name == backup.MANIFEST


def test_derived_caches_never_travel(sandbox):
    """A restored source with an old mtime beside a newer cache means she keeps
    the wrong face permanently (main.py:1272)."""
    r = backup.create(sandbox["out"], ["kiara"], "all")
    with tarfile.open(r["path"]) as tar:
        assert not [n for n in tar.getnames() if ".avatar-" in n]


def test_round_trip_preserves_the_gate_yardstick(sandbox):
    r = backup.create(sandbox["out"], ["kiara"], "identity")
    m = backup.inspect(r["path"])
    c = m["characters"][0]
    assert c["gallery_entries"] == 2
    assert c["threshold"] == 0.58
    assert c["runs"] == 2
    assert c["conflict"] is True


# ------------------------------------------------- the three data-loss bugs

def test_identity_restore_keeps_images_and_wardrobe(sandbox):
    """THE bug: an identity-only archive restored over her must not take the
    images and outfits it never claimed to carry."""
    r = backup.create(sandbox["out"], ["kiara"], "identity")
    backup.restore(r["path"], [{"archive_id": "kiara", "mode": "replace"}])

    base = sandbox["base"]
    assert (base / "images" / "aaaa000001.webp").exists()
    assert (base / "wardrobe" / "saree.webp").exists()


def test_identity_restore_keeps_the_mark_verdicts(sandbox):
    """The marks are the only record of the axis the gate is blind to."""
    r = backup.create(sandbox["out"], ["kiara"], "identity")
    backup.restore(r["path"], [{"archive_id": "kiara", "mode": "replace"}])

    marks = _rows(sandbox, "select doc from runs where character_id='kiara'")
    assert len(marks) == 2
    assert any(json.loads(d)["mark"] == "approve" for (d,) in marks)
    assert _rows(sandbox, "select count(*) from wardrobe")[0][0] == 1


def test_identity_restore_does_not_rewind_marks_made_since_the_backup(sandbox):
    """The test above cannot catch a rollback: it restores the archive it just
    made, so the archive's marks and the live marks are identical by
    construction. The bug only appears once the ledger has MOVED ON.

    Measured on the real studio before this was fixed: restoring
    kiara-20260904-1748-identity.tar over the live db took 186 approvals down
    to 18 — 168 human verdicts destroyed by a restore that only claimed to
    carry her face, body and rooms.
    """
    r = backup.create(sandbox["out"], ["kiara"], "identity")

    # Time passes; she gets reviewed. bbbb000002 was unmarked at backup time.
    con = sqlite3.connect(sandbox["data"] / "eve1.db")
    con.execute("UPDATE runs SET doc=? WHERE id='bbbb000002'",
                (json.dumps({"id": "bbbb000002", "file": "bbbb000002.webp",
                             "mark": "approve",
                             "meta": {"from_run": "aaaa000001"}}),))
    con.commit(); con.close()

    backup.restore(r["path"], [{"archive_id": "kiara", "mode": "replace"}])

    docs = {json.loads(d)["id"]: json.loads(d)
            for (d,) in _rows(sandbox, "select doc from runs "
                                       "where character_id='kiara'")}
    assert docs["bbbb000002"]["mark"] == "approve", (
        "an identity-only restore rewound a verdict made after the backup")
    assert docs["aaaa000001"]["mark"] == "approve"


def test_identity_restore_still_seeds_the_ledger_on_a_fresh_machine(sandbox):
    """The additive path must not break the case the feature exists for.

    Recovering onto a machine that has never seen her — no rows at all — must
    still land the whole ledger, or `mark` history is lost a different way.
    """
    r = backup.create(sandbox["out"], ["kiara"], "identity")

    con = sqlite3.connect(sandbox["data"] / "eve1.db")
    con.execute("DELETE FROM runs WHERE character_id='kiara'")
    con.commit(); con.close()

    backup.restore(r["path"], [{"archive_id": "kiara", "mode": "replace"}])

    rows = _rows(sandbox, "select doc from runs where character_id='kiara'")
    assert len(rows) == 2, "a fresh-machine restore lost the run ledger"
    assert any(json.loads(d)["mark"] == "approve" for (d,) in rows)


def test_side_by_side_restore_does_not_collide_on_run_ids(sandbox):
    """runs.id is UNIQUE globally, so restoring her next to herself collides on
    every row. INSERT OR IGNORE would report success and insert nothing."""
    r = backup.create(sandbox["out"], ["kiara"], "all")
    out = backup.restore(r["path"],
                         [{"archive_id": "kiara", "mode": "new", "name": "Kiara"}])
    new_cid = out["restored"][0]["restored_as"]
    assert new_cid != "kiara"

    assert _rows(sandbox, "select count(*) from runs where character_id='kiara'")[0][0] == 2
    assert _rows(sandbox, "select count(*) from runs where character_id=?",
                 (new_cid,))[0][0] == 2
    ids = _rows(sandbox, "select id from runs")
    assert len(ids) == len({i for (i,) in ids}), "a run id was reused"


def test_reminted_runs_keep_file_and_meta_consistent(sandbox):
    """`file` == id + ext holds for every row in this project, and a video row's
    meta.from_run must follow its target to the new id."""
    r = backup.create(sandbox["out"], ["kiara"], "all")
    out = backup.restore(r["path"], [{"archive_id": "kiara", "mode": "new"}])
    cid = out["restored"][0]["restored_as"]

    docs = [json.loads(d) for (d,) in
            _rows(sandbox, "select doc from runs where character_id=?", (cid,))]
    by_id = {d["id"]: d for d in docs}
    for d in docs:
        assert d["file"].startswith(d["id"]), "file no longer names its run"
        assert (Path(sandbox["data"]) / "characters" / cid / "images" /
                d["file"]).exists()
    linked = [d for d in docs if (d.get("meta") or {}).get("from_run")]
    assert linked, "precondition: a row references another run"
    assert linked[0]["meta"]["from_run"] in by_id, "from_run points at a dead id"


# ------------------------------------------------------------------- safety

def test_restore_refuses_while_a_job_is_running(sandbox, monkeypatch):
    """Swapping a folder out from under a live generation corrupts it in a way
    that surfaces days later as a missing file."""
    from backend import generate
    r = backup.create(sandbox["out"], ["kiara"], "identity")
    monkeypatch.setattr(generate, "all_jobs", lambda: [
        {"id": "x", "label": "shot", "stage": "generating", "done": False}])
    with pytest.raises(backup.BackupError, match="still running"):
        backup.restore(r["path"], [{"archive_id": "kiara", "mode": "replace"}])


def test_archive_paths_that_escape_are_refused(sandbox):
    """An archive is untrusted input the moment it can be uploaded; a member
    named ../../.env would overwrite the admin-scoped fal key."""
    evil = sandbox["out"] / "evil.tar"
    evil.parent.mkdir(parents=True, exist_ok=True)
    payload = sandbox["out"] / "payload"
    payload.write_bytes(b"pwned")
    with tarfile.open(evil, "w") as tar:
        tar.add(payload, arcname="characters/kiara/../../../../.env")
    with tarfile.open(evil) as tar:
        with pytest.raises(backup.BackupError, match="suspicious"):
            backup._safe_extract(tar, "characters/", "kiara",
                                 sandbox["out"] / "x")


def test_unknown_preset_is_named(sandbox):
    with pytest.raises(backup.BackupError, match="unknown preset"):
        backup.normalise("everything")
