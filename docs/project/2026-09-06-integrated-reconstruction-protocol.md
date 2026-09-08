---
summary: "Exact replacement v1/v2 and additive saved-reopen IPC contracts for separately reviewed machine endpoints."
read_when:
  - "You implement or review the machine-owned reconstruction endpoint."
type: "reference"
---

# Integrated reconstruction and saved-reopen internal protocols

Implemented portable coordinator and separately owned, independently reviewed machine endpoint;
**no production profile provisioning or live desktop safety certification**.
[Design](2026-09-06-integrated-reconstruction-design.md) and
[implementation gates](2026-09-06-integrated-reconstruction-plan.md) remain the product contract.
This document fixes the interface; machine code and private evidence do not ship in this package.
The endpoint is trusted, source-reviewed physical-effect code, **not an OS sandbox**.
A green fabricated workflow does not establish native compatibility or authorize a loss.

## 1. Wire types and limits

Sections 1–7 specify frozen v1 shapes; section 8 defines exact v2 changes, not optional fields.
Section 9 defines a separately versioned additive saved-set mode; it does not reinterpret v1/v2.
`V` = `desktop-continuity.recovery.v1`; `C` = `saved-conversations-v1`.
All objects below have **exactly** their listed keys. Unknown keys, missing keys, duplicate JSON
keys, nonfinite numbers, wrong types, unsupported phases and trailing messages refuse.
JSON is explicitly decoded as strict UTF-8 (UTF-16/UTF-32 autodetection is forbidden); one object
followed by LF per frame. Float parsing also rejects exponent overflow such as `1e309`, not only
NaN/Infinity literals. Maximum encoded JSON: 1,048,576 bytes, excluding exactly the terminating LF.
The stream reader removes that LF before applying the JSON byte bound; a maximum-sized JSON
object plus LF is valid. Additional final bytes/frames remain invalid. Arrays have at most 256 elements except canonical accounting,
which admits at most 1,000 attempts. Booleans are not integers. Responses contain no arbitrary
text, environments, paths, native bodies, argv, shell commands or exception strings.

`H` = lowercase 64-character SHA-256 hex. `digest(value)` = SHA-256 of UTF-8 Python
`json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)` (default ASCII escaping).
Digests are integrity bindings, not signatures. `H[]` is sorted, unique. `Count` is integer 0..256.
`Time` is a timezone-aware ISO-8601 timestamp understood by Python 3.11 `datetime.fromisoformat`.
Plans bind creation/deadline with lifetime 1..900 seconds. Absolute deadline applies to each effect;
a final observation/receipt may finish after it without granting further effects.

`Pin`:

```text
{boot_id: string matching [A-Za-z0-9-]{1,64}, pid: integer,
 start_ticks: integer, exe_sha256: H, exe_inode: integer, exe_device: integer, uid: integer}
```

All Pin integers are nonnegative and less than 2^63; pid/start_ticks/exe_inode are positive.
The coordinator checks the boot against the source compositor and UID against its own UID.
No title, PID alone, stale handle, or absent native process-image identity is sufficient.

`Selection`:

```text
{window_ids: positive-integer[], pids: positive-integer[], app_id: string|null,
 version: string|null, requested_window_ids: positive-integer[], requested_pids: positive-integer[]}
```

Integer arrays are sorted, unique, at most 256 entries, each less than 2^63.
Strings are bounded to 256 characters. Selectors are intersected by the existing planner;
the machine endpoint must independently establish the full selected ownership census.

## 2. Owner trust anchor, configuration and entrypoint

The fixed owner profile is the account-database home (`pwd.getpwuid(os.getuid()).pw_dir`) plus
`.config/niri-desktop-continuity/recovery-profile.json`. **HOME, XDG variables, CLI state root,
config location and config copies cannot select this trust anchor.** No profile-discovery API or
profile-install command is provided. The machine owner provisions/reviews it independently.
Changing this anchor is an owner action, not a retry mechanism. Preserve its ledger identity and
all historical accounting across upgrades. Existing foreign-profile ledger entries fail closed;
there is no migration, reset, automatic cleanup or reconciliation bypass in v1.

Profile exact object:

```text
{schema: V, contract: C, reviewed: true,
 interpreter: FilePin, endpoint: FilePin, sources: FilePin[],
 ledger_root: absolute-directory-path, legacy_locations: absolute-path[]}
FilePin = {path: absolute-file-path, sha256: H}
```

`sources` has 1..256 entries. Interpreter, endpoint and source paths must be distinct. These are
**the owner's reviewed closed recovery-control source manifest**, not caller-selected hashes.
Include helper/bootstrap recovery code. Installed OS/ELF/Pi/Jiti is an owner-trusted application
platform, not an exhaustive static capsule. Critical executable/entrypoint/provider/presence/config
pins and fresh native corroboration remain mandatory owner obligations. The coordinator hashes
declared files, not every dependency systemwide; no sandbox or total loaded-byte proof is claimed.
Dynamic discovery of unreviewed recovery-control code remains forbidden. V1 objects stay unchanged;
v2 explicitly declares this platform in its profile as specified below.

