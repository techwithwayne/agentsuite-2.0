#!/usr/bin/env bash
set -euo pipefail

# CONFIG
ZIP="${1:-postpress_wp.zip}"
BRANCH="feat/wp-plugin/postpress-ai"
TARGET_DIR="wp-plugins/postpress-ai"
GIT_IGNORE_FILE=".gitignore"
NOW_TS="$(date +%Y%m%d%H%M%S)"
LOG_DATE="2025-09-04"

CHANGE_LOG_BLOCK=$(cat <<'EOT'
# CHANGED: 2025-09-04 - imported from postpress_wp.zip
/**
 * CHANGE LOG
 * 2025-09-04: Imported from postpress_wp.zip into agentsuite repo branch.
 */
EOT
)

if [ ! -f "$ZIP" ]; then
  echo "ERROR: ZIP not found at: $ZIP"
  exit 2
fi

echo "Using ZIP: $(realpath "$ZIP")"

# 1) Checkout branch (create if doesn't exist)
if git rev-parse --verify --quiet "$BRANCH" >/dev/null; then
  echo "Switching to existing branch: $BRANCH"
  git checkout "$BRANCH"
else
  echo "Creating branch: $BRANCH"
  git checkout -b "$BRANCH"
fi

# 2) List top entries (short list)
echo "Listing top entries inside zip (first 200 lines):"
if command -v unzip >/dev/null 2>&1 && unzip -Z1 "$ZIP" >/dev/null 2>&1; then
  unzip -Z1 "$ZIP" | sed -n '1,200p'
else
  # fallback: use python to list zip contents
  python - <<PY
import zipfile,sys
z=zipfile.ZipFile("$ZIP")
for i,n in enumerate(z.namelist()):
    if i<200:
        print(n)
    else:
        break
PY
fi

# 3) Find plugin root inside zip (the path that contains postpress-ai.php)
PLUGIN_PHP_PATH=$(python - <<PY
import zipfile,sys,os
z=zipfile.ZipFile("$ZIP")
for n in z.namelist():
    if n.lower().endswith('postpress-ai.php'):
        # print the containing dir (no trailing slash)
        d=os.path.dirname(n)
        if d=='':
            print('.')
        else:
            print(d)
        sys.exit(0)
print("")
PY
)

if [ -z "$PLUGIN_PHP_PATH" ]; then
  echo "ERROR: could not find 'postpress-ai.php' inside the zip. Aborting."
  exit 3
fi

echo "Detected plugin root within zip: $PLUGIN_PHP_PATH"

# 4) Backup existing plugin dir if present
if [ -d "$TARGET_DIR" ]; then
  BAK="${TARGET_DIR}.bak.${NOW_TS}"
  echo "Backing up existing $TARGET_DIR -> $BAK"
  mv "$TARGET_DIR" "$BAK"
fi

# 5) Extract plugin files into a temp dir and then move into target
TMPDIR="$(mktemp -d)"
echo "Extracting zip to temp dir: $TMPDIR"
unzip -qq "$ZIP" -d "$TMPDIR"

# compute extracted plugin directory (join TMPDIR + PLUGIN_PHP_PATH)
EXTRACTED_PLUGIN_DIR="$TMPDIR/$PLUGIN_PHP_PATH"
if [ ! -d "$EXTRACTED_PLUGIN_DIR" ]; then
  # try to locate any directory that contains postpress-ai.php
  FOUND_DIR=$(find "$TMPDIR" -type f -iname 'postpress-ai.php' -printf '%h\n' | head -n1 || true)
  if [ -z "$FOUND_DIR" ]; then
    echo "ERROR: extracted zip did not contain expected plugin layout"
    exit 4
  else
    EXTRACTED_PLUGIN_DIR="$FOUND_DIR"
  fi
fi

# ensure parent path exists
mkdir -p "$(dirname "$TARGET_DIR")"
echo "Moving extracted plugin folder into $TARGET_DIR"
mv "$EXTRACTED_PLUGIN_DIR" "$TARGET_DIR"

# 6) For each PHP file lacking CHANGE LOG (case-insensitive), cp .orig and insert block after <?php
ANNOTATED_FILES=()
SKIPPED_FILES=()

while IFS= read -r -d '' FILE; do
  # check for CHANGE LOG string case-insensitive
  if grep -qi "CHANGE LOG" "$FILE"; then
    SKIPPED_FILES+=("$FILE")
    continue
  fi

  # create .orig backup (only if not already present)
  if [ ! -f "${FILE}.orig" ]; then
    cp -p "$FILE" "${FILE}.orig"
  fi

  # insert change log block immediately after the first "<?php" occurrence
  # We will rewrite the file safely to a temp file then move back
  TMPF="$(mktemp)"
  awk -v block="$CHANGE_LOG_BLOCK" '
    BEGIN{ inserted=0 }
    {
      if(!inserted && $0 ~ /^<\?php/){
        print $0
        print block
        inserted=1
        next
      }
      print $0
    }
    END{
      if(!inserted){
        # if file never had <?php (unlikely), prepend the block
        print block
      }
    }
  ' "$FILE" > "$TMPF"
  mv "$TMPF" "$FILE"
  ANNOTATED_FILES+=("$FILE")
done < <(find "$TARGET_DIR" -type f -iname '*.php' -print0)

# 7) Update .gitignore (append if missing)
GITIGNORE_ADDS=(
"$TARGET_DIR/*.orig"
"$TARGET_DIR/*.bak.*"
"$ZIP"
)
for L in "${GITIGNORE_ADDS[@]}"; do
  if ! grep -Fxq "$L" "$GIT_IGNORE_FILE" 2>/dev/null; then
    printf "%s\n" "$L" >> "$GIT_IGNORE_FILE"
  fi
done

# 8) Stage and single commit
git add "$TARGET_DIR" "$GIT_IGNORE_FILE"
git status --porcelain

git commit -m "chore(postpress-ai): import plugin from postpress_wp.zip and add CHANGE LOG to PHP files where missing" || {
  echo "git commit failed or nothing to commit."
}

# 9) Report
echo ""
echo "Annotated ${#ANNOTATED_FILES[@]} PHP files (CHANGE LOG added where missing)."
echo "Annotated files:"
for f in "${ANNOTATED_FILES[@]}"; do echo " - $f"; done
echo ""
echo "Skipped files (already had CHANGE LOG):"
for f in "${SKIPPED_FILES[@]}"; do echo " - $f"; done

echo ""
echo "Recent commits (top 3):"
git --no-pager log --oneline -n 3

echo ""
echo "Done. To push, run locally:"
echo "  git push origin $BRANCH"

# Cleanup temp dir
rm -rf "$TMPDIR"
