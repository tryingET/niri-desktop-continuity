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

1. Move the user-facing changes into a new `## [X.Y.Z] - YYYY-MM-DD` entry in `CHANGELOG.md` (it
   becomes the release notes), set the version in `pyproject.toml` and
   `src/niri_desktop_continuity/__init__.py`, and run `uv lock`.
2. Run `just ci` on a clean tree. Commit, push `main`, and wait for the `ci` workflow to pass.
3. Tag that commit and push the tag: `git tag -a vX.Y.Z -m "vX.Y.Z"` and
   `git push origin vX.Y.Z`. That is the release decision; nothing else is published by hand.
4. The `release` workflow builds once from the tag, checks that the tag names the packaged
   version, runs `just ci`, uploads the wheel and sdist to PyPI through trusted publishing in the
   `pypi` environment (deployable from `v*` tags only), and then creates the GitHub Release with
   the same files, `SHA256SUMS` and notes generated from the version's `CHANGELOG.md` entry
   (`scripts/release-notes.py`). Releases in this repository are immutable: files cannot be added
   after publishing, which is why the release is created together with its files.
5. Verify: download the release assets and run `sha256sum -c SHA256SUMS`; install with
   `pipx install niri-desktop-continuity==X.Y.Z` and run `niri-desktop-continuity --version`.

One-time setup, done by the PyPI account owner: a trusted publisher for project
`niri-desktop-continuity`, owner `tryingET`, repository `niri-desktop-continuity`, workflow
`release.yml`, environment `pypi`.

## Rollback

Never move or delete a published tag. Fix forward with a patch release; if a release is harmful,
mark it in its notes and point to the replacement. Saved captures are content-addressed JSON that
the newer version wrote alongside the older ones; roll back by installing the previous release.
