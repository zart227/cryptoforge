#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${CRYPTOFORGE_APP_DIR:-/opt/cryptoforge/app}"
REPO_DIR="${CRYPTOFORGE_REPO_DIR:-$APP_DIR/cryptoforge_repo}"
VENV_DIR="${CRYPTOFORGE_VENV_DIR:-$APP_DIR/venv}"
BRANCH="${CRYPTOFORGE_BRANCH:-main}"
REMOTE="${CRYPTOFORGE_REMOTE:-origin}"

cd "$REPO_DIR"

git fetch --prune "$REMOTE" "$BRANCH"
REMOTE_COMMIT="$(git rev-parse "$REMOTE/$BRANCH")"
CURRENT_COMMIT="$(git rev-parse HEAD 2>/dev/null || true)"

if [ "$CURRENT_COMMIT" = "$REMOTE_COMMIT" ] && git diff --quiet && git diff --cached --quiet; then
  echo "cryptoforge_deploy_no_change branch=$BRANCH commit=$(git rev-parse --short HEAD)"
  exit 0
fi

git checkout -B "$BRANCH" "$REMOTE/$BRANCH"
git reset --hard "$REMOTE/$BRANCH"

if [ -x "$VENV_DIR/bin/python" ]; then
  PYTHON="$VENV_DIR/bin/python"
  PIP="$VENV_DIR/bin/pip"
else
  PYTHON="python3"
  PIP="python3 -m pip"
fi

$PIP install -e .
PYTHONPATH=src "$PYTHON" -m compileall -q src scripts
PYTHONPATH=src "$PYTHON" - <<'PY'
from cryptoforge.bybit_private import BybitPrivateClient

print("cryptoforge_import_ok")
print(BybitPrivateClient.__name__)
PY

if [ "$(id -u)" = "0" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
fi

echo "cryptoforge_deploy_ok branch=$BRANCH commit=$(git rev-parse --short HEAD)"
