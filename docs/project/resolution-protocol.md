---
summary: "Portable resolution, exact retained-history decoding, observer wire, and parent-held serialization boundaries."
read_when:
  - "You implement a machine settlement observer or review portable resolution admission."
  - "You inspect or change abandonment/profile-transition code."
type: "reference"
---

# Abandonment and same-ledger profile transition

## Implementation and qualification boundary

The portable CLI implements candidate planning/admission, resolution planning/exact approval,
append-only apply/profile replacement, and offline inspection. Tests use fabricated profiles,
roots, process inventories and history. **No machine observer, native qualification, deployment,
source-policy bypass or live-effect authorization is supplied.**

**Exact retained-history decoding is implemented, not natively qualified.** A present
`catalog.json` exclusively selects `resolution_worker_history` and its closed schema module for
`workstation.saved-reopen.catalog.v1`. It decodes the actual retained State/Journal/bootstrap
record shapes, correlates canonical events and retained controls, and normalizes evidence only
in memory. Fabricated historical-byte specimens test the original zero-permit and first-launch
prefixes; no owner code is executed and no replacement history is written.

The separate `desktop-continuity.resolution-worker-data.v1` codec in
`resolution_worker_history_fixture` remains prospective/test-only, NOT a claim about bytes an
existing machine worker wrote. Unknown catalogs, schemas, namespace layouts and root files block;
a present unsupported catalog never falls back to the prospective codec. Do not manufacture
records beside an old attempt, rewrite history, or add another authoritative worker cache.

Later **completed** owner history is decoded by `resolution_worker_history_completed` with
closed native shapes in `resolution_worker_history_native`: rooted manifests/present bindings,
launch children and retained bootstrap tickets, grouped dispatch/bindings, launch and focus
measurements, intent/result/ACK sequences, finished records, proof dimensions and native
verification records correlated with canonical receipts. Known but unrooted verification objects
still fail closed; recognizing a shape does not supply its authority edge. Fabricated completed
history regressions cover these relationships, not arbitrary owner history or native execution.
No passing portable test establishes eligibility of an existing machine attempt or native
qualification; exact installed historical/configuration binding still needs owner review.

Likewise `workstation.saved-reopen.machine.v3` is the explicitly supported **configuration-binding
spelling**, not a verified identification of any installed configuration. Owner integration must
confirm the actual spelling and its semantics, or review an exact additional binding. There is
no arbitrary JSON-pointer mapping or configurable trust-root fallback. Unsupported bindings block.

The finite settlement decisions are:

- Direct first launch: a complete sequence-zero launch/result/ACK/child/request/started graph,
  changed host boot, expired retained ticket, and freshly admitted conflict-free observation.
- Same-boot zero permits: no issued intents, launch children, requests, started claims or finished
  marker, plus the reviewed wait/source contract and complete current candidate discovery.
- Same-boot historical direct launch: **always blocked**, even when both recorded PIDs are absent.
  No historical descendant/session closure is inferred. Reboot, cleanup, signals and retry are
  never proposed or performed by this feature.

Resolution means **abandoned-settled**, not recovered, successful, no-effects, or retriable.
Original receipts, CLI used markers, canonical events and worker completion history are unchanged.
Only the exact old-profile → new-profile edge for the original attempt is exempted from the
normal unresolved-history admission gate. New reconstruction still needs its entire normal lifecycle.

## Existing CLI routes

All commands use the existing `niri-desktop-continuity` entrypoint. Uppercase tokens below are
placeholders, not machine paths or identities.

```text
plan --intent profile --candidate-profile NEW_PROFILE --observer-config OBSERVER \
     --source-contract SOURCE --attempt ORIGINAL_ATTEMPT --ttl 600
preview CANDIDATE --kind profile
approve CANDIDATE --kind profile --confirm CANDIDATE \
        --accept-profile-admission resolution-observe-only
plan --intent abandon --candidate CANDIDATE --attempt ORIGINAL_ATTEMPT --ttl 300
preview PLAN --kind resolution
approve PLAN --kind resolution --confirm PLAN \
        --accept-abandonment abandon-without-retry-or-success
reconcile APPROVAL --kind resolution --apply
inspect APPROVAL --kind resolution
```