File pins reject symlinks, hardlinks, nonregular files, group/world writability, unexpected owners,
files larger than 512 MiB and observed inode/device/mtime/size changes during hashing. Files must
belong to root or the current user. Interpreter must be executable. Paths are absolute and lexical,
without `..` or symlink ancestors. Writable ancestors are refused except sticky shared ancestors.
Profile/config/reference JSON files are current-user-owned, private (no group/world bits),
non-hardlinked regular files, at most 1 MiB. Ledger is an **already owner-provisioned**, current-user,
0700 directory with safe ancestors. Legacy paths are sorted, unique, at most 256 entries.
No CLI option selects the canonical ledger or legacy set. The endpoint must account for the entire
bounded set including malformed/unknown/incomplete earlier attempts; an empty set is an explicit
owner assertion that no legacy locations exist, not automatic discovery.

`plan --adapter-config FILE` exact object:

```text
{schema: V, profile_digest: H, interpreter: FilePin, endpoint: FilePin}
```

The entire object must equal the corresponding fixed owner-profile projection. The immutable plan
retains the profile digest, not a mutable config path. Later phases reload the fixed owner profile
and require that digest. Config/profile copies, a new state root, nonce or invocation supply no new
authority. Each phase independently revalidates profile/interpreter/endpoint/all declared sources
**before invocation**. Hashing is not claimed to eliminate hostile same-user replacement races.

Canonical-only inspection separates safe identity from executable admission: `identify_profile()`
reads only the fixed, private owner trust anchor, validates its entire schema and pin specifications,
and validates its fixed ledger directory/ancestry. It does not require endpoint/interpreter/source
files still to match or exist. This lets intact canonical evidence remain visible after executable
drift, with `adapter_accounting=unknown` and no new proof/authority. Any attempted adapter inspection
still passes `Adapter.call()`'s full `load_profile()` pin validation **before subprocess creation**.
Approve, reconstruct and fresh verify retain full pin admission. No caller-selected config/root,
insecure or malformed trust anchor, or missing-anchor fallback is accepted by this diagnostic path.

Exact subprocess invocation, no shell:

```text
[profile.interpreter.path, "-I", "-S", profile.endpoint.path]
```

There are no endpoint CLI arguments or arbitrary argv fields. The environment contains only
`NDC_RECOVERY_FD=<decimal socket fd>`. Stdin, stdout and stderr are `/dev/null`; diagnostics are
not protocol messages and are never relayed. `-I -S` disables ambient Python path/site loading.
The endpoint must be self-contained or load only its reviewed explicitly pinned recovery-control sources;
it cannot assume the coordinator checkout or importable site-packages. No private machine imports
are made by the portable package. The endpoint starts in a separate session with `close_fds=True`.
Only its private AF_UNIX socketpair FD and, for execute only, the inherited lock FD are passed.
The endpoint must make both descriptors non-inheritable immediately. **No launched application or
bootstrap may inherit either descriptor**; launch with `close_fds=True` and no such `pass_fds`.

## 3. Request envelope and phases

One request starts each subprocess:

```text
{protocol: V, phase: "observe"|"admit"|"execute"|"verify"|"inspect",
 profile_digest: H, payload: object, expires_at: Time|null,
 lock_fd: nonnegative-integer|null, liveness_seconds: 5}
```

Only execute receives a lock descriptor, deadline and execution authorization. Other phases may
write private planning/verification evidence, but must never reach native/process/service/compositor
effect transports. Capture and offline preview never instantiate this adapter.

`Admitted` payload projection:

```text
{snapshot_digest: H, identity_digest: H, state_fingerprint: H, focus_digest: H,
 selection: Selection, omission_pins: H[], private_ref: H|null}
```

The existing model supplies identity/fingerprint/focus digests. The adapter must bind its own fresh
observation to the same compositor/topology/focus; copying request values without measuring is not
proof. `private_ref` is an immutable, content-addressed **adapter-private** manifest reference, never
a native payload or caller-selected path. It binds exact saved files/headers/cwd, complete trees,
protected/controller set, running/replacement/native builds, service contract, target layout,
launch/bootstrap contract, required native proof and all decisions. The endpoint owns its resolver,
private retention, size/permissions/link checks and fresh drift detection. It must never execute an
unbound selection or a free-form effect described by a caller.

| Phase | Exact payload | Exact final result body |
|---|---|---|
| observe | Admitted, with private_ref=null | Observation |
| admit | Admitted, with private_ref=H | Observation |
| execute | `{attempt_digest:H, plan_digest:H, approval:Approval, admitted:Admitted}` | Proof |
| verify | `{attempt_digest:H, plan_digest:H, admitted:Admitted}` | Proof |
| inspect | `{attempt_digest:H, plan_digest:H, admitted:Admitted}` | Inspection |

Admit must rebuild/revalidate the entire private manifest. Its sanitized Observation must exactly
equal the plan's Observation. It receives no execution approval. Plan creation, approval and execute
admission also perform a fresh ordinary read-only CLI capture, comparing identity, topology and
focus against the source snapshot. Changed historical snapshots cannot be executed.

`Approval` (also the deterministic CLI approval artifact):

```text
{schema: V, plan_digest: H, expires_at: Time, scope: C,
 profile_digest: H, accepted_omissions: H[]}
```

`attempt_digest = digest(Approval)`. Approval plan/profile/deadline and omissions must match the
request exactly. There is no new attempt nonce. Native selection comes only from the pinned
admitted private manifest. The CLI plan itself uses the existing plan schema and adds `recovery`:

