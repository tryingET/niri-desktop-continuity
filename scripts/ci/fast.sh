#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
uv run --frozen ruff check src tests scripts/check-portability.py scripts/ci/package-smoke.py
uv run --frozen ruff format --check src tests scripts/check-portability.py scripts/ci/package-smoke.py
uv run --frozen pytest -q
./scripts/ci/smoke.sh
