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

The git tag `vX.Y.Z` and the GitHub Release with that name are the release; PyPI carries the same
files. `pyproject.toml`, `niri_desktop_continuity.__version__`, `niri-desktop-continuity --version`
and the newest `CHANGELOG.md` heading must name the same version; a test enforces it, and the
release workflow refuses a tag that does not match.

## Steps

1. Move the user-facing changes into a new `## [X.Y.Z] - YYYY-MM-DD` entry in `CHANGELOG.md`, set
   the version in `pyproject.toml` and `src/niri_desktop_continuity/__init__.py`, and run `uv lock`.
2. Run `just ci` on a clean tree. Commit, push `main`, and wait for the `ci` workflow to pass.
3. Tag that commit: `git tag -a vX.Y.Z -m "vX.Y.Z"` and `git push origin vX.Y.Z`.
4. `gh release create vX.Y.Z --verify-tag --title vX.Y.Z --notes-file <notes>`. The notes state
   what changed, compatibility, privacy relevance and known issues.
5. The `release` workflow then builds once from the tag, runs `just ci`, attaches the wheel, sdist
   and `SHA256SUMS` to the release and uploads the same files to PyPI through trusted publishing
   in the `pypi` environment (deployable from `v*` tags only).
6. Verify: download the release assets and run `sha256sum -c SHA256SUMS`; install with
   `pipx install niri-desktop-continuity==X.Y.Z` and run `niri-desktop-continuity --version`.

One-time setup, done by the PyPI account owner: a trusted publisher for project
`niri-desktop-continuity`, owner `tryingET`, repository `niri-desktop-continuity`, workflow
`release.yml`, environment `pypi`.

## Rollback

Never move or delete a published tag. Fix forward with a patch release; if a release is harmful,
mark it in its notes and point to the replacement. Saved captures are content-addressed JSON that
the newer version wrote alongside the older ones; roll back by installing the previous release.
