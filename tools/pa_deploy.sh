#!/usr/bin/env bash
# Reclaimr — PythonAnywhere Deploy Helper (dry-run by default)
# Usage:
#   bash tools/pa_deploy.sh                        # dry-run (prints plan only)
#   bash tools/pa_deploy.sh --apply                # execute on this PA console
#   bash tools/pa_deploy.sh --apply --noseed       # skip Account seed
#   bash tools/pa_deploy.sh --branch main          # deploy a specific branch
#
# Env/flags:
#   APP_ROOT   (default: ~/agentsuite)
#   SUBDIR     (default: reclaimr-ai)
#   VENV       (default: $APP_ROOT/venv)
#   BRANCH     (flag --branch overrides; default: current)
#   SEED_KEY   (default: acc_live_test)
#   SEED_NAME  (default: Live Test)
#   SEED_EMAIL (default: noreply@live.test)

set -euo pipefail

APPLY=0
NOSEED=0
BRANCH="${BRANCH:-}"
APP_ROOT="${APP_ROOT:-$HOME/agentsuite}"
SUBDIR="${SUBDIR:-reclaimr-ai}"
VENV="${VENV:-$APP_ROOT/venv}"
SEED_KEY="${SEED_KEY:-acc_live_test}"
SEED_NAME="${SEED_NAME:-Live Test}"
SEED_EMAIL="${SEED_EMAIL:-noreply@live.test}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --noseed) NOSEED=1; shift ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    *) echo "[error] unknown arg: $1" >&2; exit 2 ;;
  esac
done

REPO="$APP_ROOT/$SUBDIR"
DJANGO="python manage.py"
SEED_CMD="python manage.py shell -c \"from apps.accounts.models.account import Account; Account.objects.update_or_create(api_key='${SEED_KEY}', defaults={'name':'${SEED_NAME}','sender_email':'${SEED_EMAIL}'})\""

echo "== PythonAnywhere Deploy Helper =="
echo "App root:   $APP_ROOT"
echo "Subdir:     $SUBDIR"
echo "Repo path:  $REPO"
echo "Venv:       $VENV"
echo "Branch:     ${BRANCH:-<current>}"
echo "Seed:       $([[ $NOSEED -eq 1 ]] && echo skip || echo \"$SEED_KEY / $SEED_NAME / $SEED_EMAIL\")"
echo "Mode:       $([[ $APPLY -eq 1 ]] && echo apply || echo dry-run)"

plan() {
  # enter repo + venv
  echo "\$ cd \"$REPO\""
  echo "\$ source \"$VENV/bin/activate\""
  # optional checkout
  if [[ -n "$BRANCH" ]]; then
    echo "\$ git fetch origin"
    echo "\$ git checkout \"$BRANCH\""
    echo "\$ git pull --ff-only origin \"$BRANCH\""
  else
    echo "\$ git pull"
  fi
  # install
  if [[ -f requirements.txt ]]; then
    echo "\$ pip install -r requirements.txt"
  fi
  # sanity import (optional)
  echo "\$ python - <<'PY'\nimport importlib; import sys\nok=['config','apps.api']\nfor m in ok:\n    try:\n        importlib.import_module(m)\n        print(f\"[ok] import {m}\")\n    except Exception as e:\n        print(f\"[warn] import {m} failed: {e}\")\nPY"
  # migrate
  echo "\$ python manage.py migrate --noinput"
  # optional seed
  if [[ $NOSEED -eq 0 ]]; then
    echo "\$ $SEED_CMD"
  fi
  echo "# Reload your web app in the Web tab after this completes."
}

# Print plan first
plan

# Dry-run exits here
if [[ $APPLY -eq 0 ]]; then
  echo "PASS: deploy plan printed (dry-run; nothing executed)"
  exit 0
fi

# Execute for real
cd "$REPO"
# shellcheck source=/dev/null
source "$VENV/bin/activate"

if [[ -n "$BRANCH" ]]; then
  git fetch origin
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
else
  git pull
fi

if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
fi

# quick import sanity (non-fatal)
python - <<'PY' || true
import importlib
for m in ("config","apps.api"):
    try:
        importlib.import_module(m)
        print(f"[ok] import {m}")
    except Exception as e:
        print(f"[warn] import {m} failed: {e}")
PY

python manage.py migrate --noinput

if [[ $NOSEED -eq 0 ]]; then
  eval "$SEED_CMD"
fi

echo "PASS: deploy steps completed (remember to reload app in Web tab)"
