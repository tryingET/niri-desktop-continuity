#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
uv run --frozen python -m niri_desktop_continuity --help >/dev/null
uv run --frozen python scripts/check-portability.py
