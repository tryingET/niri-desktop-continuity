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

## What Surprised Me

- The PyPI name was still free, but trusted publishing needs a one-time owner step on pypi.org;
  it waits for a patch release.
- Writing the promotion copy exposed that recipes pass Ghostty-style `--working-directory`/`-e`
  to every terminal; kitty and WezTerm take other flags.

## Crystallization Candidates

- → docs/learnings: promotion drafts are a good audit of claims, like the README's "never" list.
