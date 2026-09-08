---
summary: "Portable reconstruction orchestration, exact internal protocol, synthetic installed-console proof and outstanding review gates."
type: "implementation-note"
---

# Portable integrated reconstruction slice

## Implemented scope

Added `recovery*.py` modules and bounded routing in the existing CLI for fresh reconstruction
planning, exact loss/association-omission approval, reconstruction, inspect and fresh verification.
No second console script, runtime dependency, machine import or real native adapter was added.
Exact restart/migration gates and layout reconciliation remain separate. Capture/preview do not
invoke recovery adapters. Existing preview renders the original target topology with explicit
coverage/loss/omission warnings, not invented replacement window identities or native recovery groups.

The owner profile is anchored in the account-database home, independent of environment/config/state
roots. Its pins are independently checked before every adapter phase. A private socketpair carries
closed bounded JSON; ordinary adapter stdout/stderr is discarded. Effects use durable per-effect
intent/permit/result exchanges and expiry/liveness gates. Cancellation closes IPC and waits; it never
kills/retries the worker. The compositor flock is inherited only by the worker. A fixed canonical
Store holds prepared/CLI-consumed/ready fences, indexed intent/result evidence and terminal history.
Unresolved history blocks reconstruction across state-root copies. Fresh verification does not
promote interrupted effect history. Exact typed omissions never waive ownership, process identity
or protection and cap successful status at verified-with-accepted-omissions.

The [internal protocol](../docs/project/2026-09-06-integrated-reconstruction-protocol.md) specifies
all profile/config/wire/phase/proof schemas, endpoint invocation, private manifest responsibilities,
worker liveness/claim obligations and crash fencing for the separately owned machine implementation.
`tests/test_recovery_backend.py` is a reusable fabricated endpoint, not production adapter code.
Its only effects are scratch log entries and an isolated Python FD-inheritance oracle.

## Initial implementation validation (historical, before review fixes)

- Initial `UV_OFFLINE=1 just ci`: Ruff lint and formatting passed; **73 tests passed**. The command
  then failed the source privacy scanner on pre-existing foreign `.ontology/` state: a machine-bound
  JSON path, database/WAL/SHM binary files and runtime snapshot files. Those files were present at
  initial readback and are outside this delegated mutation scope; they were not edited or removed.
  **The checkout's full CI is not green.**
- Separately, initial `UV_OFFLINE=1 uv build` passed: wheel and sdist produced.
- Initial `UV_OFFLINE=1 uv run --frozen python scripts/ci/package-smoke.py` passed. It installed the
  wheel into a disposable venv outside the checkout, drove the actual public console script through
  capture/plan/preview/approve/reconstruct/verify/inspect/history, exercised a separately accepted
  fabricated omission, checked replay/restart/migration refusal, and verified no runtime dependencies.
  Fake profile/capture/lock-root injection exists only in that disposable interpreter's sitecustomize;
  it is not a shipped production bypass flag. The endpoint itself runs through real private IPC.
- The built sdist's own `scripts/check-portability.py`, run from a temporary extracted archive,
  passed. This distribution check does **not** replace the failed current-checkout CI gate.
- `git diff --check` passed. Scoped diff/status readback retained the pre-existing contributor-contract
  edit, design/plan documents and foreign state. No commit, publication, global installation, task
  mutation, real compositor/lock access, real adapter/native launch or signal/service effect occurred.

Tests exercise malformed/oversized/wrong-phase/extra-field responses, discarded noisy diagnostics,
source/interpreter pin drift including after readiness, exact confirmation/losses, stale/expired and
cross-root replay, incomplete crash fences/legacy coverage, every native proof dimension, omission
rules, per-effect expiry, worker failure after intent, inspectable unresolved intent references and
parent disconnect before/between effects. A synthetic coordinator exits without signalling; the
still-running worker alone retains exclusion. Fake application launch independently checks that
it does not inherit the lock descriptor. Scratch honors TMPDIR.