The old snapshot positional remains required for every old plan intent. Default layout and
replacement/additive reconstruction routes retain their existing selection and approval semantics.
Resolution routes reject layout/reconstruction selectors and loss/focus acknowledgments.

Only new `preview --kind profile`, `preview --kind resolution` and `inspect --kind resolution`
have the new zero-write/zero-lock/offline guarantee. They route before eager Store construction,
ignore caller state-root for authority, and output text/JSON without launching a browser or
creating a misleading topology map. Original reconstruction inspection still may lock and invoke
its pinned adapter. Preview output is private data, including retained source bytes: never publish it.

Outputs distinguish `native_effects: []` from explicit `accounting_mutations` and `profile_mutations`.
A profile admission grants only observation capability, never activation or application effects.

## Module APIs and owner hooks

Paths below resolve under `src/niri_desktop_continuity/`.

| Module/API | Contract |
| --- | --- |
| `resolution_candidate.plan(new_path, observer_path, source_path, attempt, ttl=300)` | Data-only candidate creation; initial graph/root/source validation. |
| `resolution_candidate.approve(key, confirmation, acceptance)` | Exact owner data admission; checks new live pins, no subprocess. |
| `resolution_candidate.admitted(key, live=True, active="old", fresh=True)` | Returns `(candidate, admission)` from fixed account anchors; C alone is insufficient. |
| `resolution_candidate.validate(candidate, live=False, active="old", fresh=True)` | Closed candidate and explicit configuration bindings; old executable drift is not loaded. |
| `resolution_observer.observe(candidate_key, graph_key)` | Pinned isolated read-only socket invocation; only heartbeat/result. |
| `resolution_evidence.persist_packet(packet, candidate, graph, objects)` | Validates a bounded closed packet, then persists canonical attachments/evidence. |
| `resolution_graph.initial(candidate)` | Exactly one old attempt and no resolution marker namespace prefix. |
| `resolution_graph.unchanged(candidate, graph, durable=False)` | Apply gate allows transaction prefixes but requires unchanged original graph and one attempt. |
| `resolution_graph.unchanged(..., durable=True)` | Same original graph; permits legitimate unrelated later attempts/manifests. |
| `recovery_transition.plan(candidate_key, attempt, ttl=300)` | Admitted observation → proposal, not approval. |
| `recovery_transition.approve(key, confirmation, acceptance)` | No observer invocation; exact abandonment approval. |
| `recovery_transition.apply(approval_key)` | Fresh observation under owner/ledger/compositor locks, durable accounting and profile CAS. |
| `recovery_resolution.durable_view(profile, live=False)` | Shared read-only final-chain validator; returns `None`, one explicit edge, or raises on damage/prefix. |
| `recovery_resolution.admission_gate(profile)` | Same view plus current new control/config pins, used by normal profile admission. |
| `recovery_resolution.legacy_disposition(profile, worker_root, attempt, historical_status)` | Machine hook below; explicit worker-root equality, not a success flag. |
| `resolution_lock.owner_guard()` | Coordinator holds fixed anchor mutex → canonical ledger inode/path mutex; take compositor locks afterward. A child must not reacquire these parent-held mutexes. |

### Machine State.legacy

The separately owned machine integration must:

1. Preserve its normal read-only legacy accounting and reject missing/unknown/damaged native state.
2. Call `legacy_disposition(active_profile, state_root, attempt, "indeterminate")` for an old
   indeterminate attempt. A returned overlay is exactly
   `{historical_status:"indeterminate", resolution_disposition:"abandoned-settled",
   accounted_settled:true, replay_authorized:false}`. `None` grants nothing.
3. Exclude only that exact validated attempt from its unresolved count. Never call `State.completed`,
   write `finished`, synthesize success, or tolerate foreign profiles globally.
