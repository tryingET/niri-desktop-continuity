# Standardized operator surface for this standalone CLI.
# Thin delegation to repo-local wrappers; see scripts/ci/ and docs/engineering.local.md.

default: help

# Show the supported local command surface.
help:
    just --list

# Run the default test suite (pytest; config lives in pyproject.toml).
test:
    uv run --frozen pytest

# Fast local validation gate: lint, formatting check, tests, entrypoint smoke,
# and the portable-source/privacy check. Delegates to the canonical wrapper.
check:
    ./scripts/ci/fast.sh

# Non-formatting linter over the same scope as the check gate.
lint:
    uv run --frozen ruff check src tests scripts/check-portability.py scripts/ci/package-smoke.py scripts/demo-desktop.py

# Apply formatting to the same scope as the check gate.
fmt:
    uv run --frozen ruff format src tests scripts/check-portability.py scripts/ci/package-smoke.py scripts/demo-desktop.py

# Build distributable artifacts (wheel + sdist).
build:
    uv build

# Full local CI-equivalent gate: check + package build via the canonical wrapper.
# scripts/ci/full.sh already runs fast.sh, so ci must not also invoke check.
ci:
    ./scripts/ci/full.sh

# Toolchain/runtime sanity checks: uv present, locked environment, interpreter.
doctor:
    uv --version
    uv run --frozen python --version

# One-shot execution of the primary CLI entrypoint (truthful --help smoke).
run:
    uv run --frozen niri-desktop-continuity --help

# Re-render the README screenshots from the fabricated demo desktop (needs chromium + ImageMagick).
screenshots:
    ./scripts/docs-screenshots.sh

# NOTE: no `dev` target: this repo has no long-running dev/watch surface
# (standard-library CLI; iteration is edit + `just run`/`just test`).
