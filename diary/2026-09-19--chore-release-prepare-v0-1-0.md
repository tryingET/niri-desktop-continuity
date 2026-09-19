---
summary: "First release preparation: CI, issue templates, changelog, release process, --version and a social card."
read_when:
  - "You cut a release, change CI, or wonder where the release process came from."
---

# 2026-09-19 — Preparing v0.1.0

## What I Did

- Found no release strategy: no tags, releases, changelog or CI, and the template's release pack
  disabled. Followed engineering-core's `release-package` discipline instead of inventing one:
  `docs/release.md` (semver pre-1.0, tag + GitHub Release as the one authority, checksums, fix
  forward), `CHANGELOG.md` (user-facing, in the sdist) and a test that `pyproject.toml`,
  `__version__`, the newest changelog heading and `--version` agree.
- `.github/workflows/ci.yml` runs `just ci` on push, tags and pull requests, with actions pinned to
  commit SHAs and no persisted checkout credentials. Issue templates ask for the preview's
  reboot-ledger row and warn about private paths.
- `just screenshots` also renders a 1280×640 social card from the demo desktop; GitHub has no API
  for it, so it is uploaded by hand.

- After v0.1.0: Ghostty is the only supported terminal, by the operator's decision (other
  terminals fork). Detection now matches it, so kitty/WezTerm windows reopen as plain
  applications instead of receiving Ghostty's flags. v0.1.1 adds a `release` workflow: one build
  from the tag, `just ci`, assets and `SHA256SUMS` attached to the release, the same files to PyPI
  through trusted publishing in a `pypi` environment limited to `v*` tags. README links became
  absolute so the PyPI page renders.

## What Surprised Me

- The PyPI name was still free, but trusted publishing needs a one-time owner step on pypi.org;
  it waits for a patch release.
- Writing the promotion copy exposed that recipes pass Ghostty-style `--working-directory`/`-e`
  to every terminal; kitty and WezTerm take other flags.
- The first GitHub CI run failed 9 of 665 tests that always pass locally, and both causes were
  isolation leaks. Five transport-deadline tests went through `owner_guard()`, locking the real
  `~/.config` owner anchor and reading the real recovery profile. Four installed-CLI tests injected
  their fakes via `sitecustomize.py`, which a system `sitecustomize` (Debian/Ubuntu ship one)
  shadows; the installed CLI then ran real `capture`, and on a Debian machine running niri it would
  have contacted the compositor. Fixed with a `tests/conftest.py` that unsets `NIRI_SOCKET` and
  points the owner profile at an empty temp path for every test, a `.pth` injection (tested
  against a shadowing `sitecustomize`), and a deadline fixture that no longer takes the owner lock.

## Crystallization Candidates

- → docs/learnings: promotion drafts are a good audit of claims, like the README's "never" list.
- → docs/learnings: a suite that only ever ran on the maintainer's desktop cannot show it is
  hermetic; the first clean runner is the test. Default every test to fail closed on live state.