4. Keep admission serialized by the **coordinator parent's** `owner_guard()` for the entire child
   invocation. The machine `resolution_admission.CooperatingAdmission` checks socket
   `SO_PEERCRED`, parent PID/birth identity and kernel FLOCK ownership by that parent for the
   exact owner/ledger locks. It does **not** reacquire those locks or call serialized
   `load_profile()` in the child. Merely observing that some process holds a lock is insufficient.
   A standalone provisioning/profile-changing owner takes the same mutexes itself.
   `durable_view` and `legacy_disposition` are pure reads, not standalone serialization guarantees.
   Calling `owner_guard()` or `load_profile()` in the isolated child while the parent holds the
   locks fails with `BlockingIOError`; blocking retries would deadlock this protocol. In-process
   ContextVar nesting is not cross-process authority and must not be inherited as a boolean waiver.
5. Use `State(read_only=True)` in the observer. Do not call an ordinary producer that writes objects
   while observing. Only the portable coordinator persists resolution evidence.

`Ledger.admission_disposition()` retains `status:"indeterminate"` and adds a separate `admissible`
field for the explicit edge. `available`, direct proposal, validate, prepare, execute, and adapter
admission use the shared gate. Fresh verification passes a transitively validated exact resolution
edge to strict ledger accounting solely to route the old profile. It uses the **target attempt's**
current-profile historical status plus fresh proof, never `admissible` as historical success.
The abandoned original remains indeterminate and cannot be verified using the new profile.
Old-pinned clients retain their old unresolved/foreign-profile fence.

### Owner observer entrypoint and closed module map

No observer entrypoint/loader ships here. The machine owner must implement it separately and pin it:

- Interpreter invocation: `INTERPRETER -I -S ENDPOINT`.
- Environment has only `NDC_RESOLUTION_FD`; exactly that socket FD is inherited. There are no
  compositor lock FDs, effect permits, phase=execute, site, pyc, network or caller-root fallback.
- Load candidate **and** exact admission from fixed account-home anchors before imports, verify
  complete source/critical interpreter pins and the closed `modules` map. Repeat before reply.
- The owner maps every imported owner/portable module to an exact retained source pin. This includes
  all transitive imports of the shared view, not just `recovery_resolution.py`. The present portable
  graph/view closure reaches recovery/profile/ledger/protocol/verification, additive/projection/
  utilities, model/planner, Store and lock modules. `coordinator_digest()` binds all package `.py`
  basenames to exact SHA256 bytes; it is not an installed native-platform qualification certificate.
- Platform is explicitly owner-trusted stdlib under the declared root, with a pinned interpreter;
  it is not a total OS/ELF dependency closure or sandbox. Closed loader enforcement remains an
  independently reviewed owner implementation obligation.
- Produce the packet below using read-only native queries and a source-admitted candidate detector.
  Wait on disconnect/expiry; never kill, cleanup or retry. The coordinator waits without kill too,
  so a defective observer can indefinitely block its caller after authority has closed.

## Closed data contracts

Canonical digests are `model.digest` of strict JSON; raw hashes are SHA256 of exact bytes.
JSON rejects duplicate keys, nonfinite numbers and unknown fields on the declared schemas.
Integers never accept booleans. Digests are lowercase 64-hex; boot IDs are canonical UUIDs.
UTC lifetimes are 30–600 seconds. Normal expiry applies at admission/apply, not forever to history.

The code's `fields(...)` definitions are executable schema authority. These are the full top-level
wire fields and nested record meanings; unknown fields do not provide an extension mechanism.

### Candidate and source contract

Candidate schema `desktop-continuity.profile-candidate.v1`:

```text
schema, created_at, expires_at, old_profile, new_profile, old_config, new_config,
ledger, worker, attempt_digest, saved_set, selected_refs, observer, source_contract
```

`selected_refs` is exactly the original two sorted refs, not an alternate selection.
Retained profile/config/source/review objects are `{path, sha256, raw_base64}`. Raw bytes must match
both their exact hash and their applicable decoded schema/semantic identity. Historic live source
files are never read to reconstruct missing retained bytes. Historical interpreter/platform pin
specifications are retained in the original profile; binary platform bytes are not archived.
Original endpoint/source bytes, profile/config and the source review are archived canonically.

