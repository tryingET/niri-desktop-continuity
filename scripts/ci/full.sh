#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
./scripts/ci/fast.sh
uv build
uv run --frozen python scripts/ci/package-smoke.py