## Review-driven concrete improvement and hardening

The independent implementation review found a missing parent-directory crash-durability guarantee,
a torn-record diagnostic failure, lost decision context in transport-failure receipts and three
strict JSON framing/decoding defects. This pass fixes those findings without a claimed improvement
multiplier:

- **Durability:** previously, mkdir hierarchy names were not parent-fsynced. Store now establishes and
  validates every directory edge root-to-leaf, fsyncing the directory and its parent before descendants
  or records; existing edges are synchronized too, covering an earlier interrupted mkdir. No permission
  repair or symlink acceptance was added. A handwritten oracle records real mkdir/fsync order and
  independently asserts each ancestor/Store root/marker directory becomes durable before record fsync
  and the dispatch sentinel. Injected canonical directory-sync failure prevents the execute phase.
  These are syscall-order/failure tests, **not power-loss hardware proof**. Filesystem/storage must
  honor successful ordered file/directory fsync, exclusive creation and a stable trusted hierarchy.
- **Torn accounting:** previously, one malformed terminal stopped inspect before intact intents were
  exposed. Admission and fresh verification retain strict refusal. A separate read-only diagnostic
  projection now classifies each attempt and each intent/result independently, preserves valid refs,
  marks missing/invalid/unreadable evidence explicitly unknown/unresolved, and never treats absent
  evidence as no effects. Target metadata/adapter failure does not hide valid canonical evidence.
  No diagnostic branch repairs/recreates marker directories or grants retry authority. Terminal
  accounting additionally checks its indexed results against the saved receipt's event list.
- **Decision context:** normal and proof-unavailable receipts use one constructor. Before-permit,
  after-dispatch and invalid-final-proof failures retain coverage, exact typed accepted omissions,
  unsupported process memory and unverified provider/human dimensions, with overall coverage false.
- **Wire strictness:** explicitly decode UTF-8 rather than bytes autodetection; reject overflowed
  floats as well as NaN/Infinity; exclude exactly the framing LF from the one-MiB JSON bound. The
  exact maximum frame now passes, while UTF-16/UTF-32, nonfinite values, duplicates and overflow fail.
- **Execute fault matrix:** real scratch subprocess streams now test wrong request/phase, duplicate/
  out-of-order/orphan exchanges, invalid/trailing final proof, nonzero exit after final proof, and
  exact/oversized final frames. Handwritten scratch-effect sequences prove no later dispatch in these
  fabricated scenarios. Actual elapsed five-second lease tests exercise stalled responses and a
  worker independently expiring a permit while its test-only patient coordinator keeps IPC open.
  Existing before/during/between-disconnect and inherited-lock tests remain in the suite. Coordinator
  revocation and the reviewed worker's duty to cease effects are distinct—not sandbox enforcement.

The task-scoped orchestration test path is `tests/test_recovery_orchestration.py`; additional tests
are split into `tests/test_recovery_hardening.py` and `tests/test_recovery_execute_faults.py`.
The protocol reference documents the updated diagnostic/receipt behavior and durability assumptions.

### First review-fix validation (historical)

- Ruff lint and formatting checks passed over the declared complete source/test/script scope.
- Then-current `UV_OFFLINE=1 just ci`: **110 tests passed**; the subsequent portability/privacy scanner
  still fails on the same pre-existing foreign `.ontology/` machine-bound JSON, binary database and
  runtime snapshot artifacts. The full checkout gate is **not green**. Neither scanner policy,
  Git ignores nor those foreign files was changed to hide the blocker.
- `UV_OFFLINE=1 uv build` passed for the current wheel and sdist.
- `UV_OFFLINE=1 uv run --frozen python scripts/ci/package-smoke.py` passed with the current installed
  console script outside the checkout, all phases and the fabricated omission workflow. This remains
  isolated synthetic integration, not the stopped machine endpoint integration.
