#!/usr/bin/env bash
# Move a CHARACTER between machines. `data/` is gitignored (11 GB of it), so a
# fresh clone gives you a working app and an empty studio — this is the other
# half of the migration.
#
#   ./scripts/sync_data.sh knaik@box:~/Throughline          # her, ~750 MB
#   ./scripts/sync_data.sh --with-wardrobe /mnt/d/backup    # + outfit images
#   ./scripts/sync_data.sh --all /mnt/d/backup              # + every generation
#   ./scripts/sync_data.sh --dry-run knaik@box:~/Throughline
#
# DEST is the project root on the far side (local path or rsync/ssh target);
# everything lands under DEST/data/. Push-only — to pull, run this on the box
# that HAS her.
#
# What crosses by default, and why:
#
#   state/       112 K   gallery.npz IS the gate. Without it every run is
#                        `ungated` and "is this still her?" has no answer.
#                        Also parts.json (your part-tree edits — absent, the
#                        code silently falls back to default_parts()),
#                        threshold, bio, bodies/nails/places/home/timeline.
#   refs/        502 M   @image1. Her face. The one thing words cannot replace.
#   places/      211 M   location attachments the brief routes to.
#   bodies/       34 M   @image2 build reference.
#   nails/       3.2 M   manicure references.
#   poses/ pose-refs/ gold/   skeletons and the human-APPROVED shots.
#   eve1.db      1.9 M   roster row + 358 runs (prompt, verdict, and `mark` —
#                        the body-consistency verdict the gate is blind to) +
#                        109 wardrobe rows. Those rows are the garment
#                        DESCRIPTIONS, so the whole wardrobe crosses in text
#                        form even when the 3.3 G of images does not.
#
# What doesn't: images/ (6.5 G of past generations) and wardrobe/ (3.3 G of
# outfit photos). Both are large and neither is her. Note that skipping them
# leaves live db rows pointing at files that aren't there — the review tab will
# show broken thumbnails, and a saved outfit will fall back to its description.
# That is the intended trade, not a bug.
set -euo pipefail
cd "$(dirname "$0")/.."

WARDROBE=0 IMAGES=0 DRY=""
DEST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --with-wardrobe) WARDROBE=1 ;;
    --with-images)   IMAGES=1 ;;
    --all)           WARDROBE=1; IMAGES=1 ;;
    --dry-run|-n)    DRY="--dry-run" ;;
    -h|--help)       sed -n '2,40p' "$0"; exit 0 ;;
    -*)              echo "unknown flag: $1" >&2; exit 2 ;;
    *)               DEST="$1" ;;
  esac
  shift
done

[ -n "$DEST" ] || { echo "usage: $0 [--with-wardrobe|--with-images|--all] [--dry-run] DEST" >&2; exit 2; }
command -v rsync >/dev/null || { echo "ERROR: rsync not found." >&2; exit 1; }
[ -d data ] || { echo "ERROR: no data/ here — run this from the machine that HAS her." >&2; exit 1; }

EXCLUDES=(--exclude='videos/' --exclude='__pycache__/' --exclude='_*.png'
          --exclude='eve1.db' --exclude='eve1.db-wal' --exclude='eve1.db-shm')
[ "$IMAGES"   = 1 ] || EXCLUDES+=(--exclude='images/')
[ "$WARDROBE" = 1 ] || EXCLUDES+=(--exclude='wardrobe/')

# The db is staged through sqlite's own backup API rather than copied, so a
# running backend mid-write can't hand the far side a torn file. Plain cp is the
# fallback; it's only correct if nothing is writing.
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
if [ -x .venv/bin/python ]; then
  ./.venv/bin/python - "$STAGE/eve1.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("file:data/eve1.db?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[1])
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
else
  echo "WARNING: no .venv — copying eve1.db directly. Stop the backend first." >&2
  cp data/eve1.db "$STAGE/eve1.db"
fi

DU=(du -sh --exclude=videos)
[ "$IMAGES"   = 1 ] || DU+=(--exclude=images)
[ "$WARDROBE" = 1 ] || DU+=(--exclude=wardrobe)
echo "==> $("${DU[@]}" data 2>/dev/null | cut -f1) to send -> $DEST/data/"
[ "$IMAGES"   = 1 ] || echo "    skipping images/   (past generations)"
[ "$WARDROBE" = 1 ] || echo "    skipping wardrobe/ (outfit photos; descriptions still cross in the db)"

rsync -a --mkpath --info=progress2 --human-readable $DRY "${EXCLUDES[@]}" data/ "$DEST/data/"
rsync -a --mkpath --human-readable $DRY "$STAGE/eve1.db" "$DEST/data/eve1.db"

echo
echo "Done. On the far side:"
echo "  ./setup.sh        # python3.11 venv + frontend + .env skeleton"
echo "  \$EDITOR .env      # FAL_KEY + ANTHROPIC_API_KEY — never copied by this script"
echo "  ./run.sh          # :5173"
