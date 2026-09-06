---
summary: "Contributor contract for the standalone Niri desktop-continuity tool."
read_when:
  - "You change code, tests, documentation or packaging in this repository."
type: "reference"
---

# niri-desktop-continuity

## Product boundary

A small Niri/Linux-only tool. No multi-compositor framework, daemon, application launcher,
telemetry, browser-profile reader or arbitrary process-memory recovery. Runtime uses Python's
standard library and Niri IPC. Development must not require a maintainer's private infrastructure.

## Safety and privacy

- Capture/preview never moves windows, runs discovered app binaries or grants approval.
- All restart/migration remains blocked until an independently tested exact recovery adapter exists.
- Live layout actions require explicit operator approval; synthetic tests do not authorize them.
- Never put real desktop snapshots, titles, executable paths, environment dumps or session logs in Git.
- Use fabricated fixtures. Keep generated runtime state outside the repository.
- Preserve the digest, expiry, focus, per-compositor writer-lock and replay gates.
- No automatic retry after ambiguous IPC effects. No automatic rollback or process termination.
- Tests must not contact a real compositor or modify its live lock directory.

## Engineering and validation

Read `README.md`, `docs/architecture.md`, and the exact affected modules. UI changes follow
`DESIGN.md`. Keep Python 3.11 syntax compatibility; runtime dependencies remain empty.
`just check` runs style, formatting, tests and privacy checks. `just ci` also builds packages.
Tests must include a handwritten oracle where an implementation helper could otherwise test itself.

Keep `docs/_core/` immutable if present in a local template checkout. It is not distributed.
Do not hand-edit generated indexes or runtime receipts. Capture implementation notes under `diary/`
without personal incident details. External maintainer task tracking is not a runtime dependency or
an exportable private database. Do not add local task/session identifiers to this public source tree.

Work on main locally; do not push or publish a release without explicit operator instruction.
