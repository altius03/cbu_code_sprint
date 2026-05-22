#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
APP_BIN="$DIR/apps/macos/CBU Code Sprint.app/Contents/MacOS/CBU Code Sprint"
if [ -x "$APP_BIN" ]; then
  "$APP_BIN" --home "$DIR" "$@"
elif [ -x "$DIR/.venv/bin/python" ]; then
  PYTHONPATH="$DIR/src" "$DIR/.venv/bin/python" -m cbu_code_sprint --home "$DIR" "$@"
else
  PYTHONPATH="$DIR/src" python3 -m cbu_code_sprint --home "$DIR" "$@"
fi