```text
{schema: V, contract: C, profile_digest: H, observation: Observation,
 coverage: Coverage, omissions: Omission[]}
Omission = {process_pin_digest: H, pin: Pin,
            reason: "owned-process-native-association-unresolved"}
Coverage = {owned_native_processes: Count, associated_processes: Count,
 omitted_associations: Count, unique_saved_conversations: Count, unresolved_associations: Count}
```

Omissions are ordered by pin digest. Coverage is recomputed from individual records, never accepted
as adapter-supplied counts. `unresolved_associations` includes explicitly omitted associations.
`plan --omit-association H` makes a **new proposal** from fresh evidence. Approval requires the exact
whole plan, `--accept-losses saved-conversations-v1`, and `--accept-omission H` once per omission.
Duplicates, extra omissions, changed boot/birth/image pins and missing acceptance refuse.
No omission can waive ownership, native process identity, or controller/protected overlap.
The baseline loss contract covers prior memory, drafts, scrollback, shell memory and hidden-tab order;
it does not accept a missing session association. No actual operator omission is implied by tests.

## 4. Observation, inspection and proof

```text
Observation = {
 identity_digest:H, state_fingerprint:H, focus_digest:H, private_ref:H, supported:boolean,
 processes: Process[], session_refs:H[], legacy:Legacy
}
Process = {pin:Pin, owned:boolean, identity_proved:boolean,
           protected_overlap:boolean, session_ref:H|null}
Legacy = {locations_digest:H, complete:boolean, unresolved:Count}
Inspection = {legacy:Legacy, interrupted:boolean, unresolved_children:Count}
```

Process records are sorted uniquely by digest(pin), with unique PIDs. `session_refs` equals the
unique non-null process session references, not one launch per process. Empty native process/session
selection blocks. Every selected process must have owned=true, identity_proved=true and
protected_overlap=false. `supported=false`, unknown association without exact omission, incomplete
legacy coverage or unresolved prior attempts blocks approval. Legacy locations digest is precisely
`digest(profile.legacy_locations)`. Both unknown ownership and missing native process identity remain
unwaivable even when all other sessions are recoverable.

```text
Proof = {dimensions:Dimensions, native:Native[], interrupted:boolean, unresolved_children:Count}
Dimensions = {
 causal_ownership:Evidence, new_images:Evidence, old_tree_exit:Evidence,
 service_contract:Evidence, layout:Evidence, focus:Evidence, recovery_labels:Evidence,
 temporary_holds:Evidence, protected_preservation:Evidence
}
Evidence = {status:"proved"|"failed"|"unknown", evidence_ref:H|null}
Native = {session_ref:H, evidence_ref:H, file:boolean, cwd:boolean, runtime:boolean,
          bootstrap:boolean, surface:boolean, causal_window:boolean}
```

A proved dimension requires a non-null private evidence reference. Native records are sorted and
unique by session_ref; no unknown extra session is allowed. Missing records yield partial, never
complete. Every native predicate must be measured independently: exact file/header/session ID,
**actual process cwd**, supported runtime/image, exact bootstrap, distinct surface, and causal
launch-to-window ownership. A sidecar alone, title, ACK, matching count or one scalar `ok` cannot
satisfy the schema/contract. The endpoint must resolve evidence refs to retained native proof.

`verified` requires all nine dimensions proved, every admitted unique saved conversation present
with all six native predicates true, no interrupted history, no unresolved child, and no accepted
omission. Accepted association omissions cap the status at `verified-with-accepted-omissions` and
`overall_native_coverage_complete=false`. Any failed/missing mandatory proof yields partial;
transport/worker failure or interrupted effect history yields indeterminate. Provider usability,
semantic completeness, human acceptance and memory restoration are never inferred.

Execute requires at least one observed effect exchange as well as the final Proof. Final receipts
include structured Proof, individual effect observations, coverage, accepted typed omissions and
explicit unsupported/unverified dimensions. Transport failure or rejected final proof uses the same
receipt constructor with `proof=null`, `status=indeterminate` and retained coverage/typed omissions,
`process_memory=unsupported`, `provider_usability=unverified` and `human_acceptance=unverified`.
Loss of proof does not erase the operator's accepted decision context or imply full coverage.
A successful final frame alone is insufficient.
Fresh verify records new read-only proof, retaining `historical_status`. It **never changes the
canonical terminal marker or upgrades partial/interrupted/missing execution history**. Inspect is
history/accounting projection, not a fresh native verification or authorization to retry.

## 5. Effect conversation and cancellation

Every endpoint frame has exactly:

```text
{protocol:V, request_digest:digest(request), phase:request.phase,
 type:"heartbeat"|"effect"|"effect-result"|"result", body:object}
```

Read-only phases may send heartbeat frames, then exactly one result. Execute follows the finite
sequence below. No asynchronous multiplexing, unsolicited messages or pipelined effects exist.
Only one effect can be pending. Sequence indices start at zero and are contiguous, maximum 256.
A heartbeat while an effect is pending is a protocol violation: no `continue` is sent, IPC authority
is revoked, and the unresolved intent remains indeterminate. The matching effect-result must precede
any next heartbeat, whether or not the physical dispatch has already occurred.

1. Optional heartbeat, body `{}`. Wait for coordinator `continue`, body `{}`.
2. Before an effect, independently check running image/source pins, fresh admitted ownership/state,
   canonical ready/consume pair, absolute deadline and peer liveness. Durably fsync the **private**
   effect intent before asking for permission.
