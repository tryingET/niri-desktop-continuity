---
summary: "How a release is versioned, validated, tagged, built and published, and how to roll one back."
read_when:
  - "You prepare, publish or roll back a release."
---

# Releasing

A release is a claim that a named artifact installs, runs and can be audited and rolled back.
Only the maintainer publishes, and only on explicit instruction (see `AGENTS.md`).

## Versioning

Semantic versioning, pre-1.0 alpha. The compatibility surface is the CLI and its JSON output,
the saved-state layout under the state root, reopen recipes and the systemd units that
`autostart` writes. Before 1.0 a minor release may change these; its changelog entry says how.

## One authoritative release

The git tag `vX.Y.Z` and the GitHub Release with that name are the release. `pyproject.toml`,
`niri_desktop_continuity.__version__`, `niri-desktop-continuity --version` and the newest
`CHANGELOG.md` heading must name the same version; a test enforces it. No package-registry
release exists yet; PyPI is planned through trusted publishing from CI.

## Steps

1. Move the user-facing changes into a new `## [X.Y.Z] - YYYY-MM-DD` entry in `CHANGELOG.md` and
   set the version in `pyproject.toml` and `src/niri_desktop_continuity/__init__.py`.
2. Run `just ci` on a clean tree (lint, formatting, tests, privacy check, build, installed-wheel
   smoke). Commit, push `main`, and wait for the `ci` workflow to pass on that commit.
3. Tag that commit: `git tag -a vX.Y.Z -m "vX.Y.Z"` and `git push origin vX.Y.Z`.
4. Build from a clean checkout of the tag: `uv build`, then
   `(cd dist && sha256sum *.whl *.tar.gz > SHA256SUMS)`.
5. `gh release create vX.Y.Z dist/*.whl dist/*.tar.gz dist/SHA256SUMS --title vX.Y.Z
   --notes-file <notes>`. The notes state what changed, compatibility, privacy relevance,
   known issues, the source commit and the build command.

## Rollback

Never move or delete a published tag. Fix forward with a patch release; if a release is harmful,
mark it in its notes and point to the replacement. Saved captures are content-addressed JSON that
the newer version wrote alongside the older ones; roll back by installing the previous release.
