#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
./scripts/ci/fast.sh
uv build --clear  # stale wheels would make the smoke test the wrong one
uv run --frozen python scripts/ci/package-smoke.py
