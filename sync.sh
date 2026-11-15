#!/bin/bash
# Sync project files to Raspberry Pi (excludes venv, cache, output, git).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/deploy.env"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${PI_TARGET:?Set PI_TARGET in deploy.env (copy deploy.env.example first)}"

rsync -av \
  --exclude venv \
  --exclude cache \
  --exclude output \
  --exclude .git \
  --exclude __pycache__ \
  "$SCRIPT_DIR/" "$PI_TARGET:~/eInk/"
