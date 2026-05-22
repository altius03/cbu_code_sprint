#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "Missing .venv. Run: python3.12 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'" >&2
  exit 2
fi
"$ROOT/.venv/bin/python" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --paths "$ROOT/src" \
  --name "CBU Code Sprint" \
  "$ROOT/scripts/pyinstaller_entry.py"
mkdir -p "$ROOT/apps/macos"
rm -rf "$ROOT/apps/macos/CBU Code Sprint.app"
cp -R "$ROOT/dist/CBU Code Sprint.app" "$ROOT/apps/macos/CBU Code Sprint.app"
echo "Built: $ROOT/dist/CBU Code Sprint.app"
echo "Installed for USB layout: $ROOT/apps/macos/CBU Code Sprint.app"
