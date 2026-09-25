#!/usr/bin/env bash
set -euo pipefail

RUNNER_DIR="${CRYPTOFORGE_RUNNER_DIR:-/opt/github-actions/cryptoforge}"
RUNNER_USER="${CRYPTOFORGE_RUNNER_USER:-cryptoforge}"
REPO_URL="${CRYPTOFORGE_GITHUB_REPO_URL:-https://github.com/zart227/cryptoforge}"
LABELS="${CRYPTOFORGE_RUNNER_LABELS:-cryptoforge-vps}"
RUNNER_VERSION="${CRYPTOFORGE_RUNNER_VERSION:-2.328.0}"

if [ "${1:-}" = "" ]; then
  echo "usage: $0 <github-runner-registration-token>" >&2
  exit 2
fi

TOKEN="$1"
ARCHIVE="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${ARCHIVE}"

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

if [ ! -f ./config.sh ]; then
  curl -fsSL "$URL" -o "$ARCHIVE"
  tar xzf "$ARCHIVE"
fi

chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR"

if [ ! -f .runner ]; then
  runuser -u "$RUNNER_USER" -- ./config.sh \
    --unattended \
    --url "$REPO_URL" \
    --token "$TOKEN" \
    --labels "$LABELS" \
    --name cryptoforge-vps \
    --work _work \
    --replace
fi

./svc.sh install "$RUNNER_USER"
./svc.sh start
./svc.sh status
