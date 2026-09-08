---
summary: "Proposed existing-CLI orchestration of explicitly loss-bounded, machine-adapted saved-conversation reconstruction."
read_when:
  - "You review or implement the reconstruction boundary and its admission contract."
type: "design"
---

# Integrated saved-conversation reconstruction

**Status: Pi/Claude/Codex/btop implemented and independently reviewed with isolated integration
tests; native desktop qualification unperformed.**
This packet retains the original design baseline below, not a description of today's missing code.
The portable coordinator and separately owned machine adapter support Pi/Claude/Codex saved-conversation
recipes and typed btop utilities through the existing CLI and unchanged public v1/v2 schemas.
The private `machine.v3` implementation is not a public schema upgrade.
Independent review defects have been fixed and rechecked. The static-capsule requirement
is retired: installed native runtimes are an explicitly owner-trusted platform, not an exhaustive
filesystem closure. The machine implementation is not shipped in the public wheel.
No production profile was provisioned and no live desktop reconstruction was performed. See the
[protocol](2026-09-06-integrated-reconstruction-protocol.md) and
[shipped validation summary](../usage.md#recorded-validation-and-qualification-limits).
Historical chronology is checkout-only: `diary/2026-09-07--implementation-native-recovery-integration.md`
(excluded from the sdist).
Task, decision, lease and evidence authority remains external to this public repository.
This document supplies no live-effect approval or native desktop safety certification.
The [coverage table](../usage.md#conversationtool-coverage-and-evidence-limits) tracks the broader
Pi/Claude/Codex/btop requirement without upgrading existing evidence. Generic opaque references and
six independent native predicates already express it in v1/v2; no app-name field or new schema is
required. Machine isolated tests verified cross-app native-ID separation and same-app deduplication;
public fabricated multi-conversation tests cannot certify those producer semantics. Real sandbox
prototype evidence is limited, including an unclean Claude harness exit and a held sandbox awaiting
operator cleanup approval. Permanent real Claude/Codex native opt-in tests were not delivered.
Unknown or unproved helpers still block; implementation review is not full native/runtime certification.

## 1. Verified product gap at design baseline

The current CLI exposes capture, plan, preview, approve, reconcile, verify and history.
`planner.build_plan` always blocks restart/migrate; `approval.validate_plan` accepts only
layout reconciliation. `reconcile` handles same-workspace single-tile column insertion,
not application recovery. `verify` measures same-instance layout, not native sessions.
There is no adapter configuration, reconstruction admission, native resume, or fresh
reconstruction verifier. An offline preview cannot stand in for those missing capabilities.

Existing reusable guarantees are private content-addressed storage, deterministic approval,
expiry, source/compositor/focus checks, a per-compositor lock across state roots, durable
pre-effect intents, no replay after uncertainty, and measured rather than ACK-only layout.
Preserve them. Runtime and wheel installation remain Python 3.11+, standard library only.

The machine-owned candidate contains planning, ancestry census, pidfd shutdown, bootstrap,
causal host/window binding and replacement-only column placement. It is implementation
material, not an approved independent operator workflow or proof of successful recovery.
Its previous separate-entrypoint instructions do not define this product's integration.

## 2. Explicit product-boundary decision

Keep `restart` and `migrate` exact-continuity proposals blocked. Do not claim an exact
checkpoint/restart adapter exists. Add a distinct `reconstruct` intent with the narrowly
versioned `saved-conversations-v1` contract, available only through a reviewed exact adapter.

This is a proposed change to the current no-launch/no-termination boundary, not a silent
exception. Before code enables effects, amend the contributor/product contract explicitly:
only an operator-approved reconstruction may launch replacements and terminate its freshly
admitted old ownership set. No general launcher, arbitrary command execution, automatic
cleanup/rollback, daemon, other compositor, or arbitrary process-memory recovery is added.
Complete the context-loader preflight before editing the contributor instructions.

| Claim | Required proof or explicit limit |
|---|---|
| Saved conversation selected | Native store/file/header identity and original cwd, not title/recency |
| Saved conversation resumed | Exact native file/ID/cwd and current runtime/bootstrap identity |
| Window/tab ownership | Newly launched pinned host, unique Niri PID/window, distinct native surface |
| Layout reconstructed | Complete mixed target/protected ordering, membership, sizes and focus measured |
| Prior process memory | Unsupported; accepted loss, never recovered |
| Drafts, scrollback, shell memory, hidden-tab order | Accepted loss, never exact continuity |
| Known session with uncertain former tab grouping | Resume once in a labelled recovery group |
| Owned Pi process without native session association | Blocks; not covered by generic loss acceptance |
| Human usability, provider health, context semantics | Separate evidence; file header/sidecar alone insufficient |

Unknown ownership, birth identity or protected overlap always blocks. Unobservable running images
block except the separately typed, exactly accepted v2 capability-btop limit below; no loss decision
can waive those predicates. This proposal includes a separately approved omission of **session
association only**, for an otherwise fully identified owned process. It is not enabled by the
baseline loss flag. An existing-CLI `plan --omit-association PROCESS_PIN_DIGEST` option produces
a new blocked-for-review proposal containing the exact boot/birth/image-bound omission, its
reason and the unresolved native coverage count. `approve --accept-omission PROCESS_PIN_DIGEST`
must repeat each omission in addition to the whole new plan digest. No manual manifest editing.
Fresh observation must still prove that exact process and all mandatory ownership predicates.
Record owned native process count, associated process count, explicitly omitted association
count and unique saved conversations separately. The terminal status is at most
`verified-with-accepted-omissions`, never complete recovery or ordinary `verified`. This feature
requires explicit product acceptance and independent tests; absent that, missing association
continues to block. No specific omission has been accepted. A skipped form is no consent.

## 3. One public CLI, two implementation owners

The operator uses **only `niri-desktop-continuity`** for observation, plan, preview, approval,
reconstruction, receipt inspection and fresh verification. No second public CLI, manual
machine-script invocation, or instructions to finish recovery with another tool.

### Portable CLI owner

- Owns the typed orchestration state machine, exact-digest approval, source snapshot binding,
  compositor lock, expiry policy, durable consumption, private summaries and receipt status.
- Adds one small versioned recovery-adapter protocol, not a discovery/plugin framework.
- Validates request/response schemas, sizes, identities, protocol version and phase legality.
- Runs without an adapter installed: current read-only/layout commands retain their behavior;
  reconstruction fails closed with a specific unavailable/unreviewed-adapter reason.
- Does not import machine packages, embed machine paths/IDs, inspect native transcript bodies,
  ship private selections, or require a database/agent harness to install or test.

### Machine adapter owner

- Owns the exact Ghostty/Pi/service/native-presence integration and compatibility evidence.
- Owns private configuration, dependency/build/source pins, controller/protected references,
  process ancestry, native store inspection, environment handling and physical effects.
- Reuses reviewed candidate functions behind an **internal protocol endpoint**, not the old
  candidate command parser. Its terminal bootstrap is internal too, not an operator retry API.
- Remains outside the public wheel. Default capture/preview never loads it or executes
  discovered binaries. No arbitrary shell/argv field, PATH lookup, or plugin auto-discovery.
- Preserves protected recovery-controller source bytes and their existing private proofs.

A private, strictly validated configuration explicitly selects the absolute endpoint and
interpreter, content pins and supported protocol/compatibility profile. The ledger location and
identity are established by the machine owner's fixed recovery profile, not selectable through
configuration or `--state-root`; conflicting configuration refuses. The profile names a bounded
owner-supplied set of legacy attempt locations. Their accounting must be complete before admission;
unknown legacy coverage blocks. Configuration is inert data, not executable shell. Loading it
grants no effects. Same-user malicious code is outside the accidental-use safety model; digests
are not signatures.

Before starting **any** adapter phase, the coordinator independently checks the endpoint,
interpreter and closed recovery-control source pins against that owner-reviewed compatibility
profile, not just self-reported hashes or arbitrary caller pins. Revalidate at phase dispatch;
refuse observed drift. Reviewed code must check its running image/source bindings before effects.
Residual same-user file replacement races are not claimed eliminated by pathname hashing.

## 4. Command contract proposed at the design baseline (now implemented)

```text
niri-desktop-continuity capture
niri-desktop-continuity plan SNAPSHOT --intent reconstruct --adapter-config PRIVATE_CONFIG
niri-desktop-continuity preview PLAN --kind plans
niri-desktop-continuity approve PLAN --confirm PLAN --accept-losses saved-conversations-v1
niri-desktop-continuity reconstruct APPROVAL --apply --acknowledge-non-atomic-focus
niri-desktop-continuity verify ATTEMPT --kind reconstruction
niri-desktop-continuity history --kind receipts
niri-desktop-continuity inspect ATTEMPT --kind reconstruction
```

A plan command performs fresh adapter observation, not historical-snapshot execution. If the
supplied snapshot no longer agrees, return a structured blocker and require a new capture.
The plan contains a sanitized coverage/impact projection and content-addressed reference to
adapter-private material, not environments or session bodies. Existing default behavior of
`verify SNAPSHOT` remains layout-only. Reconstruction verification is explicitly typed.

`approve` repeats the whole plan digest and accepted-loss contract, revalidates read-only,
and writes deterministic approval; it never starts or stops anything. It cannot turn an
unsupported adapter, unknown ownership, or unknown process identity into an admissible plan.
An omitted session association follows only the separately typed decision in section 2, never a
broad flag. `inspect` projects current canonical and legacy attempt disposition and interruption
evidence through the CLI without authorizing effects or exposing environments. It is not fresh
native verification. Missing/ambiguous prior-state coverage blocks rather than implies no effects.

The CLI invokes the configured endpoint through bounded structured IPC without a shell.
Plan/admit/verify phases permit no desktop/process/service effects under the audited phase
contract, and receive no execution authorization. Private planning/verification evidence writes
are allowed. This is not OS capability isolation: tests must fail if these phases reach effect
transports. The execute phase accepts only the immutable admitted attempt, not free-form effect
commands or a new selection.
The coordinator holds the canonical compositor lock for the entire attempt; an inherited
lock descriptor keeps exclusion if the coordinator fails while its worker still runs.
Native child applications must not inherit that descriptor. Tests must prove this lifecycle.
Do not kill or retry an effect worker on timeout. Broken transport becomes indeterminate.
On detected coordinator disconnect/cancellation, the worker issues no new effects; it may only
observe an already-dispatched effect and durably record what is known. Retain exclusion until
it has ceased issuing effects. Use bounded/liveness-aware IPC so blocked output cannot silently
extend execution authority. Test disconnect before, during and between effects; an in-flight
operation may remain unresolved, never automatically reversed or reissued.

The adapter remains trusted physical-effect code, independently reviewed as such. Protocol
validation cannot prove a malicious adapter harmless. Pinning binds the reviewed implementation;
it does not manufacture compatibility or native-state proof.

## 5. Admission and execution state machine

`observed → proposed/blocked → approved → consumed → executing → verified|partial|indeterminate`

1. Collect a coherent current desktop and compositor socket/boot identity; inspect every
   selected host and current descendant, including descendants outside the service cgroup.
2. Bind the current long-lived controller ancestry. Exclude all non-target apps, controller
   trees and separately proved healthy protected terminals. Never signal historical PIDs.
3. Prove every selected native process accounted for; deduplicate saved conversations; distinguish
   missing identity from uncertain grouping. Recheck saved-file membership/header/inode and cwd.
4. Pin actual running images where observable, replacement build, interpreter, native runtime,
   provider extension, source set and service start contract. A narrow utility exception must
   explicitly report running image unobservable and independently corroborate exact capabilities,
   argv, file pin, UID/birth/parent and selected leaf ownership; never generalize to unknown Pi.
5. Under the same per-compositor lock, re-observe topology/focus/outputs/protected identities,
   coverage, pins, unresolved prior attempts and time. Rebuild and compare the exact plan.
6. Under lock, first publish a durable canonical prepared fence binding the approval/ownership
   set, then consume CLI approval, then mark the canonical attempt ready. Only the complete pair
   permits effect dispatch. Any crash/incomplete combination blocks subsequent effects and stays
   inspectable, even if no effect was known. Changing CLI state root, configuration copy, nonce or
   invocation cannot bypass an unresolved overlapping attempt. Do not erase previous records.
7. Journal each effect intent before dispatch and result after observation. Check expiry and
   expected state before every effect. Adapter and coordinator both enforce the same deadline.
8. Use only admitted pidfds for frozen-tree shutdown. Verify stopped state and repeat the complete
   ownership census before escalation. TERM while frozen is not graceful shutdown. Fork/reparent
   drift stops; a partial attempt may leave stopped processes. No SIGCONT/kill cleanup on failure.
9. Verify old admitted handles exited before starting replacements. Recheck service ownership
   before stop/start; do not infer completeness from its cgroup or allow unadmitted stop targets.
10. Launch each exact saved conversation at most once. Persist causal child identity as soon as
    available; an incomplete launch remains an explicit unresolved child, never silently omitted.
    Bind native runtime/cwd/session/surface and unique window ownership, not ACK or title alone.
11. Move/resize only replacements. Preserve protected relative order, supported original geometry,
    and full mixed columns. Verify recovery workspace membership/labels and removal of temporary
    holds. Restore current admission focus or its exact causal replacement, not historical focus.
12. Finish with separate observed proof dimensions. `verified` requires complete selected native
    coverage, causal ownership, pinned new images, old-tree exit, service contract, layout/focus,
    labels/holds and protected preservation. Approved association omissions can yield only
    `verified-with-accepted-omissions`, with explicit incomplete overall coverage. Neither status
    implies provider usability, transcript semantic completeness, human acceptance or memory
    recovery. Any missing mandatory dimension yields partial/indeterminate. A fresh verifier is
    read-only and does not erase or promote an interrupted effect history.

Any failure after an effect intent stops without automatic replay, new-nonce retry, rollback,
service repair, process cleanup, broader kill or fallback launch after ambiguous dispatch.
An idle operator is still required: Niri focus-plus-move is not atomic against external input.

## 6. Independent candidate assessment and required remediation

These are source/fixture findings, not live runtime observations:

| Finding | Required change before integration acceptance |
|---|---|
| Executor lacks per-compositor lock/socket identity | Use existing CLI lock and complete source identity across the entire worker lifetime |
| Candidate expiry is admission-only | Recheck deadline before every physical effect |
| Native matcher can count matching sidecar with wrong process cwd/non-Pi image | Corroborate actual cwd, supported Pi runtime and exact bootstrap identity; adversarial oracle |
| Final layout can pass with misplaced/mislabelled recovery host | Model every new recovery host, workspace label and temporary hold in final verification |
| Spawn failure can omit a known child from interruption summary | Durable spawn evidence plus explicit unknown-result inventory |
| Checkout-relative bootstrap and Python 3.14 exception syntax | Installed endpoint contract and Python 3.11 public compatibility; no copied checkout assumptions |
| Candidate receipt command only reads stored status | Real fresh verifier driven by the existing CLI |
| Missing owned Pi sidecar is a deliberate blocker | Preserve refusal; resolve through owner evidence or exact additional loss decision |

The fixed-prefix replacement-only ordering is promising reusable code. The handwritten
counterexample `[A,B,P,Q] → [P,A,Q,B]` with protected P/Q is corrected by moving only A/B.
Independent analysis confirms prefix preservation under the single-tile insertion model.
Permutation fixtures establish that model only, not compositor focus/IPC behavior.

## 7. Privacy and public-source contract

Keep runtime data outside Git in owner-only directories/files, reject unsafe symlink/hardlink,
ownership, size and permission conditions, and pin referenced private data against drift.
Do not copy captured environments into public plan/preview/receipt projections or stderr.
Prefer in-memory credentials; any necessary private environment persistence needs explicit
review and is never an ordinary exportable artifact. Use bounded jq-only native session metadata;
no transcript-body or secret/environment dump as a debugging fallback.

Public examples and test fixtures are fabricated. No local task/session identifiers, executable
paths, incident process tables or private attempt references belong in this packet's source.
Machine evidence stays with its owner; external task/decision records reference this design.

## 8. Acceptance and current nonclaims

See [the implementation plan](2026-09-06-integrated-reconstruction-plan.md) for ordered gates.
The minimum integration proof is an installed console-script process exercising plan, admission,
reconstruction and fresh verification through a fabricated internal adapter outside the checkout.
Unit calls alone or manually running the candidate do not satisfy it.

Portable implementation evidence is recorded separately; it does not establish actual machine
integration, destructive admission, Ghostty restart, native reconstruction, a measured improvement
factor, freeze-cause fix, human acceptance, task completion, global installation or publication.
Live operations remain blocked on missing normal-profile functionality, native compatibility and
current ownership/identity coverage, exact approval and verification readiness. The portable
checkout's validation now passes; this does not supply native proof. The operator has prohibited
further Ghostty restarts, so no live canary is authorized by continued source work.

## 9. Native integration reset and protocol v2 decision

Reuse reviewed saved-session recipes behind the existing CLI's thin internal adapter. Closed,
source-checked Python recovery-control code remains mandatory; proving an exhaustive OS/ELF/Pi/Jiti
dependency universe is not. The installed application platform is explicitly owner-trusted, not a
sandbox: critical executables, entrypoints, provider/presence implementations and configuration
remain pinned and freshly checked by the owner. Source pins attest the reviewed recovery
implementation, not every loaded byte systemwide. No dynamic recovery-control plugin discovery.

V1 schemas and historical identities remain unchanged. V2 adds only typed btop utilities, not
synthetic sessions or association omissions for utilities. An observed-image utility needs a real
running Pin. The capability-btop alternative explicitly records image unobservability, exact birth,
UID, parent, cgroup/argv, installed-file and capabilities evidence. Private corroboration must prove
a sole owned leaf and causal window. Approval repeats each such utility_ref separately; generic
loss acceptance cannot authorize it. Any such limit caps success at
`verified-with-accepted-limitations`; omissions remain visible independently. Image dimensions
cover only observable images, and overall image coverage is explicitly incomplete. A utility-only
selection can succeed without claiming saved-conversation recovery. Native/live proof remains
unperformed and no live effects are authorized. The exact schema is in the protocol's v2 section.