3. Send `effect`, body `{sequence:integer, kind:"shutdown"|"service"|"launch"|"layout", intent_ref:H}`.
   `intent_ref` addresses the exact private intent bound to the immutable admitted attempt.
4. Coordinator fsyncs its canonical intent, rechecks expiry and sends `permit`, body equal to the
   effect body plus `{expires_at:Time}`. This permits **one** bound physical dispatch, not a phase,
   subprocess tree, batch of signals or automatic fallback. Check pins, fresh state, peer EOF,
   deadline and monotonic lease again immediately before that dispatch. Permit must be fresh within
   five seconds of the most recent response; do not buffer authorization across stalled work.
5. Durably record observed result or unresolved causal child **before** sending `effect-result`:
   `{sequence:integer, intent_ref:H, outcome:"observed"|"indeterminate", evidence_ref:H}`.
   Coordinator fsyncs this observation. Only `observed` receives `continue`, body `{}`. An ACK is
   not native proof; missing ACK or indeterminate stops without another effect.
6. Only after receiving continue can another heartbeat/effect be issued. Finish with one `result`,
   body Proof; close protocol output/socket and exit zero. Nonzero exit, extra bytes, missing EOF,
   wrong phase/schema/identity or invalid final proof means indeterminate after consumption.

Coordinator messages use the same envelope and request identity, with types `continue` or `permit`.
A five-second socket liveness lease bounds blocked reads/writes. **EOF, broken socket, missing reply,
lease expiry or cancellation revokes new effect authority.** There is no separate retry/cancel CLI.
The worker may only observe an already dispatched effect and persist its uncertainty after revoke.
It must not signal, thaw, kill, launch, stop/start a service, move windows or otherwise repair state.
An in-flight operation may remain unresolved. Recheck after any blocking native operation before
another physical dispatch. Read-only or pre-effect observations may use cooperative heartbeats;
heartbeats cannot renew a pending effect. If its observation cannot finish within the lease, it
remains unresolved and no new physical dispatch is permitted. The owner must instrument each physical-effect boundary, not just outer
candidate functions. This is an audited implementation obligation, not proof supplied by a JSON ACK.

The coordinator closes IPC on cancellation/failure and waits for worker exit while retaining its
lock. It never calls timeout-kill, terminate, automatic rollback or cleanup. A defective worker that
never exits can therefore block the command; this is deliberate fail-closed behavior, not an
availability guarantee. Coordinator death leaves exclusion held by the worker's inherited flock
open-file-description. The worker releases it only when it ceases issuing effects/exits. Applications
must not retain it. The same compositor lock path is never unlinked, regardless of CLI state root.

## 6. Durable canonical fencing

Canonical ledger is an existing `Store` under the fixed owner-profile ledger_root. Store setup
establishes every directory edge root-to-leaf: create a missing directory as 0700, validate its
ownership/type/privacy, fsync the directory, then fsync its parent **before creating descendants or
writing effect-authorizing records**. This includes a new Store root and all newly created ancestors,
not only the immediate marker directory. Existing edges are also synchronized to close an earlier
interrupted-mkdir gap. Symlink/unsafe-owner/unsafe-permission conditions and fsync errors refuse;
there is no chmod repair or fallback. Canonical diagnostic reads use `Store(create=False)` and never
recreate missing accounting directories. The public CLI routes reconstruction `inspect` before any
writable `Store` construction; its `--state-root` is not a diagnostic source and is not created or
populated, including when that argument equals the canonical ledger. Only the safe fixed owner
profile selects the canonical diagnostic source.

Durability assumes Linux filesystem/storage semantics that honor file and directory fsync and ordered
successful calls, plus exclusive creation on a stable trusted pathname hierarchy. It does not claim
to survive hardware lying about flushes, arbitrary filesystem corruption, hostile same-user races or
external deletion. The tests establish syscall ordering/failure refusal, **not actual power-loss
survival**. The machine endpoint must apply equivalent parent-directory durability to its own private
worker claims, intent/results, bootstrap/child evidence and any new ancestor directories.

Before effect dispatch, under the existing per-compositor writer lock, the coordinator:

1. Re-admits exactly and refuses any unresolved canonical/legacy attempt. Canonical policy is
   conservative: **any** partial/indeterminate entry in this profile blocks new reconstruction.
2. Stores immutable plan and Approval copies in canonical plans/approvals for cross-root inspection.
3. Publishes `recovery-prepared/ATTEMPT.json` using exclusive creation plus file/directory fsync.
4. Consumes the CLI Approval with an exclusive, durable `used/ATTEMPT.json` marker.
5. Publishes `recovery-ready/ATTEMPT.json` exclusively/durably.
6. Revalidates all adapter pins and invokes execute. Each intent/result is separately content-addressed
   in canonical receipts. A durable `recovery-events` marker indexes each receipt by
   `digest({attempt_digest:ATTEMPT, sequence:integer, event:"intent"|"result"})`, with the exact value
   `{receipt_digest:H}`. Inspection reads at most 256 intent/result pairs and exposes only their
   validated evidence references/outcomes, including intent-without-result uncertainty.
   Finishing saves canonical/CLI receipts, then the exclusive terminal marker.

