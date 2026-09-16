---
summary: "Contributor contract for the standalone Niri desktop-continuity tool."
read_when:
  - "You change code, tests, documentation or packaging in this repository."
type: "reference"
---

# niri-desktop-continuity

## Product boundary

A small Niri/Linux-only tool. No multi-compositor framework, daemon, general application launcher,
telemetry, browser-profile reader or arbitrary process-memory recovery. The portable runtime uses
Python's standard library, Niri IPC and an optional explicitly pinned internal recovery adapter.
Development must not require a maintainer's private infrastructure.

Loss-bounded saved-conversation reconstruction is a distinct, explicitly approved contract:
[design](docs/project/2026-09-06-integrated-reconstruction-design.md). All operator stages must use
the existing CLI; machine-specific adapter/configuration/private state stay with their owner.
This boundary permits implementation, not unreviewed or automatically authorized live effects.

## Safety and privacy

- Capture/preview never moves windows, runs discovered app binaries or grants approval.
- `restore --apply` spawns recorded recipes and moves only the windows it spawned; live windows are
  protected and nothing is ever closed. Login/timer units exist only after `autostart --enable`.
- All restart/migration remains blocked until an independently tested exact recovery adapter exists.
- Live layout actions require explicit operator approval; synthetic tests do not authorize them.
- Never put real desktop snapshots, titles, executable paths, environment dumps or session logs in Git.
- Use fabricated fixtures. Keep generated product runtime state (including captures and receipts)
  outside the repository. Optional workspace-local SCI development state may remain only in ignored
  root `.ontology/`; it is not a product state location, source input or distributable. Never track it.
- Preserve the digest, expiry, focus, per-compositor writer-lock and replay gates.
- No automatic retry after ambiguous effects or automatic rollback/cleanup. Process termination
  is permitted only within an independently reviewed, exact-digest-approved reconstruction of
  freshly proved owned targets; never as generic recovery, timeout cleanup or fault handling.
- Unknown ownership, process identity or protected/controller overlap always blocks. Missing native
  session association blocks unless a separately reviewed, exact-process omission is explicitly
  approved in the new plan; generic loss acceptance never supplies that decision.
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
