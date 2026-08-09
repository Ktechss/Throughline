"""One-off: give existing runs a session, and register images generated outside
the API so they appear in the review grid.

The bakeoff and the two-shot tests were driven by ad-hoc scripts that wrote
files directly and never touched runs.json. The images exist on disk and are
invisible to the UI, which is exactly the state that made this morning's lost
bakeoff unrecoverable. Anything worth looking at belongs in the log.

    .venv-win\\Scripts\\python.exe scripts\\backfill_sessions.py
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, gate                           # noqa: E402
from backend.config import IMAGES, RUNS_PATH               # noqa: E402

# note -> (session label, started). Grouped by the decision each run belonged
# to, which is what the note recorded at the time.
BY_NOTE = {
    "first run of rebuilt pipeline": ("first run — no face reference", "2026-07-17T12:13:00"),
    "face ref only":                 ("face ref vs face ref + pose", "2026-07-17T13:05:00"),
    "face ref + pose":               ("face ref vs face ref + pose", "2026-07-17T13:05:00"),
    "2-ref recipe: closeup":         ("2-ref recipe (mismatched refs)", "2026-07-17T14:40:00"),
    "2-ref recipe: fullbody":        ("2-ref recipe (mismatched refs)", "2026-07-17T14:40:00"),
    "matched-pair refs: closeup":    ("matched pair from one generation", "2026-07-17T15:00:00"),
    "matched-pair refs: fullbody":   ("matched pair from one generation", "2026-07-17T15:00:00"),
}

# Images the bakeoff wrote straight to disk. Same session: they were one
# decision, and comparing them only means anything because the config was held
# constant across them.
BAKEOFF = {
    "bake_ideogram-character.png": "fal-ai/ideogram/character",
    "bake_flux-pulid.png": "fal-ai/flux-pulid",
    "bake_instant-character.png": "fal-ai/instant-character",
}
BAKEOFF_SESSION = {"id": "bakeoff01", "started": "2026-07-17T15:20:00",
                   "label": "identity-transfer bakeoff — one face ref, close-up"}


def main() -> int:
    rows = json.loads(RUNS_PATH.read_text()) if RUNS_PATH.exists() else []
    ids = {}

    for r in rows:
        if r.get("session"):
            continue
        note = (r.get("meta") or {}).get("note", "")
        label, started = BY_NOTE.get(note, ("earlier runs", r.get("created", "")))
        if label not in ids:
            ids[label] = uuid.uuid4().hex[:8]
        r["session"] = {"id": ids[label], "label": label, "started": started}
        print(f"  {r['id']}  -> {label}")

    have = {r["file"] for r in rows}
    for fname, endpoint in BAKEOFF.items():
        if fname in have or not (IMAGES / fname).exists():
            continue
        row = {
            "id": uuid.uuid4().hex[:10], "session": BAKEOFF_SESSION,
            "file": fname, "endpoint": endpoint,
            "prompt": "(ad-hoc bakeoff; see FINDINGS.md)", "system": "",
            "refs": [config.bio_face().name], "pose": None, "seed": None,
            "aspect": "1024x1408", "resolution": "1024x1408",
            "seconds": None, "created": BAKEOFF_SESSION["started"],
            "mark": None, "meta": {"note": f"bakeoff: {endpoint}"},
        }
        try:
            row["verdict"] = gate.check(IMAGES / fname).dict()
        except Exception as exc:                            # noqa: BLE001
            row["verdict"] = {"status": "error", "reason": str(exc)[:80]}
        rows.append(row)
        print(f"  + registered {fname}  {row['verdict'].get('similarity')}")

    RUNS_PATH.write_text(json.dumps(rows, indent=2) + "\n")
    n = len({r["session"]["id"] for r in rows})
    print(f"\n{len(rows)} runs across {n} sessions -> {RUNS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
