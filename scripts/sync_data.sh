#!/usr/bin/env bash
# Move a CHARACTER between machines. `data/` is gitignored (11 GB of it), so a
# fresh clone gives you a working app and an empty studio — this is the other
# half of the migration.
#
#   ./scripts/sync_data.sh knaik@box:~/Throughline        # her, ~750 MB
#   ./scripts/sync_data.sh --with-images /mnt/d/backup    # + past generations
#   ./scripts/sync_data.sh --dry-run knaik@box:~/Throughline
#
# DEST is the project root on the far side (local path or rsync/ssh target);
# everything lands under DEST/data/. Push-only — to pull, run this on the box
# that HAS her.
#
# A character here is three things: her BIO, her BODY and her HOME. That is the
# definition guided creation is built around, and it is the definition this
# script preserves. Everything else — wardrobe, poses, past generations — is
# per-shoot dressing that can be remade. The three cannot.
#
#   BIO    state/bio.json + state/parts.json (the part tree; absent, the code
#          silently falls back to default_parts() and her written identity is
#          quietly replaced with a stranger's defaults)
#          refs/ — 502 M, @image1, her face. The one thing words cannot replace:
#          measured 0.860 with a reference against 0.531 from description alone.
#   BODY   state/bodies.json + bodies/ (34 M) — @image2, and bio.json's
#          body_reference. The axis the gate is blind to, so it has no automated
#          backstop and losing it is unrecoverable.
#   HOME   state/home.json + places/ (211 M) — her ten corners and her regulars.
#          One specific kitchen, not a kitchen invented per shot.
#
# Riding along because they are small and hers: state/gallery.npz (the gate's
# yardstick — without it every run is `ungated` and "is this still her?" has no
# answer), threshold/nails/timeline, nails/, poses/, pose-refs/, gold/, and
# eve1.db (the roster row, 358 runs, and the `mark` verdicts).
#
# NOT preserved, deliberately: images/ (6.5 G of past output) and the WARDROBE,
# both its 3.3 G of photos and its 109 db rows. Outfits are what she wears, not
# who she is; the far side gets a clean wardrobe rather than a list of garments
# whose images aren't there. The source db is never modified.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGES=0 DRY=""
DEST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --with-images)   IMAGES=1 ;;
    --dry-run|-n)    DRY="--dry-run" ;;
    -h|--help)       sed -n '2,40p' "$0"; exit 0 ;;
    -*)              echo "unknown flag: $1" >&2; exit 2 ;;
    *)               DEST="$1" ;;
  esac
  shift
done

[ -n "$DEST" ] || { echo "usage: $0 [--with-images] [--dry-run] DEST" >&2; exit 2; }
command -v rsync >/dev/null || { echo "ERROR: rsync not found." >&2; exit 1; }
[ -d data ] || { echo "ERROR: no data/ here — run this from the machine that HAS her." >&2; exit 1; }

EXCLUDES=(--exclude='videos/' --exclude='wardrobe/' --exclude='__pycache__/'
          --exclude='_*.png' --exclude='eve1.db' --exclude='eve1.db-wal'
          --exclude='eve1.db-shm')
[ "$IMAGES" = 1 ] || EXCLUDES+=(--exclude='images/')

# The db is staged rather than copied, for two reasons. It goes through sqlite's
# own backup API, so a running backend mid-write cannot hand the far side a torn
# file — and the staged copy is where the wardrobe rows are dropped, leaving the
# source db untouched.
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
if [ -x .venv/bin/python ]; then
  ./.venv/bin/python - "$STAGE/eve1.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("file:data/eve1.db?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[1])
with dst:
    src.backup(dst)
n = dst.execute("select count(*) from wardrobe").fetchone()[0]
with dst:
    dst.execute("delete from wardrobe")
dst.execute("vacuum")
dst.close(); src.close()
print(f"    dropped {n} wardrobe rows from the copy (source untouched)")
PY
else
  echo "WARNING: no .venv — copying eve1.db directly, wardrobe rows included." >&2
  echo "         Stop the backend first." >&2
  cp data/eve1.db "$STAGE/eve1.db"
fi

DU=(du -sh --exclude=videos --exclude=wardrobe)
[ "$IMAGES" = 1 ] || DU+=(--exclude=images)
echo "==> $("${DU[@]}" data 2>/dev/null | cut -f1) to send -> $DEST/data/"
echo "    bio + body + home preserved; wardrobe dropped"
[ "$IMAGES" = 1 ] || echo "    skipping images/ (past generations)"

rsync -a --mkpath --info=progress2 --human-readable $DRY "${EXCLUDES[@]}" data/ "$DEST/data/"
rsync -a --mkpath --human-readable $DRY "$STAGE/eve1.db" "$DEST/data/eve1.db"

echo
echo "Done. On the far side:"
echo "  ./setup.sh        # python3.11 venv + frontend + .env skeleton"
echo "  \$EDITOR .env      # FAL_KEY + ANTHROPIC_API_KEY — never copied by this script"
echo "  ./run.sh          # :5173"
