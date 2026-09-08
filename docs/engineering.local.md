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
`just ci` additionally builds wheel and sdist and runs the installed-console smoke in a scratch
virtual environment outside the checkout. Privacy regressions use Git only in fabricated scratch
repositories. All effect tests use fake Niri transports and private test lock directories;
no automated check may move a user's windows. Live-effect canaries
require explicit separate approval and do not follow from a green test suite.

Shared engineering guidance may inform maintenance but is optional; installation, tests, builds
and CI must not invoke company-specific commands, databases, source checkouts or services.

## Optional development state versus product state

The approved narrow exception is root `/.ontology/`: optional workspace-local SCI development
state may remain there only as ignored, untracked tooling state. It is not a runtime dependency,
product Store location, source input or distributable. The privacy scanner does not open its
payloads. Git-index enumeration independently rejects **every tracked `.ontology` path**, even
force-added ignored files; exports without Git reject `.ontology` at any depth. The exception
does not apply to a root symlink, nested `.ontology`, other hidden data or arbitrary ignore rules.
Known checkout build/tool caches and the immutable local template context remain excluded;
tracked paths are still checked independently. Export inputs have no such cache exemptions.
Directory-enumeration errors fail closed with a static diagnostic, not an incomplete passing scan;
this does not require descending into the intentionally pruned development-state directory.

Product captures, previews, approvals and receipts must remain outside the repository, at the
existing private Store location. Ignoring runtime-state directories does not make them acceptable
source inputs. Home-specific paths, unreviewed binaries and symlinks remain privacy failures.
No existing development or product state may be moved, deleted or read to manufacture a pass.

The sdist's explicit allowlist ships the integrated reconstruction design, plan and protocol
linked by portable documentation. Wheel/sdist metadata checks reject `.ontology`, runtime artifact
paths, private template context, diaries and links/special entries without extracting payloads.
These checks do not certify arbitrary content as non-sensitive; only fabricated fixtures belong
in source and packages. Runtime dependencies remain empty and there is still one CLI.

Validate with `UV_OFFLINE=1 just ci`: lint, formatting, the entire test suite, source/privacy and
entrypoint checks, wheel/sdist builds and isolated installed-console smoke. Tests honor `TMPDIR`;
no machine adapter, live compositor or native profile integration is implied by this gate.