- The first full post-fix run exposed one ordinary Store diagnostic regression: its symlink refusal
  text no longer matched the established contract. The static `symlink` diagnostic was restored;
  the subsequent full run above passed all 110 tests. This historical failure is not hidden by the
  focused tests that preceded it.

Independent re-review should focus on directory-edge/file fsync ordering and failure propagation;
strict admission versus bounded non-authorizing diagnostic projection (especially missing/torn/
unreadable records); retained loss/omission context on unavailable proof; exact byte/encoding/finite
number rules; and the distinction between coordinator revocation and worker-enforced lease/cessation.
The expanded fault matrix is concrete hardening evidence, not a performance multiplier or native
safety certification.

## Final residual-review fixes

Three additional review findings were corrected without granting broader runtime authority:

- `recovery_profile.identify_profile()` now separates the safe fixed owner-profile/ledger identity
  from `_load_profile()` executable admission. It still requires a private, non-symlink, well-formed
  owner trust anchor, valid pin specifications and a safe fixed ledger; there is no caller-root/config
  fallback. `recovery.inspect_or_verify()` uses that identity for canonical-only inspection, so an
  endpoint comment, deletion or transitive source drift no longer hides an intact shutdown intent.
  Adapter accounting becomes unknown. `Adapter.call()` still runs full `load_profile()` validation
  before **every** subprocess invocation, including inspect. Approve/reconstruct/fresh verify retain
  full pin admission. Ancestor owners must be root or the current user.
- `cli.run()` routes reconstruction inspection before writable Store construction. It does not create
  or populate the caller's state root, even when it is exactly the canonical ledger. Canonical sources
  remain read-only. Missing terminal directories/markers and malformed other attempts remain visible
  as missing/invalid, rather than being recreated on the route into inspection.
- `recovery_adapter.Adapter.call()` refuses heartbeat while an effect is pending. The matching
  effect-result must arrive first; no continue is sent on violation. Actual scratch streams test
  this both before and after dispatch, retaining exact omission/coverage/nonclaim metadata and one
  unresolved intent, with no subsequent physical effect or automatic cleanup.

Final re-review targets are the exact functions above plus `pin_spec()`/`pin_file()` and the tests
`tests/test_recovery_residuals.py` and the pending/dispatched-heartbeat cases in
`tests/test_recovery_execute_faults.py` / `tests/test_recovery_backend.py`. The residual tests exercise
intact evidence after pin drift, no adapter invocation on invalid pins, unsafe/malformed anchor
refusal, and CLI inspection with equal, separate and nonexistent state roots. A canary forbids any
writable CLI Store construction in the aliasing tests.

### Current final validation

- Focused residual/execute suite: **30 tests passed**.
- `UV_OFFLINE=1 uv run --frozen ruff check src tests scripts/check-portability.py scripts/ci/package-smoke.py`: passed.
- `UV_OFFLINE=1 uv run --frozen ruff format --check src tests scripts/check-portability.py scripts/ci/package-smoke.py`: passed.
- `UV_OFFLINE=1 uv run --frozen pytest -q`: **123 tests passed**.
- `UV_OFFLINE=1 uv build`: current wheel and sdist built successfully.
- `UV_OFFLINE=1 uv run --frozen python scripts/ci/package-smoke.py`: current installed-console
  synthetic workflow passed outside the checkout, including all phases and the omission workflow.
- Broad `just ci` was not repeated for this narrow residual pass. Its known out-of-scope `.ontology/`
  privacy failure remains unresolved, not hidden by these passing synthetic/package checks.

No live effects, actual owner-profile invocation, AK/Git mutation, global installation or foreign
state changes occurred. This is not actual machine endpoint integration or native safety proof.

## Controller verification and stopping point