Roots are `{path, device, inode}` with safe owned current directory identities. Both profiles have
the same ledger, legacy locations and worker root. The unique profile source basename
`saved-reopen.json` pins the retained machine configuration. Its `private_root` must be the exact
worker root, and the observer configuration must be the same new configuration pin. Other machine
configuration fields are opaque retained bytes, not a portable schema interpretation.

Observer fields: `{interpreter, endpoint, sources, modules, platform, config}`. Pins are
`{path,sha256}`. Pin paths are unique, every module/config is a source, and module names/paths
are bounded and unambiguous. Platform fields are
`{schema:"desktop-continuity.observer-platform.v1", python_sha256, stdlib_root,
policy:"isolated-source-only-v1"}`.

Source contract `desktop-continuity.resolution-source.v1` fields:
`schema, original_files, old_config, new_config, review_artifact, original_profile_digest,
coordinator_sha256, prefix_rule`. Original files are the exact sorted original endpoint/sources.
The retained review schema `desktop-continuity.resolution-source-review.v1` binds
`old_profile_digest, new_profile_digest, old_config_sha256, new_config_sha256,
original_sources_digest, coordinator_sha256, prefix_rule, claim`.
`claim` is the exact string
`wait-before-terminal;permit-before-dispatch;no-detached-transport;one-shot-bootstrap;no-autostart`.
These are **externally reviewed, exactly admitted claims**, not facts proved by portable strings or
booleans. Existing owner source admission/raw scanning is still required; no bypass/hook is added.

Candidate and admission anchors are siblings of the fixed account-home recovery profile:
`recovery-candidates/C.json` and `recovery-candidate-admissions/C.json`. Account home comes from
`pwd.getpwuid(getuid())`, not HOME/XDG/state-root. Candidate creation paths select data only.
Admission schema `desktop-continuity.profile-admission.v1` has
`schema,candidate_digest,confirmation,admitted_at,expires_at,capability` with exact C confirmation,
matching expiry and `capability:"resolution-observe-only"`.

### Transport

LF-framed strict JSON, at most 1 MiB per frame. Request:

```text
{protocol:"desktop-continuity.settlement-observer.v1", candidate_digest, graph_digest,
 phase:"observe-settlement", expires_at}
```

Every observer frame is exactly `{protocol, request_digest, type, body}`. `type` is only
`heartbeat` (empty body) or `result` (packet). Heartbeat receives the same envelope with
`type:"continue",body:{}`. Result must be followed by EOF and successful observer exit.
Complete-frame monotonic lease is five seconds; expiry is absolute. Effects/effect-results,
unbound frames, trailing bytes and late frames close authority. No permit can be emitted.

Result packet `desktop-continuity.settlement-packet.v1`:
`{schema,evidence,attachments:[{digest,value}]}`. Attachments are unique, sorted, bounded and must
be exactly the referenced set, with no unrelated payloads or caller-selected archive paths.

### Evidence and attachments

Evidence `desktop-continuity.settlement-evidence.v1` fields:

```text
schema, candidate_digest, graph_digest, observed_at, expires_at, observer_digest,
boot_before, boot_after, current_identity, focus_digest, protected_digest,
process_scan, writers, tickets, saved_files, source_contract_digest, mode, verdict, blockers
```

- `current_identity`: `{boot_id,niri_socket,socket_device,socket_inode}`.
- `process_scan`: `{rows_ref,names_before_ref,names_after_ref,attribution_ref,complete,escaped_cohort}`.
- `process-names.v1` attachment: `{schema,tasks:[numeric task IDs]}`, sorted unique, ≤100000.
  Its historical meaning remains **full visible same-account task-set stability**, including
  noncandidates. It is not reinterpreted as a candidate subset.