`Binding = {schema:V, approval_digest:H, plan_digest:H, profile_digest:H}`.
Prepared marker has exactly `{schema:V, profile_digest:H, approval_digest:H, plan_digest:H,
cli_used_path:absolute-path, binding:Binding}`. Ready and CLI used markers both equal Binding.
Terminal marker has exactly `{binding:Binding, receipt_digest:H, status:string}`; status is one of
verified, verified-with-accepted-omissions, partial, indeterminate. Canonical receipt must agree.
Prepared-only or consumed-without-ready fences remain indeterminate even if no effect was observed.
Unknown/malformed files or inconsistent pairs fail closed for admission and fresh verification.
Completed accounting also requires indexed results to agree with the terminal receipt's event list;
verified history cannot omit an indexed unresolved intent. Marker files are keyed by ATTEMPT rather
than their own content digest; ordinary receipts are content-addressed.

Inspection uses a **separate non-authorizing diagnostic projection**, not exception recovery around
admission. Each bounded attempt is classified independently with `accounting=valid|missing|
invalid-or-unreadable`; damaged/missing accounting is indeterminate. It scans at most 1,001 entries
per prepared/ready/terminal directory, reports count/unknown-entry/unreadable conditions explicitly,
and projects at most 1,000 attempt identities, always including the requested target. A malformed
other attempt cannot suppress independently valid target evidence. Strict admission/verification
still refuses the damaged ledger. No marker is repaired, removed or rewritten.

For each target sequence 0..255, intent and result indexes/receipts are independently integrity- and
schema-checked. `interruption_evidence` retains valid records even if the paired record is damaged;
its per-kind `accounting` distinguishes valid, missing and invalid-or-unreadable. A pair reports an
observed outcome only if both records validate and their intent refs agree. Missing/unreadable/
mismatched pairs are unresolved. `event_scan.missing_indices` records absent indexes/references;
`absence_is_no_effects_proof=false` explicitly forbids interpreting absent evidence as no effects.
If target plan metadata or the adapter's inspection fails, canonical/event diagnostics are still
returned with those surfaces unknown; without a valid plan identity no adapter is invoked. Every
diagnostic projection has `retry_authorized=false`. This does not restore lost evidence, certify a
consistent live desktop observation, or relax fresh-verification admission.

**The endpoint must independently read the fixed canonical ledger, validate prepared/ready and the
bound private CLI consumed record before any effect.** It must refuse a terminal attempt and
exclusively fsync a permanent private worker-started claim before starting execution; another worker
or a directly replayed internal frame cannot reuse the ready pair. It must also maintain complete
private legacy accounting and per-effect journals. An execute frame without this durable pair and
exclusive worker claim is no authority. The fabricated backend demonstrates this with
`endpoint-started/ATTEMPT.json` containing Binding; the machine owner must include such claims in
its complete private attempt accounting, never erase them on failure. Cross-root copies cannot bypass prepared creation;
re-approval produces the same Approval digest. Canonical records are never deleted or reset by this
CLI. A crash after readiness or intent may have no terminal record; inspect retains indeterminate.
A profile upgrade/accounting reconciliation requires separately reviewed owner work, not a new nonce.

## 7. Integration fixture and current proof limits

`tests/test_recovery_backend.py` is a self-contained fabricated endpoint plus `provision()` and
`installation_hook()` test helpers. It has **no native effect transport**. Its only effects append
fabricated names to a scratch log; its fake launch is a Python FD-leak oracle. It independently
checks wire identities, declared pins/running Python image, durable ready/consume pair, expiry,
peer disconnect and per-effect permit ordering. It is not a production native adapter or a source
of live approvals. The machine integrator can reuse this fixture and its handwritten proof oracle
while replacing only machine-native boundaries with equally isolated fakes.

`provision(root, interpreter=None, *, mode="normal", missing=False, unsafe=False, utility=None,
utility_only=False, saved_refs=("c" * 64,))` preserves the original one-conversation default.
Each `saved_refs` entry creates one fabricated native process: PID/start ticks 102/43, then 105/46,
106/47, etc.; 101/103/104 remain host/omission/utility reservations. Processes sort by pin digest;
observation refs and handwritten native proofs sort/deduplicate by ref. Repeated input refs therefore
mean multiple processes for one conversation, not multiple launches. `utility_only=True` with a
utility still removes all native records. All settings/profiles/state/locks are disposable scratch.

`tests/test_recovery_multitool.py` covers three distinct refs, consistent opaque renaming, same-ref
multiprocess deduplication, all six native predicates independently false for each of three refs,
missing/extra/duplicate native proof, mixed observed/capability utilities, independent exact omission
and utility-limit acceptance, retained decisions, replay refusal and non-upgrading fresh verification.
Missing native proof is valid but incomplete (`partial`); missing v2 utility proof is a schema refusal
(`indeterminate` on execution). V2 `saved_conversations_recovered=0` on partial/indeterminate attempts
is the existing aggregate complete-proof/history contract, not a count of individually passing refs.

