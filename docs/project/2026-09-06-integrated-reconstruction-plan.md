---
summary: "Ordered owner-scoped implementation, independent review, improvement, hardening and live-proof gates for integrated reconstruction."
read_when:
  - "You execute the integrated reconstruction design after owner acceptance."
type: "plan"
---

# Integrated reconstruction implementation plan

**Status: Pi/Claude/Codex/btop implemented and independently reviewed with isolated integration
tests; native desktop qualification unperformed. Live stage not executed.**
The existing installed CLI drives the actual machine adapter through all phases in isolated tests,
including Pi, readable-image/capability-limited btop and mixed or utility-only selections. The static
capsule is replaced with closed recovery-control code and an explicit trusted installed platform.
Public v1 remains supported; exact v2 utility identities, limits and accounting are implemented.
Independent review defects in host classification, diagnostics, preserved-service verification and
normal replacement-host reparenting have been corrected and rechecked. Independent public review
accepted 161 tests (70 new) and eight installed smoke cases; the parent actual checkout passed
`UV_OFFLINE=1 just ci` with 343 tests, a new build and installed smoke. Independent machine final
review accepted six native fixes after 187 application tests and eight independent cases; recorded
machine source/full validation passed 686 tests with five native Pi skips. These are separate,
non-additive evidence sets; the later combined parent run was still running, with no newer total
claimed. See the shipped [validation summary](../usage.md#recorded-validation-and-qualification-limits)
for categories and qualification limits. Chronology is checkout-only:
`diary/2026-09-07--implementation-multitool-recovery.md` (deliberately excluded from the sdist).
The machine owner separately validated real Pi resume using fabricated sessions inside a filesystem
and network sandbox. That is not Ghostty, service, provider or live layout proof.
Production profile provisioning, native desktop admission and live dogfood remain unperformed.
The operator prohibits further Ghostty restarts; this plan grants no exception or live authority.
The expanded Pi/Claude/Codex/btop requirement retains the existing CLI and v1/v2 contract. Public
work covers opaque three-reference and mixed-utility regressions, not machine tool detection or
native semantic identity. The private `machine.v3` implementation adds Claude/Codex alongside Pi/btop
without changing public schemas or adding a CLI. Isolated machine tests verified app-kind-scoped
ID collisions, same-kind deduplication and actual native-shape callback/log fixtures. Native proof
predicates remain mandatory; unknown or unproved helpers block. Real Claude/Codex sandbox prototypes
provided callback/FD/initialization evidence, not permanent native opt-in tests or full certification.
A faulty Claude harness prevented clean exit; one isolated sandbox remains held awaiting operator
cleanup approval. No clean Claude compatibility or cleanup authority is claimed. See the
[coverage table](../usage.md#conversationtool-coverage-and-evidence-limits).
Depends on the [design packet](2026-09-06-integrated-reconstruction-design.md).
Task IDs, lease state, owner decisions and private runtime evidence belong in external authority
records, not this portable source. Register exact owner scopes before implementation; a completed
bootstrap task and an expired machine-task lease are not new authority.

## Stage 0 — authority and product decision

- Verify both owning repositories and scoped Git status; preserve all foreign/staged source.
- Record the standalone missing-direction-node failure. Ask the owner to authorize the minimal
  native direction representation; do not fabricate a healthy direction check or legacy-import
  unrelated documents. Link newly scoped work only after the owner surface permits it.
- Accept or revise the distinct loss-bounded reconstruction contract. Exact restart/migrate stay
  blocked. The explicit reconstruction exception to launch/termination policy needs a contributor
  contract update, preceded by the mandated resource-loader/system-prompt source preflight.
- Scope standalone integration separately from machine adapter work. Reconcile an existing machine
  claim only by its exact task/lease protocol, or register a new bounded integration task. Do not
  release all expired tasks, steal generic claims, alter the held additive slice, or widen old scope.
- Confirm the internal adapter architecture: no operator-facing second CLI or manual execution path.

**Exit:** exact active task scopes and explicit product decision; no live effects authorized by this gate.

## Stage 1 — portable orchestration, tests first

Proposed standalone implementation scope (finalize exact names when registering the task):

- `src/niri_desktop_continuity/cli.py`, `planner.py`, `approval.py` and `store.py` only for typed
  routing/storage changes; preserve existing default commands and restart refusal.
- New focused `recovery_protocol.py`, `recovery_adapter.py`, `recovery.py`, and
  `recovery_verification.py` modules, split further only to meet readability/owner boundaries.
- Reuse `operation_lock.py`; change it only if the reviewed worker descriptor-lifetime seam needs
  an explicit API. Existing layout use must not regress.
- `tests/test_recovery_*.py`, focused existing CLI/approval/store regression tests, and
  `scripts/ci/package-smoke.py` for installed-console-script orchestration.
- `README.md`, `AGENTS.md`, `docs/architecture.md`, `docs/usage.md`, this design/plan and a scoped
  diary entry. No visual restyling. If renderer changes prove necessary, read DESIGN.md and its
  design-tool contract first; do not smuggle UI scope into protocol work.
- No runtime dependencies, second console script, machine imports, personal configuration,
  source-tree-only bootstrap or private IDs in public artifacts.

Implement strict finite protocol schemas and phases, explicit configuration and source pins,
bounded IPC/diagnostics, state/expiry/approval gates, canonical lock handling and durable attempts.
Use a fabricated adapter with an auditable effect log and fabricated Niri transport. Prove that
capture/preview never invoke adapter effects, and approval cannot admit unknown or unsupported state.

**Exit:** installed existing CLI drives the full synthetic phase sequence outside the source tree;
restart/migrate remain blocked and absent/unreviewed adapters cannot reconstruct. Not live recovery.

## Stage 2 — machine-owned adapter integration

Proposed machine scope: the reconstruction package, its focused tests, a new internal adapter
endpoint under the same package, and its specific plan/usage/diary documentation. Include the
owner-generated diary index only through its generator. Do not touch the additive recovery
package, existing staged session tools, unrelated Justfile/Phase E files, continuity prototype,
service definitions, global configuration, private proof sources or immutable shared docs.

- Extract callable planning/admission/effects/verification seams without invoking the old candidate
  CLI parser. Endpoint operates only when called by the public coordinator under protocol gates.
- Replace checkout bootstrap assumptions with the pinned internal endpoint invocation. Keep exact
  saved-file selection, no prompt/task continuation, provider binding and safe native environment.
- Remediate every high-consequence design finding before effect availability: lock/compositor,
  per-effect expiry, native runtime/cwd proof, full recovery placement and unresolved-child evidence.
- Preserve complete owned-ancestry census, pidfds, UID/boot/birth/image checks, protected/controller
  exclusions, narrow opaque-utility corroboration and coverage refusal. Strengthen, do not bypass.
- Add a real read-only verifier; persisted status is history, not a current native/layout proof.
- Introduce canonical unresolved-attempt reconciliation that notices earlier candidate intents,
  including incomplete old records. Never escape an indeterminate attempt by selecting a new root.
- Keep service start/stop checks fresh and prove no unadmitted service members can be signalled.
- Tests must substitute native/process/service/compositor boundaries, boot context and lock paths.
  No test touches live lock directories, signals, or native session stores.

**Exit:** actual adapter callable through the installed public CLI with injected synthetic boundaries;
reviewed source/dependency pins and no manual side-channel execution. No live invocation yet.

## Stage 3 — independent implementation review

Commission a new independent review of the integrated diff, not just reuse the candidate review.
Reviewers receive exact scopes, invariants, current test evidence and immutable source references.
Do not give a mutation reviewer broad access to held machine source or effects.

Review targets: admission reachability; PID reuse/escaped cgroups/protected overlap; freeze and
service races; expiry between effects; parent/worker death and lock inheritance; cross-root replay;
unknown owned Pi; misleading sidecars; launch-before-proof failures; lost tab ACK; fallback timing;
focus/placement races; source/config/native-file drift; private-data leakage and installed packaging.

**Exit:** every high-severity finding fixed and independently rechecked, or effects remain blocked.
A source-only review does not count as native/runtime proof.

## Stage 4 — concrete improvement pass (no invented multiplier)

Use the first integrated implementation as baseline and record actual before/after observations:

| Target | Concrete improvement and evidence |
|---|---|
| Honest verification | Independent native identity, ownership, old-tree exit, layout, recovery-group and protection dimensions |
| Action safety | Prefix-preserving replacement-only moves; count actions in exhaustive supported cases |
| Operator clarity | Stable blocker codes and exact unresolved identity counts without leaking transcript/environment |
| Failure diagnosis | Durable causal child and per-effect evidence even when window/native binding fails |
| Integration | One installed operator command family; no instructions to invoke a private controller manually |

Choose and implement the highest-value changes found by review. Do not call an arbitrary refactor
or added test count a measured 10× improvement; report the dimensions actually improved.

**Exit:** documented concrete changes, before/after tests or measurements, independent follow-up.

## Stage 5 — hardening and governed validation

Required adversarial matrix:

- Unsupported adapter/profile/version/config, malformed/oversized response, wrong request/attempt
  identity, nonzero exit, noisy diagnostics, missing endpoint, changed source/interpreter.
- Blocked/expired/replayed approval; same plan across state roots; simultaneous writers; coordinator
  death with live worker; leaked lock descriptor into a new app; unresolved previous effect.
- Boot/PID/image/ancestry/UID/cgroup drift; missing child/census edge; controller and protected-tree
  overlap; service changes/new members; narrow utility capability/argv mismatch.
- Missing or duplicated native identity; wrong actual cwd/runtime; stale or forged sidecar; saved
  file/inode/header change; concurrent unrelated native/window appearance; no title fallback.
- Failure before/after every signal/service/launch/IPC dispatch; timeout and missing ACK; no second
  launch after uncertainty; all possible new children retained or marked unresolved.
- Handwritten mixed-column counterexample and exhaustive admitted permutations; protected order
  drift; wrong recovery workspace/label; temporary holds not removed; wrong size/focus; ACK no effect.
- Test isolation, Python 3.11 syntax, zero runtime dependencies, wheel/sdist privacy and imports.

Run current `just check` and `just ci` (offline where supported); installed console-script smoke
must exercise every orchestration stage, not only Python helper calls. Run the machine repo's
scoped reconstruction lint/format/type/compile/tests and strict docs checks with declared fake
boundaries. Run normal commit gates if committing; do not bypass scanner failures or whole-index
commit a shared checkout. Record historical failures separately from new validation.

All safety-relevant improvement/hardening changes after the first implementation review require
independent re-review. Final reviewed source/dependency pins must match the actual executable tree.
Also test omission-policy admission/status, conflicting ledger configuration, incomplete two-record
fencing, legacy-state coverage and disconnect before/during/between effects.

**Exit:** current recorded validation and final re-reviewed pinned implementation. No live admission implied.

## Stage 6 — controlled live dogfood, only through the existing CLI

Before any live effect:

1. Use the proposed `niri-desktop-continuity inspect --kind reconstruction` surface to account for
   canonical and owner-bounded legacy attempts: no effects, completed, or indeterminate. Unknown
   legacy coverage blocks. Do not manually edit state, retry an indeterminate attempt or erase its fence.
2. Bind this controller's fresh long-lived ancestry, all protected/non-target apps and the two
   separately proved healthy terminals. Preserve their source-pinned proofs unchanged.
3. Through the CLI/adapter, refresh the entire desktop, target trees, executable identities,
   service contract, native session presence and complete coverage. Historical PIDs/counts are hints.
4. Resolve any owned Pi association gap with bounded owner metadata (session JSONL only through jq
   metadata projection). The alternative exists only if the product's typed omission feature has
   been accepted, implemented and independently reviewed: use the existing CLI to create a new
   proposal with exact process-pin omissions and separately confirm each plus the whole plan digest.
   Unknown ownership/process identity always blocks. No skipped-form consent or complete-coverage claim.
5. Render and inspect the exact fresh plan, losses, protected set and verification obligations.
   Explicitly confirm the plan and idle-desktop requirement. Re-admit under lock immediately before effects.
6. Invoke only `niri-desktop-continuity reconstruct`; never run the machine candidate manually.

After dispatch, independently verify through `niri-desktop-continuity verify --kind reconstruction`:
exact saved-session/native runtime/cwd; causal window/tab ownership; pinned new images; admitted
old-tree termination; service status; complete actual layout/focus/recovery labels; protected app
identity and placement. A fresh CLI capture/preview is a supporting observation, not a substitute.
Human usability/context acceptance remains separately requested; do not send an automatic prompt.

Any partial result stops this procedure. Report stopped/surviving/unresolved processes and effects
without automatic cleanup or retry. A new reconciliation requires a separately scoped decision.

**Exit:** source-owned evidence for each measured dimension or an explicit partial/blocker report.
No assertion of exact memory/tab fidelity, freeze fix, publication or full task completion follows.

## Stage evidence and closeout

Record design, plan, implementation, independent review, improvement, hardening, offline validation
and live dimensions separately in their owner task/evidence surfaces. Docs describe contracts and
limits; they are not a task ledger or a substitute for receipts. Mark a stage complete only when its
exit condition has corresponding current evidence. Keep unperformed stages and blockers explicit.
