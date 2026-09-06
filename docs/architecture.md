---
summary: "Niri-only module boundaries, evidence model and portable packaging."
read_when:
  - "You change the runtime, state model or packaging."
---

# Architecture

One CLI, no daemon, no platform plugin framework. Python standard library at runtime; Niri/Linux
is the supported environment. Plain JSON on stdout composes with Unix tools; errors go to stderr.
No application restart or migration adapter is implemented.

- `probe`: bounded read-only Niri queries and Linux same-user process metadata. Discovered
  application binaries are hashed, never executed. Version remains unknown.
- `model`: snapshot normalization, topology/process identity, output readiness, separate focus
  predicates and same-compositor verification. Titles are never identity keys.
- `store`: private immutable JSON/HTML/SVG artifacts, durable pointer writes and replay markers.
- `planner`: intersected selectors, observed shared-process impact and explicit admission blockers.
  Only same-workspace single-tile column reorder is effect-modelled.
- `approval`: complete plan digest, bounded lifetime, source/current state and focus revalidation.
- `operation_lock`: one cooperating writer per boot/compositor inode/device across state roots.
- `reconcile`: predict, lock/revalidate, consume, persist intent, act, observe, compare. No retry or
  rollback after indeterminate effects. Niri focus/move remains non-atomic against external input.
- `map_preview`: escaped offline schematic and complete HTML ledger. CSS is packaged beside the
  module; no access to a source checkout or external design service is needed after installation.
- `cli` / `__main__`: console script and `python -m` entrypoints; no private infrastructure imports.

## Evidence model

Observed is not desired; desired is not approved; approved is not executed; acknowledged is not
verified. Layout verification is not native application-state verification or memory recovery.
Process pins include boot context, PID start ticks, executable hash/inode/device and cgroup.
No title heuristic or PID alone establishes continuity across compositor/process replacement.

## Tests and packaging

Pure fabricated fixtures cover selectors, missing windows, unknown identity, absent output,
privacy, immutable storage, stale/expired/replayed approval, writer exclusion and ambiguous effects.
A handwritten action-order oracle complements fake transport self-consistency tests. No test sends
live desktop actions. Build tests should exercise the installed wheel from outside the repository
and verify packaged map assets and absence of runtime dependencies.

Wheel contains only the Python package/assets plus license metadata. Sdist uses an explicit
source allowlist. Local private template snapshot context and runtime state are not distributed.
The source tree's reusable code is Apache-2.0; generated personal capture data is never sample data.