Independent final focused review accepted the portable slice against the remaining diagnostic and
protocol findings, with **31 independently executed synthetic tests passing**. It did not accept
machine integration, full CI or live safety. The controller then reran `UV_OFFLINE=1 just ci`:
lint/format and **123 tests passed**, followed by the same privacy-scan failure. The machine's
separate candidate/retired-entrypoint suite also passed, but its actual adapter endpoint is absent.
No manually invoked candidate substitutes for that missing integration.

Generated-state attribution is bounded: `.ontology/` was absent from the controller's initial
clean readback and appeared during its tool-assisted source inspection, before implementation
children began. It was therefore pre-existing **to those children**, not established pre-session
operator dirt. Timing is consistent with code-intelligence tooling, but the precise writer has
not been proved. Do not delete active owner state or weaken the scanner; route safe externalization
and ignore/distribution policy to the state-producing owner before claiming full checkout CI.

The controller verified the held machine additive source still matches its staged bytes. Concurrent
unrelated machine repository changes are not this slice's commits or recovery effects. Neither repo
received a commit from this controller or its children. Unperformed native coverage, source-pinned
protected/controller admission and specific association-loss decisions remain future gates.

## Subsequent blocker resolution — 2026-09-07

The operator reported a separate manual daemon recovery and explicitly prohibited further Ghostty
restarts. That recovery is not evidence for this adapter. No live Ghostty/probe, service, window,
layout, signal or native-session operation was performed in the subsequent work.

The generated-state writer was identified as the code-intelligence bridge's live child. Its state
was left untouched. The operator approved a narrow optional development-state exclusion, with
stronger checks rejecting tracked/exported tool state and product runtime data. Exact package input
rules now include all three linked reconstruction contracts and exclude private artifacts. A
retained directory-traversal failure was also fixed. Independent review accepted those changes;
current parent-run `UV_OFFLINE=1 just ci` passes **211 tests**, lint/format, privacy, builds and the
installed-console smoke. See [privacy notes](2026-09-06--implementation-development-state-privacy.md).

Machine source now implements the real internal endpoint, with installed public CLI integration
against low-native substitutes. Independent review found concrete lifecycle/accounting/loading/
identity/dispatch defects; remediation and regression review closed the identified failures. The
last fix remeasures native closure before subsequent effects and at fresh verification entry/exit.
These are actual correctness improvements, not a measured multiplier or native compatibility proof.

A major functionality gap remains: the resulting restricted static-capsule contract is not a usable
profile for ordinary dynamic Ghostty/Pi/Jiti, and btop is unsupported. Fabricated inert native inputs
cannot establish such a profile. The implementation remains source-only/synthetic and must not be
presented as operational reconstruction merely because its refusal and orchestration tests pass.
The no-restart instruction stays in force. The machine task remains open for usable native-profile
work; no manual command sequence or weakened gate substitutes for it.

## Remaining boundaries

This is portable orchestration and fabricated evidence, **not live safety certification**. The machine
owner still must implement/review complete native ownership/ancestry/pidfd/service boundaries,
transitive dependency closure and running images, private legacy accounting, immutable native
selection, causal bootstrap/window/surface identity, actual cwd/runtime proof, replacement-only
geometry/protected ordering and all physical-effect instrumentation. The coordinator checks the
owner-declared pin set; it cannot establish the truth/completeness of that owner's declaration or
native evidence by itself. The protocol is trusted reviewed code, not a sandbox.

The focused portable review and subsequent machine guard reviews are recorded above. Independent
review of any future normal-profile implementation and separately approved native/operator
verification remain mandatory; the existing reviews do not establish that missing functionality. Runtime testing here used CPython 3.13; Python 3.11 syntax checks are present, but
this work did not execute a Python 3.11 interpreter. A defective non-exiting worker deliberately can
block the coordinator rather than trigger unsafe timeout cleanup. Unknown/malformed canonical
records fail closed; there is no repair/migration/reset command. No specific real loss or omission,
provider usability, semantic completeness, memory restoration or human acceptance is claimed.
