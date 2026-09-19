#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
uv run --frozen ruff check src tests scripts/check-portability.py scripts/ci/package-smoke.py scripts/demo-desktop.py scripts/release-notes.py
uv run --frozen ruff format --check src tests scripts/check-portability.py scripts/ci/package-smoke.py scripts/demo-desktop.py scripts/release-notes.py
uv run --frozen pytest -q
./scripts/ci/smoke.sh