- `process-names.v2`: exactly `{schema,discovery_scope,stability_scope,tasks}` with
  `discovery_scope:"all-visible-same-account-tasks"` and
  `stability_scope:"candidate-and-protected-cohort"`. Tasks are sorted unique, ≤100000.
  Both passes must fully discover and classify visible same-account tasks, retaining every
  possible writer, recovery executor, unknown and required protected/control identity. Only
  proved noncandidates outside the protected cohort may be omitted. Retained noncandidate
  leaders have `protected` classification, not generic `noncandidate` rows.
  Before/after versions and scopes must agree, with equal task lists exactly matching process
  rows. Mixed versions, unknown/lying scope labels and full-set fields on v1 refuse. For v2,
  `complete:true` asserts that full reviewed discovery succeeded, **not** that every discovered
  task was retained or all noncandidate threads/FDs were quiescent. The native producer must
  explicitly emit v2 for its stable subset; changing a label cannot certify native coverage.
- `process-rows.v1`: `{schema,rows:[{boot_id,pid,tgid,start_ticks,ppid,pgid,sid,uid,
  image_digest,pid_namespace_inode}]}`. Sorted by task PID; ≤20000 leaders/100000 tasks.
- `candidate-discovery.v1`: `{schema,contract,rows:[{process_ref,classification,association_ref}]}`.
  Exact contract is `owner-reviewed-possible-writer-and-recovery-executor-v1`.
  Classifications: noncandidate, observer, controller, protected, possible-writer,
  recovery-executor, unknown. Exactly one discovery row per supplied process row; before/after
  sets must match within the explicitly versioned scope. Unknown and durable recovery executors
  block. V2 discovery attachments describe the retained cohort, not raw whole-discovery metadata.
- `writers` is a sorted array of attachment digests. `writer-association.v1` fields:
  `{schema,process_ref,session_ref,saved_device,saved_inode,disposition,birth_digest}`.
  Disposition is unrelated/selected/descendant/unknown. Only unrelated exact associations outside
  the original selection pass. Any `(saved_device,saved_inode)` overlap with either selected saved
  file independently blocks as `writer-conflict`, regardless of claimed ref/disposition (including
  hardlinks or a selected-file descriptor alongside unrelated argv). Every possible writer needs
  an association; controller or protected overlap never becomes a writer exemption.
- `saved_files`: exactly the two ordered original refs; each has
  `{session_ref,device,inode,bytes,sha256,original_prefix_bytes,original_prefix_sha256,
  metadata_ref,prefix_preserved}`. Device/inode/original prefix/metadata bind the historic manifest;
  append-only growth is observation data, not permanent whole-file graph identity.
- `tickets`: `{request_ref,request_sha256,claim_ref,claim_sha256,boot_id,pid,start_ticks,
  expires_at,disposition}`; exact graph raw hashes, request expiry and started birth must agree.

All attachment schema names above have the `desktop-continuity.` prefix. Process discovery is an
owner-reviewed **possible-writer/recovery-executor detector**, not universal app classification.
Unrelated ordinary apps need no invented per-PID source waiver. Conversely an erased-argv or
unobservable potential writer cannot be silently called noncandidate. Full native attribution,
boot/namespace stability, source admission and complete enumeration are owner producer obligations;
the portable packet validator cannot independently certify a defective native claim. The supported
cooperating-runtime boundary covers reviewed Pi/Node/Python-style runtimes and known interpreter/
embedding families, not arbitrary malicious native code implementing a saved-session format.
Runtime markers and mapping checks are recognition evidence, not proof against stripped/encrypted
interpreters, privileged actors or transient activity entirely between samples. Unclassified or
unreadable potential tasks still block; noncandidate churn is not a waiver for failed discovery.
An admitted defective producer could strip v2 scopes and falsely assert v1; no portable label
validator can discover that lie without native producer proof. Source admission and independent
producer-to-consumer oracles remain necessary. The protocol must not be presented as an OS
sandbox, absence-only settlement proof, or arbitrary job recovery.

## Graph, transaction and durable authority

The graph binds raw and semantic identities, canonical original approval/plan/receipt/events,
worker attempt and reachable dispatch records, relevant snapshots, and exact retained archives.
Original CLI root derives only from canonical `prepared.cli_used_path`; it is not an input option.
Unissued canonical event slots and worker finished remain explicit absences. Resolution markers are
excluded from the graph. New original-attempt records, orphan canonical events, replaced roots,
missing bytes, corruption or overflow block. Unrelated later manifests/attempts do not enlarge the
original graph; their ordinary canonical profile/schema validation still applies.

