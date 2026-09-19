#!/usr/bin/env python3
"""Release notes for one tag: its CHANGELOG.md entry, links pinned to the tag, plus install/verify.

Usage: release-notes.py vX.Y.Z   (prints Markdown; used by .github/workflows/release.yml)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPOSITORY = "https://github.com/tryingET/niri-desktop-continuity"
PACKAGE = "niri-desktop-continuity"


def notes(changelog: str, tag: str) -> str:
    version = tag.removeprefix("v")
    heading = re.search(rf"^## \[{re.escape(version)}\] - .+$", changelog, re.M)
    if heading is None:
        raise SystemExit(f"CHANGELOG.md has no entry for {version}")
    entry = changelog[heading.end() :].split("\n## [", 1)[0].strip()
    entry = re.sub(r"^### ", "## ", entry, flags=re.M)
    # Relative links resolve on GitHub's file view, not on a release page.
    entry = re.sub(
        r"\]\((?!https?://|#)([^)]+)\)", lambda m: f"]({REPOSITORY}/blob/{tag}/{m[1]})", entry
    )
    workflow = f"{REPOSITORY}/blob/{tag}/.github/workflows/release.yml"
    return f"""```sh
pipx install {PACKAGE}=={version}
```

{entry}

## Verify

Built once from `{tag}` by the [release workflow]({workflow}) after `just ci` passed on it. The
same files are on [PyPI](https://pypi.org/project/{PACKAGE}/{version}/), uploaded through trusted
publishing. Check the files attached here with `sha256sum -c SHA256SUMS`.
"""


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text()
    print(notes(changelog, sys.argv[1]), end="")
