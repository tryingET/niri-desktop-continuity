---
summary: "Niri-only module boundaries, evidence model and portable packaging."
read_when:
  - "You change the runtime, state model or packaging."
---

# Architecture

One CLI, no daemon, no platform plugin framework. Python standard library at runtime; Niri/Linux
is the supported environment. Plain JSON on stdout composes with Unix tools; errors go to stderr.
No exact application restart/migration adapter is implemented. A distinct loss-bounded reconstruction
coordinator drives a separately owned and reviewed machine adapter, which does not ship in the wheel.
Pi/Claude/Codex/btop support is **implemented and independently reviewed with isolated integration
tests; native desktop qualification unperformed**. The private `machine.v3` implementation uses
unchanged public v1/v2 schemas and the existing CLI; it is not a public protocol v3.
See the [coverage table](usage.md#conversationtool-coverage-and-evidence-limits) for proof limits.

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
- `recovery` / `recovery_verification`: fresh proposal/admission, exact losses and typed process-pin
  omissions, deterministic approval, execution and non-upgrading fresh native verification.
- `recovery_protocol` / `recovery_requests`: closed bounded, exactly routed v1/v2 schemas and separate native proof
  dimensions, never native transcript/environment payloads or arbitrary effect commands.
- `recovery_additive`: distinct saved-set protocol branch on that same lifecycle. Missing,
  present and unresolved refs partition a bound private selection; no old live PID is invented.
  The coordinator permits only an exact missing-ref launch and admitted-focus restoration,
  never shutdown/service/layout. Already-present-only execution has a canonical zero-effect
  receipt. Its proofs concern native identities/images, focus and protected preservation,
  not old-tree exit, services or reconstructed geometry. V1/v2 replacement behavior is unchanged.
- `recovery_profile` / `recovery_adapter`: account-home owner trust anchor, closed recovery-control and critical platform pins,
  explicit isolated JSON socketpair IPC, per-effect permits, liveness and cancellation without kill.
- `recovery_ledger`: fixed owner-profile canonical Store, prepare/CLI-consume/ready crash fence,
  cross-root replay refusal and retained indeterminate history. Worker inherits the compositor
  lock; applications must not. An unresolved attempt blocks new reconstruction, not automatic repair.

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

## Reconstruction integration boundary

The [exact internal protocol](project/2026-09-06-integrated-reconstruction-protocol.md) fixes the
separately owned machine adapter's contract. The coordinator validates all declared profile/source pins before
every phase. Recovery-control Python code is closed and source checked; installed OS/ELF/Pi/Jiti
is explicitly owner-trusted, not an exhaustive dependency capsule or sandbox. The owner still pins
critical executable/entrypoint/provider/presence/config surfaces and proves native ownership,
observable running images, saved-file/runtime/cwd/bootstrap presence, services and layout.
`recovery_utilities` validates only the exact v2 btop identity/proof branches. Capability-bearing
btop may explicitly lack an observable running image; separate exact utility-ref approval caps
success and exposes incomplete image coverage. No synthetic sessions or utility association omissions.
Canonical inspection routes historical versions without executing foreign-profile code; strict
admission and fresh verification still refuse foreign or damaged accounting.
Protocol validation is not a sandbox or native-state proof. Endpoint read-only phases are an audited
no-effects contract, not OS capability isolation. A defective effect worker can retain exclusion and
block indefinitely; the coordinator does not kill it, retry or clean up after ambiguity.

Installed wheel smoke drives the actual console script outside the checkout through all reconstruction
phases with a fabricated endpoint and isolated capture/profile/lock boundaries. Synthetic tests also
exercise parent disconnect, worker-retained exclusion, application FD noninheritance, replay, omissions
and independent native-dimension counterexamples. Three opaque saved references and mixed utilities
exercise unchanged v1/v2 semantics, not a public app classifier or native identity producer. Machine
implementation/review has separate owner evidence; deployment qualification and live desktop proof
remain unperformed. Preview retains the original target topology, with explicit coverage,
loss and omission warnings; it does not fabricate replacement identities or draw native recovery groups.