The actual retained-owner catalog declares `objects,attempts,events,children,finished,bootstraps`.
Its exact record definitions live in `resolution_worker_history_schema`; bootstrap request and
`.started.json` claim bytes are correlated by raw request hash, path, argv, birth and retained
source bindings. Original-attempt worker traversal uses explicit owner edges, not shared saved
refs, image hashes or file hashes as reverse links to later work. `worker_history(candidate)`
returns the validated original manifest, normalized saved-file metadata/tickets and old boot
without persisting a projection.

The separate prospective codec has namespaces `objects,attempts,events,children,requests,started,
finished`. Attempt files are `{request_digest}` indexed by approval digest; other objects have
`{schema,kind,attempt_digest,sequence,refs,data}`. Closed role definitions live in
`resolution_worker_history_fixture.worker_value` (re-exported by `resolution_graph`). This fixture
codec cannot serve as an authoritative projection of unvalidated old formats.

Bounds are conservative: ≤4096 scanned files, ≤8 MiB aggregate history bytes, ≤1 MiB individual
objects/frames, ≤256 source pins, ≤512 attachments (also constrained by frame size). Larger valid
histories fail closed; they are not silently truncated. Original graph output may itself hit the
1 MiB object bound before the file-count bound.

Canonical resolution objects live only in `ledger/resolution-objects`. Raw archives are SHA-addressed
`ledger/profile-archives/*.bin`. Transaction markers are exactly
`{resolution_digest,approval_digest,attempt_digest}` in these namespaces:

1. Archive old retained bytes and exclusively stage exact new profile bytes beside the active anchor.
2. `resolution-prepared/APPROVAL`.
3. `resolution-used/APPROVAL` (one use).
4. `resolution-ready/APPROVAL`.
5. `resolution-pending/ORIGINAL_ATTEMPT`.
6. Revalidate graph, pins, lifetime and old raw profile equality; atomic profile replacement and
   parent-directory fsync under the shared owner mutex.
7. `resolution-final/APPROVAL`, fsynced before reporting final activation.

Every partial/torn/foreign marker union blocks both upgraded owners, even if active bytes already
equal the candidate. No rollback, automatic replay, marker deletion or repair exists. A lost reply
after durable final does not erase final authority. Stage-only artifacts remain inert, with the old
unresolved attempt still blocking. Profile compare+replace is a cooperating-owner CAS, not atomic
compare-exchange against arbitrary same-UID writes. Mutex files are never unlinked.

Final validation traverses final → resolution → approval/plan → both evidence objects and their
attachments → graph → candidate/admission and raw archives. Expiry is evaluated historically after
commit. Current new profile equality is necessary but never sufficient. Inspection reports
historical status, resolution disposition, transition state and `replay_authorized:false` /
`next_attempt_authorized:false`. A separate new ordinary plan is the only route to later effects.

## Validation and remaining work

Run `UV_OFFLINE=1 just ci`; no native compositor/profile/ledger is used by tests. Targeted resolution
coverage is in `tests/test_resolution*.py`, including handwritten new-boot/same-boot, crash-prefix,
raw-history, old drift, foreign/cross-root/replay, unknown-writer, later-history, offline routing and
socket-only protocol oracles. A real isolated `-I -S` child also exercises the portable pure-read
hook while the parent holds owner/ledger locks, and confirms that child lock/profile-loader
reacquisition fails. That test does not implement or certify the machine peer-credential/birth/
kernel-lock-holder check. Thread-backed transport doubles do not qualify an installed observer.

Machine-owned integration evidence must separately cover exact historical/config binding, later
completed-history applicability, the closed loader/native producer, State read-only/legacy adoption,
complete source/platform module maps and independent cross-owner review. Those implementations
are not supplied by this portable package; this document does not classify separately owned work
as absent merely because it lives elsewhere. Native qualification and any required operator
authorization remain separate gates. Portable source changes authorize no real-attempt mutation.