References are opaque identities for separately scoped native conversations. The public coordinator
cannot identify Pi/Claude/Codex, prove tool-kind namespacing or certify semantic identity. Machine-owner
tests must prove that identical native IDs in different apps produce distinct refs and resume targets,
while repeated processes for the same app-native identity deduplicate. Do not substitute this fake
producer for that proof. All six native predicates still require independent machine corroboration.
The [coverage table](../usage.md#conversationtool-coverage-and-evidence-limits) separates public tests
from machine evidence. Pi/Claude/Codex/btop support is **implemented and independently reviewed with isolated integration tests;
native desktop qualification unperformed**. Machine tests verified app-kind-scoped equal-ID
separation, same-kind deduplication and actual native-shape callback/log fixtures. The private
`machine.v3` implementation uses unchanged public v1/v2; no public v3 or additional CLI is introduced.
The shipped [validation summary](../usage.md#recorded-validation-and-qualification-limits) records
review counts, genuine but limited sandbox prototype evidence, the unclean Claude harness exit and
held sandbox, and the absence of permanent real Claude/Codex native opt-in tests. Unknown or unproved
helpers still block. This is not clean Claude compatibility or full native/runtime certification.

`tests/test_recovery_orchestration.py` covers protocol rejection, noisy diagnostics, pin drift, stale/
expired/replayed plans, native dimension failures, exact omissions, legacy incompleteness, fencing
crashes, cross-root replay and parent disconnect. A subprocess crash test uses `os._exit`, not
signals, and proves that the still-running worker alone holds exclusion. Fake launch verifies that
applications do not inherit the lock. No test touches the account's real profile or live runtime root.

`tests/test_recovery_hardening.py` adds a handwritten directory/file synchronization-order oracle,
fsync failure before execute, strict encoding/finite-number/exact-frame-boundary counterexamples and
torn/unknown/unreadable accounting diagnostics with intact evidence and fresh-verification refusal.
`tests/test_recovery_execute_faults.py` drives actual execute subprocess streams with wrong request/
phase, duplicate keys, invalid encoding/numbers, orphan/out-of-order/duplicate exchanges, invalid or
trailing final proof, nonzero exit after proof and maximum/oversized final frames. Handwritten scratch
effect logs check no subsequent dispatch after revocation and preserve exact accepted omission context
on failures before permits, after dispatch and at final validation. Real elapsed five-second tests
cover stalled replies and permit lease expiry. A test-only patient coordinator keeps its socket open
longer than the advertised lease to distinguish **worker-side expiry obligation** from coordinator EOF.
The before/during/between-disconnect tests are complementary: cancellation is not an OS sandbox, and
these fakes do not prove a separately implemented native worker complies.

`tests/test_recovery_residuals.py` covers comment/deletion/source pin drift with intact shutdown
intents, strict executable admission before invocation, unsafe/malformed trust-anchor refusal, and
CLI inspection with canonical/equal, existing separate and absent separate state roots. Missing
canonical marker directories remain missing; malformed evidence remains reported. The execute
fault matrix also sends heartbeats after permits, both before and after scratch dispatch: each is
refused with retained typed decisions, an unresolved intent and no subsequent physical effect.

`scripts/ci/package-smoke.py` installs the built wheel in a disposable venv outside the checkout,
then drives the **actual existing console script** through capture, plan, preview, approve,
reconstruct, verify, inspect and history, including three opaque references alone and with observed
btop or capability-btop plus a separately accepted fabricated omission. Original single-reference
and utility-only cases remain covered.
A disposable venv-local `sitecustomize.py` replaces only profile-path, capture and lock-root functions.
This test seam is **not** shipped as a production environment switch or CLI option. The internal
endpoint remains a real subprocess using private socket IPC and the complete protocol. Restart and
migration stay blocked. Installation introduces no runtime dependencies or second public CLI.

The unchanged map renderer shows the original target topology and sanitized coverage/loss/omission
warnings in its existing admission area. **It does not draw predicted causal replacement window IDs,
native surfaces or recovery groups.** The warning explicitly identifies this limit; native proof is
available in typed receipts/verify, not implied by the preview. No map/visual redesign was performed.

Machine implementation and independent source review now have separate owner evidence, including
installed-CLI tests with isolated native boundaries. Actual deployment/profile qualification and
separately approved live operator/native proof remain unperformed. Portable tests do not supply them.

## 8. Exact additive protocol v2 (v1 remains frozen)

V2 = `desktop-continuity.recovery.v2`; C remains `saved-conversations-v1`. Every profile, config,
request/frame, plan recovery object, Approval, Binding and receipt uses its exact version. No
optional-field upgrade or cross-version execution. Historical canonical diagnostics may read v1
evidence after an owner profile upgrade, without invoking the old adapter or granting admission;
foreign-profile accounting still blocks effects pending separately reviewed owner reconciliation.
Canonical diagnostic entries retain their original schema/profile_digest when those identities
are readable; malformed identities remain unknown. Completed accounting checks canonical plan,
approval and the recomputed receipt projection against the original version, not only frame schemas.

All unchanged objects, bounds, locks, expiry, 256-effect cap, fences, no pending heartbeat,
revocation/no-kill/no-retry and diagnostics rules above apply unchanged. V2 changes are exact:

* Profile adds `platform:{kind:"owner-trusted-application-platform",pins:FilePin[]}`. Pins has
  1..256 distinct paths, disjoint from interpreter/endpoint/sources; every pin is freshly checked.
  Owner review selects critical executables, entrypoints, provider/presence code and config; this
  is an explicit trust declaration, not a claim of complete native dependency closure.
* Observation adds `utilities:Utility[]`, sorted uniquely by utility_ref.
* Proof adds `utilities:UtilityProof[]`, sorted uniquely by utility_ref, exactly matching admission.
* Coverage adds `owned_utilities:Count,image_unobservable_utilities:Count`.
* Approval adds `accepted_utility_limits:H[]`, exactly the capability-btop utility refs.
  Admitted and all phase payload shapes are unchanged; private_ref binds utilities and their limits.
  Execute validates those accepted limits against the immutable canonical plan before dispatch.
* CLI approval requires `--accept-utility-limit H` once per capability-btop utility, in addition to
  exact plan/loss/omission acceptance. No plan omission flag selects or excuses utilities.

```text
Utility = {utility_ref:H,kind:"btop",host_pin:Pin,identity:UtilityIdentity,
 owned:boolean,identity_proved:boolean,protected_overlap:boolean,evidence_ref:H}
UtilityIdentity = {kind:"observed-image"|"capability-btop",boot_id:string,pid:integer,
 start_ticks:integer,uid:integer,parent_pid:integer,cgroup_digest:H,argv_digest:H,
 image_pin:Pin|null,installed_file_ref:H,capabilities_digest:H|null,
 running_image:"observed"|"unobservable"}
UtilityProof = {utility_ref:H,evidence_ref:H,identity:boolean,installed_file:boolean,
 capabilities:boolean,sole_owned_leaf:boolean,causal_window:boolean,
 running_image:"proved"|"accepted-unobservable"|"failed"|"unknown"}
```

Utility identity integer/boot bounds follow Pin (parent_pid positive). Host boot/UID must match
identity and source boot/current UID; identity.parent_pid equals host_pin.pid. Host PID must
belong to the selected window-host PIDs. Utility PID is
unique across native processes/utilities, differs from every host PID; repeated host pins must
agree and any native-process pin for that host must agree. `utility_ref=digest({kind,host_pin,identity})`.
Observed-image requires running_image=observed, image_pin a real observed Pin agreeing on all
birth/UID fields, capabilities_digest=null. Capability-btop requires running_image=unobservable,
image_pin=null, capabilities_digest=H. Never invent a running image from the installed file.
The private adapter resolves retained evidence and independently corroborates exact installed file,
capabilities, argv/cgroup, birth/parent, sole-owned-leaf and causal-window predicates.

All UtilityProof booleans must be true (including capabilities, which proves absence or exact
presence as appropriate); running_image must be proved for observed-image and
accepted-unobservable for capability-btop. Failed/unknown yield partial; branch confusion refuses.
Utility refs must exactly match admission; no fabricated native/session ref. Missing mandatory
proof never yields success. Zero-session utility-only selections are valid, reporting zero recovered
conversations. Other native association/omission rules are unchanged.

V2 receipts add `accepted_utility_limits:H[]`, `overall_image_coverage_complete:boolean`,
`image_coverage:"complete"|"observable-subset-only"`, and `saved_conversations_recovered:Count`.
Accepted limits cap status at `verified-with-accepted-limitations` (also with omissions); otherwise
existing statuses apply. `overall_native_coverage_complete` is false with either limits or omissions.
`new_images` and native runtime image evidence refer only to the observable subset; every utility
predicate remains mandatory. Fresh verification cannot upgrade interrupted history or mutate its
terminal marker. Tests establish synthetic orchestration only, not native btop/Ghostty recovery.

V2 synthetic regressions live in `tests/test_recovery_utilities.py`: handwritten observed/capability
identity and proof oracles, utility-only zero-session success, independent omissions/limits, all
utility predicates, damaged accounting, interrupted fresh verification, platform drift and
profile/config/plan/approval/frame/event/receipt version confusion. Installed smoke includes actual
v1 and v2 socket subprocesses, utility-only and combined omission/limit cases and damaged-accounting
refusals. These establish public orchestration behavior only. Machine-owned retained corroboration
has separate implementation/review and limited sandbox prototype evidence; native desktop
qualification remains unperformed and live desktop effects unauthorized.

Independent-review regressions additionally reject utility PIDs colliding with any selected host,
and prevent historical success from hiding adverse current adapter accounting. Inspection retains
`historical_status` separately: interrupted/unresolved/incomplete current accounting returns
`status=indeterminate` without changing canonical history or granting retry authority.

## 9. Additive saved-reopen v1 (replacement v1/v2 remain frozen)

`A = desktop-continuity.saved-reopen.v1`; `C = saved-conversations-v1` remains the loss scope.
The same capture/plan/preview/approve/reconstruct/verify/inspect CLI lifecycle, framing/size bounds,
fixed trust anchor, pin checks, private Store, canonical ledger and cancellation rules apply.
Select it explicitly with `plan --intent reconstruct --mode additive --saved-set H`; mode defaults
to replacement. It requires an A profile. Replacement selectors, omission/utility-limit decisions,
arbitrary commands and public native paths are forbidden. No old selected PID/window is required.

The A profile has the exact **v2 profile fields**, including the explicit owner-trusted platform
and pins, with schema A. Config/frames/bindings/receipts route by exact A, never an optional v1/v2
field. Profile provisioning and reviewed native implementation remain owner responsibilities.
An owner-private immutable saved-set resolver is bound by `saved_set:H`. The public tool does not
import recipes or discover native stores. All current desktop windows/processes are protected.

```text
SavedSelection = {missing_refs:H[], present_refs:H[], unresolved_refs:H[]}
Admitted = {snapshot_digest:H, identity_digest:H, state_fingerprint:H, focus_digest:H,
 selection:EmptySelection, omission_pins:[], private_ref:H|null,
 mode:"additive", saved_set:H, saved_selection:SavedSelection|null}
EmptySelection = {window_ids:[], pids:[], requested_window_ids:[], requested_pids:[],
 app_id:null, version:null}
Observation = {identity_digest:H, state_fingerprint:H, focus_digest:H, private_ref:H,
 supported:boolean, processes:[], session_refs:H[], legacy:Legacy,
 saved_set:H, saved_selection:SavedSelection, selection_proved:boolean}
Coverage = {selected_saved_conversations:Count, missing_saved_conversations:Count,
 already_present_saved_conversations:Count, unresolved_saved_conversations:Count}
```

The three sorted unique arrays are pairwise disjoint and their sorted union exactly equals
`session_refs`; at most 256 refs total and **255 missing refs**, reserving one focus event.
`private_ref` and `saved_selection` are null only in initial observe. Every subsequent phase binds
the exact private manifest and classified set. Admit returns byte-equivalent semantic Observation;
it cannot move refs from missing to present under the old approval. Saved-set drift or classification
changes require fresh plan/approval, never replay of an unresolved attempt.

The adapter must independently prove exact native saved file/header/ID/cwd, allowed runtime and
bootstrap, current absence or already-present association, live descendant deduplication, and
protected overlap/ownership. `selection_proved` summarizes retained private evidence, not an
allowlist or permission to echo request values. A missing terminal sidecar does not establish
absence; independently identified headless/native processes must participate in duplicate checks.
No cwd/title/recency heuristic can substitute for native identity. `supported=false`, unproved
selection, empty selected refs, any unresolved ref, incomplete legacy or canonical history blocks.
A separately chosen subset has a different saved-set digest; omissions are never implicit.

Recovery plan fields are exactly the v1 fields plus `mode:"additive",saved_set:H` (omissions=[]).
Approval fields are exactly the v1 fields plus `mode:"additive",saved_set:H`
(accepted_omissions=[]). Whole-plan/approval hashes bind the classified set. Baseline loss
acknowledgment is still required. Live selected window/PID arrays and affected scope are empty,
but the complete current snapshot/focus remains the protected admission basis.

Only the following exact effect intent is accepted:

```text
{sequence:integer,kind:"launch"|"focus",intent_ref:H,target_ref:H}
```

A launch's target_ref must equal one admitted **missing** session_ref and may be permitted once.
Already-present, unresolved, extra or repeated refs refuse. A focus effect's target_ref must equal
the admitted focus_digest; exactly one is permitted **after every missing launch has an observed
result**, never before or between launches. No launch may follow focus. Shutdown, service and
layout intents refuse before permits, including attempts to target existing windows. The adapter
resolves the exact focus pin from its admitted private manifest; the opaque digest is not free-form
window targeting. Intent/result journaling, absolute expiry and no-pending-heartbeat rules remain.
Effect-result shape is unchanged. Missing-ref sets require all their launches and that one focus
exchange before final success. Already-present-only sets require **zero effects**, including zero
focus effects; they still prepare/consume/ready and cannot replay. Canonical validation independently
rechecks the event target set/order, so a missing launch cannot be hidden by a final scalar proof.

```text
Proof = {dimensions:Dimensions,native:Native[],interrupted:boolean,unresolved_children:Count}
Dimensions = {causal_ownership:Evidence,new_images:Evidence,focus:Evidence,
 protected_preservation:Evidence}
```

Evidence and Native retain their existing exact shapes. Native rows must cover **all** session_refs,
including present refs, with all six independently observed predicates true. For present refs,
causal_ownership/new_images mean corroborated current ownership and pinned observed native images;
they do not claim a new process was launched. For missing refs they also require causal binding to
the authorized launch. Old-tree exit, service contracts, layout, labels and temporary holds are not
fields, prerequisites or invented proved dimensions. Normal tiling insertion may alter geometry;
no exact tab ordering or placement is asserted by this initial mode.

A receipts retain base v1 fields and additionally `mode`, `saved_set`,
`saved_conversations_restored`, `saved_conversations_already_present`,
`saved_conversations_unresolved`, `layout`, and `destructive_effects`.
Restored is the missing-ref count only after complete proof and successful history; otherwise zero,
not a partial salvage tally. Already-present/unresolved are frozen admission counts, not fresh
claims after failed verification. Layout is
`not-reconstructed; ordinary-tiling-insertion-may-change-geometry`; destructive_effects is
`not-authorized`. Status is verified, partial or indeterminate; no omission/utility-limit upgrades.
No-op complete native proof can be verified without fabricating an event. Interrupted history
never upgrades on fresh verify. Native/provider/human/memory nonclaims remain unchanged.

`tests/test_saved_reopen_backend.py` is a handwritten fabricated endpoint with no native/compositor
transport. `tests/test_saved_reopen.py` checks missing/present selection, exact effect refs, refusal
of destructive/layout/duplicate effects, native predicates, changed pins/state/expiry, replay and
non-upgrading history. `tests/test_saved_reopen_installed.py` builds/installs a wheel outside the
checkout and drives the actual console script through both missing-ref and zero-effect workflows.
The disposable interpreter replaces only capture/profile/lock providers; no production bypass is
added. `tests/test_saved_reopen_preview.py` verifies the offline HTML saved-set/ref/disposition
ledger, missing-versus-no-op distinction and escaped values without private-manifest disclosure.
Additive scope is reviewable even though live-window selectors are empty and topology is unchanged.
These tests establish portable orchestration, not machine integration or native qualification.
