---
summary: "Portable Python engineering contract; no private infrastructure required."
read_when:
  - "You change the runtime, packaging or validation commands."
type: "reference"
---

# Engineering

Python 3.11+ and the standard library at runtime. Niri/Linux only. No framework or daemon.
Development dependencies are pytest and Ruff, declared in `pyproject.toml` and pinned in `uv.lock`.
Packaging uses Hatchling. Keep imports and assets inside `niri_desktop_continuity` so an installed
wheel works independently of the source checkout.

`just check` covers lint, formatting, unit tests, Python 3.11 syntax and portable-source checks.
`just ci` additionally builds wheel and sdist. All effect tests use fake Niri transports and
private test lock directories; no automated check may move a user's windows. Live-effect canaries
require explicit separate approval and do not follow from a green test suite.

Shared engineering guidance may inform maintenance but is optional; installation, tests, builds
and CI must not invoke company-specific commands, databases, source checkouts or services.
