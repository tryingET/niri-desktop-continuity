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
- `map_preview`: escaped offline schematic and complete HTML ledger, including the per-window
  reopen ledger read from saved recipes (it never imports or runs `restore`). CSS is packaged beside
  the module; no access to a source checkout or external design service is needed after installation.
- `launch`: per-window reopen recipes from the same-user process tree (argv, cwd; inside Ghostty
  only: Claude session registry, Pi presence, leaf command). Titles match sessions to windows and
  are never stored.
- `restore`: placement plan (workspace compaction, unknowns last, protected live windows) and the
  spawn → detect → move → arrange executor with a receipt per run. No window is ever closed.
- `autostart`: opt-in systemd user units (periodic capture, reopen at login) and their removal.
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
- `recovery_projection`: optional closed additive grouping/diagnostics projected by a reviewed
  source owner, bound to saved set/private manifest/plan and retained unchanged through admission.
  Desired group/member sequence is visible in plan/preview/inspect, not inferred native topology.
  Absent historical projections never gain defaults or new meaning.
- `recovery_profile` / `recovery_adapter`: account-home owner trust anchor, closed recovery-control and critical platform pins,
  explicit isolated JSON socketpair IPC, per-effect permits, liveness and cancellation without kill.
  Additive-only pending keepalives correlate the exact existing intent; they cannot grant another
  effect or extend absolute expiry. Replacement v1/v2 pending-heartbeat behavior remains frozen.
  Monotonic complete-frame checks reject late renewal even with a patient/trickled socket.
- `recovery_ledger`: fixed owner-profile canonical Store, prepare/CLI-consume/ready crash fence,
  cross-root replay refusal and retained indeterminate history. Worker inherits the compositor
  lock; applications must not. An unresolved attempt blocks new reconstruction, not automatic repair.

## Ordinary restore candidate boundary

Ordinary restore uses the integrated launch-bound candidate. Disposition and subsequent association
corrections passed bounded independent review. The current full isolated CI passed 1,671 tests,
package builds and installed-wheel smoke; final Python 3.14 installed synthetic cases also passed.
The width-failed native attempt received separately approved partial accounting with original evidence
preserved. A fresh native attempt then opened a host but stopped before association or width handling.
That newer attempt remains unresolved; the corrected association path is not natively qualified.
No retry, cleanup or deployment is authorized by these source changes.

- `restore_attempt`: one explicit attempt owns flock, immutable full plan and one-use subordinate
  tickets. Closed, foreign, consumed and poisoned capabilities cannot authorize new effects.
- `restore_history` / `restore_records` / `restore_plan`: bounded append-only canonical v3 chains with semantically closed records,
  original Store directory identity, source/plan binding and durable receipt references. Legacy
  `.restore` files, orphan `.permit` files, incomplete/corrupt histories and missing original artifacts
  block all effectful writers across caller Store roots. Read-only consumers retain exclusive flock
  and identity validation without acquiring effect authority.
- `restore_producer` / `restore_host` / `restore_wire` / `restore_bootstrap`: the standalone process
  probe and ordinary restore share attempt/ticket admission. Niri dispatches an installed isolated
  bootstrap with a deadline-bound Unix handshake, peer/start pins and same-process pinned ELF fd
  exec. The coordinator retains pidfds through final owned effects. No timeout process kills or
  descriptor inheritance into applications. The standalone process-only probe remains unresolved.
- `restore_execute`: complete initial accounting before effects, support refusal before launch,
  subordinate proofs, placement, final observation, terminal commit and historical replay.
- `restore_state` / `restore_geometry`: pure typed geometry, legal empty-workspace lifecycle,
  stable logical destination binding, active-column insertion and source-focus transitions, shared
  with offline history validation. The handwritten test model does not use these predictors.
- `restore_dimensions`: admitted column-wide width policy, per-dimension pending/observed accounting,
  and current-output physical-pixel targets with Rust's ties-away-from-zero rounding.
- `restore_layout`: fresh owned/protected cohorts, singleton donor suffix construction, exact
  right-top-tile consumption, measured decoration sizing, floating conversion/relative fractional
  positioning, guarded workspace names and original-focus restoration. Every action is dispatched
  once after durable intent; bounded post-observation never authorizes corrective actions.
  Index-addressed transfers/names bind the caller's intended stable workspace ID, output and index.
  Fresh resolution must agree both before intent and after its durable write, immediately before dispatch.
  The closed history validates that binding against each recorded command and pre-state.

A terminal requires every entry accounted for and every dispatched effect observed. Frozen admission
is rederived from the immutable source and coherent baseline, without consulting historical host files
or cwd paths. Bootstrap specs must match the literal frozen recipe. Associations and every observed
layout must follow their recorded transitions; effects equal the observed action ledger. Final geometry
must equal a durable full final observation and satisfy requested placement, protected grouping and
dimension coverage. Already-open requires baseline recipe evidence; unsupported is frozen before effects.
A conservative journal-capacity budget is checked before preparation. Final receipt
fsync precedes canonical terminal fsync, then success-pointer projection. Lost pointer projection
never grants replay. Completed-source replay returns retained historical results without new native
observations or effects. A different source can proceed only with clear history and a fresh baseline.
Fully accounted unsupported entries terminate as `partial`, not indeterminate and never success.
Ambiguous effects, missing geometry or unsupported in-progress layout remain unresolved; no retry,
rollback or process cleanup is provided. The narrow explicit accounting-only disposition described
below is not a generic resolution or completion API.

Only controlled fresh Ghostty shell/command/declared/Pi/Claude hosts are admitted. Browser/general
application ownership is unsupported before launch. Sequential placement supports Niri's normal
trailing-empty lifecycle from clean login. Only unnamed, empty, inactive transient cleanup and edge
creation are admitted; named/nonempty/protected workspace identities and relative order are preserved.
Logical destinations survive permitted per-output reindexing, including optional empty-above insertion.
Insertion is after the active column, not append; `--focus false` leaves focus on the source workspace.
There is no arbitrary workspace-creation feature. Source monitor affinity is not restored.
Consistent explicit widths govern the whole admitted column; unspecified members report
`inherited-column` only after observing that width. Conflicting explicit widths refuse before launch.
With no saved width, preserve the admitted seed's width; other members inherit it. Standalone extra
columns preserve their own admitted widths. Requested dimensions start pending and are promoted by
explicit equality checks on verified observations, not intent or overall success. Known decorations
are required for a resize, but not when the requested width is already observed. Only column seeds
need resize admission; consumed donors inherit the seed's geometry without a separate resize.
Fixed-width CLI tokens are positive unsigned decimal integers within i32. A candidate is selected
from requested tile width minus measured decorations, then admitted only if integer plus decorations
reconstructs that requested observable width exactly, survives the native inverse-subtraction/floor,
and stays within Niri's 1–100000 tile clamp. No tolerance, truncation or rounding of the requested
width is accepted. Seed preflight runs after association but before that host's placement effects;
refusal leaves the launched attempt unresolved. History applies the same strict token/prediction rule;
old decimal-token intents remain nonexecutable without rewriting or migration. Only the exact
reviewed pending family may be read as retained data and explicitly accepted as partial. Native constraints, scale
quantization and hidden decoration differences can still fail exact post-observation; no retry follows.
Floating targets use current `outputs.logical.scale`, physical-pixel rounding with ties away from zero,
and round-trip-precision signed deltas. Unknown scale cannot prove a requested position. Coverage marks
`requested-quantized-observed` when the observable target differs from the saved coordinate. Verification
remains exact, without a tolerance. Niri's hidden unrounded positions/native constraints can still make
a relative action fail its postcondition; no retry follows. Saved tile height is not restored.
Protected workspace metadata cannot be renamed; conflicting names block rather than create extras.
Protected grouping, relative order and dimensions are checked; numeric reindexing from owned
insertions/removals is allowed. Observed index/output drift stops before stale dispatch without rewriting
intent. The final check and IPC are still non-atomic, including compositor-driven cleanup; idle operation
reduces external interference but does not eliminate that race. Candidate v1/v2 histories fail closed;
there is no migration or generic settlement path.

Trust still includes installed Python/bootstrap, native Ghostty and its fresh connection behavior:
no forwarding, fork/connection transfer or unobserved same-image exec. Process polling alone cannot
prove that behavior, Python module origin or general Wayland causality. The nonce binds the attempt,
not a privilege against same-UID code. Custom Ghostty configuration is discarded after defaults are
read. Desired environment is sanitized; observed `/proc` initial environment is compared raw, not
normalized into matching evidence or mistaken for current dynamic libc state. FIFO nonblocking
admission and hash-loop deadlines do not bound every possible kernel/storage syscall.

Fabricated tests exercise multi-host resulting topology, interleaved protected columns, multileaf
consumption, nonzero decorations, fractional floating positions, focus, replay and crash boundaries.
Both the installed editable console and a freshly built wheel console run the real producer/bootstrap
against two bounded cooperative ELF hosts and a handwritten fake Niri lifecycle. The wheel test copies
only fabricated fixture definitions, checks installed import origins, and does not import checkout runtime
code. Single-empty-start multileaf and multi-workspace outcomes are verified. These are synthetic ownership/layout results, not native application or
session-usability proof. The test ELF requires a local C compiler; skips do not qualify this path.

### Protected-dimension refusal diagnostics

`restore_failure_observation` retains only the first `Layout.proofs` protected-dimension
refusal. Interrupted receipts may contain **`first_rejected_observation`**, separate from the
unchanged later `final_observation` fallback read. Neither is an admitted final observation.
The new field never appears in successful receipts or historical replay and is not accepted by
ordinary terminal validation or either existing disposition family. No history record/schema,
effect accounting, proof teardown, state transition, query count, sleep or retry policy changes.
Older receipts remain unchanged; absence means no retained diagnostic, not preserved dimensions.

The optional field has a closed `schema="restore-protected-dimensions.v1"` body:

- Normal fields are exactly `schema`, `phase`, `refusal_check_ns`, `queries_ns`, `sample`,
  `changes`, `unobserved`. `phase` is the proof call site: `fresh`, `postcondition`,
  `association`, `association-baseline`, or direct `proofs`; it is not a causal explanation.
- `sample` contains 1–512 rows, each exactly `id`, `protected`, `tile_size`, `window_size`.
  IDs are unique integers from zero through 2^63−1. `protected` is baseline cohort membership,
  **not** an ownership assertion about other windows. Sizes are two finite positive numbers,
  at most 1,000,000,000 each, or `null` for missing size. No titles, process IDs, recipes,
  argv, environment, paths, workspace/output names or arbitrary native metadata are copied.
  This is a dimensions-only projection of the checked state, not a full desktop snapshot.
- `changes` contains 1–1,024 rows, exactly `id`, `field`, `before`, `rejected`, `delta`.
  Each unique `(id, field)` references a protected sample row; field is `tile_size` or
  `window_size`. Both pairs use the size bounds above. `rejected` equals the sample value,
  differs from `before`, and `delta` is componentwise rejected minus before, finite and
  bounded in magnitude by 1,000,000,000. A missing pair makes `delta` explicitly `null`.
  The producer records all size differences against the original protected baseline, without
  rebasing. Other identity/proof checks need not have completed; these differences grant nothing.
- `queries_ns` has exactly `windows`, `workspaces`, `outputs`, each `[start, end]` or `null`.
  Integers are process-monotonic nanoseconds bounded to 0–2^63−1, bracketing the already
  executed transport method, not compositor processing timestamps. Available intervals are
  ordered and nonoverlapping. `refusal_check_ns` uses the same clock at first guard refusal,
  before projection, or is `null` if unavailable. Available intervals cannot end after it.
  Neither clock is receipt-write time or a cross-process/wall-clock identity.
- `unobserved` is exactly `["fullscreen", "work_area", "layers"]`. These data are not queried,
  reconstructed from sizes or inferred. No explanation of a height change follows from timing.
- The alternative body is exactly `schema` plus `unavailable=true`: retention exceeded its
  bounds or failed. The serialized ASCII projection is capped at 512 KiB. Export checks the
  closed schema again; diagnostic faults, including interruption inside diagnostic generation,
  cannot replace the original protected-dimension refusal. No raw fallback is permitted.

Retention serializes the projection immediately, so later mutable samples and fallback reads
cannot overwrite it. Even an unavailable first retention latches; it is never retried. Only the
currently bound decoded sample receives its query intervals. Reused/deep-copied association
baselines have unavailable query timing rather than the latest unrelated query's timestamps.
The association classifier still runs first: malformed/split-classification refusals outside this
specific dimension guard receive no new field. Constructor mismatch and non-dimension refusals
also remain outside scope. Failure before reaching the guard cannot manufacture a rejected sample.
Normal query timing is **not best-effort**: a clock exception before a query or after its
successful return propagates and stops effect admission. If the query callback is already raising,
end timing alone is best-effort and cannot replace that original exception. Only after the
protected-dimension veto are clock/projection/export failures contained to preserve the refusal.
Queries remain sequential, not an atomic desktop observation. Existing last-check-to-action races,
proof trust and fallback limitations are unchanged. These diagnostics cannot authorize disposition,
retry, cleanup, native qualification or deployment.

### Association-only coherence boundary

`restore_observation` classifies one narrow split family, not a repaired desktop state. Complete
independent structural validation precedes relational classification. Canonical windows must equal
the original pre-association windows exactly, including sizes and view positions; outputs and all
workspace metadata/order must match. Only the admitted focused workspace may reference one new
nonnegative integer window ID absent from the windows reply. The only allowed relational defects
are that missing reference and its consequent old-focused-window mismatch. Known foreign IDs,
multiple missing references, malformed later entries/scales and simultaneous lifecycle/reindex changes
refuse immediately. `restore_state.decode` still rejects every invalid reference; initial/fresh reads,
effect observations, error fallback and historical decoding never use this exception.

The output baseline is a validated **full output inventory** copied from the incoming coherent
capture, before the first Layout read and any launch, not the workspace-only output-scale projection.
Every subsequent sample compares the complete inventory: constructor, prelaunch fresh, pre-effect,
postcondition and error reads, as well as association. Every inventory-check failure, including
BaseException/interruption, latches refusal before propagating unchanged. Constructor validation
starts latched and clears that flag only after the incoming inventory validates. A malformed or
changed inventory permanently refuses further sampling by that Layout; error fallback cannot consume a later recovered reply or
silently rebase the evidence. Missing captured inventory or an unavailable output-query transport
refuses rather than inventing an empty inventory. Unchanged disabled outputs with
`logical: null` and no workspace are supported, including split-to-whole mapping. New/removed outputs
or disabled-output metadata drift refuse. This transient inventory is not a new history/receipt field;
canonical state/geometry retain their existing workspace-output scales. Outer output order, mapping
keys and JSON object key order are irrelevant. Finite JSON numbers compare numerically (`1` = `1.0`),
never by Python's boolean/integer alias. As a deliberate conservative bound, all entry metadata,
field presence (including missing versus null) and ordered arrays are retained: even otherwise harmless
metadata changes refuse rather than silently rebase. Mode-array order can affect the current-mode
index. Typed known metadata and finite bounded JSON are validated, including disabled entries:
at most 512 outputs/items per container, 65,536 visited metadata nodes, depth eight and 4,096 characters
per string. Integer magnitude must not exceed the largest finite Python float (`sys.float_info.max`);
this explicit inventory-only range is checked as integers without rounding or overflowing float
conversion. Oversized JSON integers raise ValueError. Floats must remain finite. This deliberately
excludes integers just beyond that limit even if float conversion would round them back into range.
Unknown metadata remains bounded JSON, not an invented native semantic interpretation.

Decoder compatibility intentionally narrows: window `workspace_id` must be an actual integer.
Boolean `true` and floating `1.0` no longer alias integer workspace 1. This sensible hardening is retained
and explicitly tested; “strict decoder preserved” does not mean literally identical historical
acceptance. No state schema or geometry transition was changed by the inventory correction.

One association retains its immutable original baseline, one pending ID/workspace pair, and a total
allowance of three eligible split samples, never reset. Every sample is independently queried; no
windows/workspaces are merged across replies. Observed unowned arrivals, protected drift, surplus
outputs or changed/disappeared pending references stop the attempt even if a later sample would recover.
Only a strict whole sample with the same active reference, unique launch-proof PID and ID/workspace
can reach unchanged `restore_geometry.associate` and one normal association append. There is no
provisional association, new launch/permit, corrective effect, cleanup or history schema change.

One absolute process-monotonic association deadline surrounds queries, pending and previously owned
proof checks, sleeps and the association append. Read-only IPC waits use the remaining budget, capped
at ten seconds; query failure/timeout is fatal, not another eligible split. A persistence overrun may
leave a durable association record: execution stops before success/layout and retains that record.
Kernel/storage calls may be non-preemptible; the guarantee is no late acceptance, not a hard wall-clock
return bound. The launch proof owns the already admitted directory pin and retained CLOEXEC directory
FD, comparing held identity, pathname and the launched host's `/proc/PID/cwd` around observations.
Closing proofs releases descriptors without terminating hosts. Utility-child cwd and session usability
are not inferred. Attempt teardown attempts every owned proof close and calls lock exit in a finally
path even after a close raises a BaseException. A sole cleanup failure propagates unchanged; multiple
failures, including an active body exception, remain visible in a BaseExceptionGroup. Successful
cleanup does not suppress the body exception. Standalone producer transfer is guarded until attempt
exit succeeds; failed exit closes the orphan proof, including on interruption. If orphan close also
fails, its error retains the exit error as exception context. No host termination, fence clearing or
cleanup retry is involved.

The fabricated schedule maps a host between windows and workspace replies, then supplies a strict
whole sample and verifies complete placement/history. This supports the correction, not a claim about
the exact cause of any unretained native failure. Polling cannot see events entirely between samples;
last-check-to-action races and trusted host behavior remain. Independent source review, parent-owned
full CI, native qualification and deployment are separate gates; none is granted by these tests.

### Ordinary interrupted disposition boundary

`restore_retained` supplies the shared bounded structural reader and exact raw-byte manifests.
`restore_history` still validates every ordinary semantic transition. The v1 exception decodes only the nine-record reviewed
v3 pending integral-decimal-width family as nonexecutable data: one strict preparation,
bootstrap/exec intent-observation pairs, association, column-move intent-observation pair, and final
width intent. No normalization feeds old tokens into the executable grammar. Without a valid special
canonical ending, `require_clear` still refuses every effect writer across caller roots.

`restore_disposition_evidence` binds the original interrupted receipt to original synchronous CLI
result/exit files in one explicitly selected private witness directory, independently of the original
Store path. It checks exact result/source/receipt/command/exit
matching, owner/path/inode/raw hashes, fresh double-read Niri topology, protected current process
pins, the associated host's recorded boot/PID/start/ELF/argv and retained pidfds.
`restore_disposition_cwd` holds the original directory FD and checks both its pathname and the host's
actual process cwd against the bootstrap directory pin; this is not a utility-child cwd policy. It copies no raw
historical diagnostic titles or environments. Installed-client and operator-attested original-witness
provenance are explicit trust, not kernel authentication. No native-session usability is inferred.
Legitimate later desktop changes are bound as the new baseline, not required to match old heights or
protected layout and not evidence of historical preservation.

`restore_disposition` and its CLI helper own a separate closed disposition plan/approval/receipt
schema using generic Store artifacts, never reconstruction/reconciliation capabilities. Approval
requires the exact plan digest, literal partial acceptance and original-client-return attestation.
The TTL is at most 900 seconds. One existing exclusive flock covers independent revalidation,
approval consumption, receipt persistence and canonical append. No Niri action, application launch,
termination, prior-record edit, last-reopened update or retry authority exists in this path.

Commit stages and fsyncs one record under a noncanonical name, then performs the last live/expiry
veto before rename and directory sync. An orphan/partial staging name fences admission; a visible
canonical name alone is NOT durability. `restore_history.load` is pure validation, not admission.
`restore_history.admit`, under the same flock, fully validates the special flow, barriers its exact
private files and parent directories through identity-checked FDs, then verifies unchanged evidence.
Dependencies include original bytes/witnesses, plan, approval, consumption, receipt and canonical record.
All effectful flock users and Attempt admission/replay use this barrier; disposition replay does too.
A persistent file/directory sync failure never releases authority. Later successful barriers on an
already approved/consumed valid record may establish durability now, without rewriting, new approval,
consumption, canonical append or current native observation. This does not prove original apply success.
Pure inspection never fsyncs and explicitly leaves durability/admission unestablished.

`Store.put` now also validates and file/directory-syncs an existing equal artifact before returning;
a content address cannot substitute for durability after an earlier failed fsync. `sync_artifact`
refuses missing, altered or substituted validated evidence and retains identity-checked FDs through
both barriers. No repair or endless acknowledgement-marker protocol was added.

Live process/topology/cwd vetoes occur after the last slow history/dependency reads, immediately before
consumption, and again after durable staging before publication. Expiry is checked there too. Context
exit only releases proofs; it cannot discover a mandatory fresh veto after canonical publication.
There remains a non-atomic last-check-to-publication/fsync interval against external activity/process
exit, not a guarantee of frozen native state. After publication, later process changes are new state,
not retroactive refusal of partial accounting. Idempotent replay does not reobserve or reapply. No arbitrary terminal
status releases a fence. Different-source ordinary admission still requires its own fresh baseline;
original-source replay is partial exit 2, invocation effects empty and historical effects separate.
The CLI's ordinary manual apply remains explicit operator action, not newly digest-approved execution.

Independent disposition re-review and the full isolated gate passed; original native-witness
validation and any live disposition remain separate approval gates. Synthetic process tests use real
pidfds, `/proc` and a cooperative fabricated ELF but fake Niri; they are not native qualification.
The operator flow and exact witness format are documented in [usage](usage.md#explicit-retained-partial-disposition-candidate-independent-review-pending).


### Exec-observed-unassociated v2 (offline verified)

The corrected implementation passed bounded independent review, installed-wheel CLI lifecycle tests
on Python 3.13/3.14 and parent full isolated CI (1,671 tests). These results do not authorize or
qualify actual native disposition, retry or deployment.

The existing `restore-disposition inspect|propose` commands require explicit
`--family exec-observed-unassociated` for this family. Omission remains the absolute-nine-record
v1 width family; v1 schemas, native width grammar and ordinary terminal semantics are not widened.
Approval/apply route by the exact stored schema, never by a generic partial status. Runtime
requirements remain Python standard library and the existing Linux/Niri process/IPC surfaces.

The active segment is exactly five records: prepared, bootstrap intent/observed, exec
intent/observed. It has one initially unprocessed controlled entry, no pending intent, association,
layout, final observation or terminal claim. Its global offset may follow validated v1, ordinary
terminal or v2 completions across original Stores. Snapshot digest, attempt and original launch
identity cannot reuse earlier attempts' identities. The segment has exactly seven fields:
`start`, `count`, `previous`, `exec_intent`, `exec_observed`, `process_receipt`, `baseline_digest`.
The two exec references are their payload receipt digests (not canonical envelope digests);
`process_receipt` identifies the observed exec evidence. The other fields bind the actual global
suffix offset/count, preceding canonical digest and frozen prepared baseline digest. Historical
process reuse compares `(boot_id, pid, start_ticks)`, ignoring incidental metadata; a recycled PID
with a different start is not permanently banned. Existing history boot validation remains strict.

The original witness must have error type `ValueError`, exact error `foreign active window`,
interrupted/not-proved status, empty effects, and exactly one `launch-indeterminate` row with its
frozen entry, saved ID, pending dimension coverage and original process receipt. No restored-window,
initial-width or target-workspace association fields are accepted. The diagnostic final observation
is either a canonical bounded state or exactly `{"unavailable": true}`; it never supplies ownership.
The original synchronous client body and exact `2\n` exit file are separately bound in one private
directory. No exception relabelling, witness reconstruction or other diagnostic is accepted.

Fresh double-read topology and held pidfds prove one current window for the original boot/PID/start
pin. Its window ID/PID cannot overlap the historical protected baseline or current controller
ancestry; its process identity tuple cannot reuse a prior launch. Every current protected process is proved, along with the owned running ELF,
original pathname image, argv and original cwd/process-directory identity. The plan records a closed
current partition and proposal-time `controller_pids`; approval/apply independently veto overlap
with their own fresh ancestry, which need not have the proposing CLI's transient PID. The historical
validator checks the recorded partition, pins, bootstrap bindings and exclusions without probing
historical processes or claiming a historical association. These are canonical topology observations,
not full physical-output inventory or native-session verification.

`restore_history.validate` processes dependencies sequentially, bottom-up, without recursive history
loading. `restore_disposition_dependencies` mediates legacy file helpers as well as ReaderStore
artifact reads. Closure includes every preceding/current canonical record, payload, original source,
process receipt, and earlier dispositions' validated plans, approvals, approval-keyed used markers,
receipts and original witness files. Ordinary terminals and their receipts are included too. A v2
plan's manifest must equal the independently derived preceding closure, not a traversal of supplied
paths. Unreferenced, omitted, duplicate, conflicting or forward/self-bound manifest data refuses.
The used marker is checked by approval-key pathname and exact consumption body, NOT body-content
address. Unknown/mixed schemas, fields, type aliases, bad cross-references and incomplete commits
cannot release a writer. Both plan limits and partial receipts use the exact literals
`historical_association="not-recorded"` and `outcome="unresolved"`; earlier unreviewed wire values
are rejected, not compatibility aliases.

The initial v2 test fixtures used an incorrect row/wire and are retained only as development
history, not intended-family qualification. Correction tests include an unchanged ordinary
executor/real bootstrap and cooperative ELF: a forced exact ValueError at read-only association
produces the original five-record chain, CLI-like output and exit 2. After accounting, a separate
fresh source actually reopens and places another cooperative host using fabricated Niri IPC and
commits its ordinary receipt. Independent rereview reproduced this positive continuation; it remains
synthetic execution, not native qualification.

#### Durable pins versus current-interval pins

Persisted manifest/witness raw hashes, lengths, file and parent identities remain mandatory and are
never regenerated as expected values. A new plan binds prior generated dependencies **as observed
at preparation**, not as independently proved original-creation inodes. Once persisted, those pins
remain binding through later admission. Conflicts reject before deduplication.

The latest generated plan/approval/receipt without a prior persisted pin is bound by its canonical
semantic digest and closed cross-references; used data by its exact approval-keyed consumption body;
the ending by its closed envelope, sequence/path/link, attempt, origin and receipt reference.
Semantically equivalent replacement, including whitespace, **before the first authoritative
observation may accept** when no durable pin forbids it. Missing or inconsistent artifacts never
cause reconstruction, repair or recreation of a consumed/incomplete flow.

Within every authoritative validation → barriers → fresh-validation interval, FIRST-observed raw,
file and parent pins also bind all newly generated artifacts as they appear. Fresh readers receive
those expected pins, not rebased observations. Raw drift, inode or parent replacement rejects.
The sole path substitution is the controlled staged-to-canonical rename, retaining the other pin
fields. A new invocation does not inherit unpersisted in-memory pins from an earlier invocation.

Terminal trust is the owner-controlled canonical append-only filesystem plus trusted application
and operator workflow, **not cryptography against a malicious account owner rewriting the graph**.
The newest ending has no independent durable original-creation-inode anchor. There is no self-
authentication, infinite acknowledgement chain, new trust authority or signed-log claim. Stronger
signed-log provenance would require a different design. Partial accounting never certifies original
apply success, historical layout/association, native sessions or permission to retry a launch.

#### Routing, resource bounds and publication

Default loading routes envelopes under the existing flock, decoding one at a time without reading
ordinary payloads. Its separate allowance remains 4,096 canonical files × 16 MiB (64 GiB), plus one
at-most-16-MiB sequence-nine disposition discriminator. Unknown discriminator schemas refuse. At
every v2 boundary, routing pauses and a NEW reader budgets the cumulative prefix before materializing
ordinary payloads. Full semantics must succeed before envelope-only routing resumes. A later v2
boundary requires another independently cumulative pass; an ordinary suffix without another v2
retains legacy bounds. This scheduling is tested with actual completed mixed-version histories,
not only the earlier synthetic routing-hook fixtures.

Each v2 validation pass permits **32,768 unique normalized absolute paths, 512 MiB aggregate unique
raw bytes, 16 MiB/file**. Routed canonical bytes and earlier manifests count again in the closure.
Identical bytes at different paths/Stores count separately. Known paths/stat sizes reserve capacity
before ordinary payload decode; every subsequently discovered dependency reserves before its IO.
`restore_reader_io` checks held no-follow/CLOEXEC file/parent descriptors, reservation and current
path before data IO, around each unbuffered read and afterward. No request/returned bytes exceed
remaining reserved length; short reads fail without retry or an extra EOF probe. Failures, including
BaseException and external semantic failures, retire the failed pass and parsed/raw caches. Complete
post-barrier validation uses new readers; cached parses do not cross barriers.

Non-authoritative plan/approval schema routing uses a one-file 16-MiB Reader, preserving the existing
v1 artifact allowance without imposing a v2 closure cap on v1. It cannot substitute for the complete
v2 authoritative pass. Explicit active-v2 inspection/proposal uses strict bounded materialization;
apply probes its candidate ending through a Reader before selecting active strict validation or
normal per-prefix historical replay. It never eagerly parses a legacy suffix just to discover that
an active v2 segment needs the cumulative cap.

One held compositor flock covers live proofs, complete validation, persistence and admission.
Before consume, the complete prospective footprint counts existing ACTUAL bytes plus exact future
serialized bytes, without future-inode fields. The existing noncanonical `.pending` ending is made
durable before consumption, so even a pre-receipt failure fences this attempt and a different
approval cannot bypass it. Its full bytes/identity join the operation interval; it grants no authority.
After stage barriers and fresh validation, the complete capacity check runs LAST, with no expanded
semantic dependencies before consume (the internal approval read is Reader-mediated). Live topology/
process validation and expiry are repeated **after** that final capacity/dependency check,
immediately before approval consumption. Drift there leaves no used marker; the existing stage may
remain fenced. Used marker and receipt are then persisted/pinned, all dependencies barriered and freshly semantically validated,
and the final live/expiry veto runs before rename/publication. Staged and canonical names represent
one ending role in separate passes, not two simultaneously retained files. No additional marker type,
canonical envelope schema, Store kind, Store source change or generic lifecycle framework is used.

A visible canonical file is not durability. Every accepting writer/admission/replay path validates,
barriers and revalidates the completed closure. Historical replay may establish durability now, with
no new native observation, consumption, append, pointer or claim that the original apply succeeded.
Inspection never syncs or grants admission. Failure leaves existing stage/consumption data fenced;
there is no cleanup, automatic retry or rollback. Non-atomic last-check-to-publication races and
trusted no-forward/no-unobserved-exec host behavior remain explicit limitations.

**512 MiB is not total IO or RAM.** Routing, input classification, repeated cumulative validation,
barrier reads, legacy suffix IO, metadata and decoded Python amplification are separate costs.
Counters report Python read attempts/request lengths/returned bytes, not kernel IO or RAM. Source,
handwritten chained/adversarial tests and installed-wheel synthetic CLI checks are development
proof only. Independent code review, parent full CI, native qualification and deployment remain
separate gates; none is authorized by this offline implementation.

### Exited associated shell v3 (offline candidate)

`restore_exited`, `restore_exited_model` and `restore_exited_history` implement a distinct,
explicit `associated-shell-protected-dimensions-interrupted` disposition. The suffix is exactly ten
records: prepared, bootstrap/exec pairs, association, workspace-transfer pair and owned-focus pair.
Only an original seven-field protected-dimension failure witness qualifies. **Every extra receipt
field, including the new `first_rejected_observation`, refuses**; diagnostic code is unchanged.
Earlier mixed-family history is validated independently, cumulatively and bottom-up. No historical
executable, cwd, process, namespace or compositor is reopened during inspection/replay.

`restore_exited_transport` uses one persistent, bounded LF JSON Unix stream; every accepted reply
has SO_PEERCRED checked on that same FD. `restore_exited_scope` holds the validated procfs root,
active PID/user namespaces and live role-specific generations. New live proofs use
`native-niri-continuing-peer-procfs-self-pidfd-esrch.v2`: genuine held `/proc/self` plus singleton
NSpid/NStgid establishes that the proc mount and caller share active PID coordinates, including a
nested matching scope. No init namespace is opened or queried. The scope independently owns its
flags-zero caller pidfd. Full-role generations (caller, peer and every protected owner) refresh
active PID/user namespace handles using their same retained pidfd each cycle. Same-user process objects and stable identity fields are mandatory;
changing memory/scheduler counters are not generation drift. Unknown ancestry still refuses.

Authenticated peer, inventory, Version and strictly decoded discovery precede a frozen full-role
cohort. All its full proofs succeed before walking actual ancestry. Caller remains full without a
window. Other ancestors use a distinct exclusion-only generation, not an ordinary generation with
optional namespace handles. Genuine numeric proc lookup and strict singleton NSpid/NStgid, each
matching Pid=Tgid, establish the ancestor's active PID coordinates in the already proved mount.
Held directories, route provenance, four UIDs, boot/start/parent and live pidfds remain mandatory.
No target namespace ioctl is required for an ancestor-only row. User-namespace equality or stability,
executable continuity and positive effect ownership are **not** asserted for that row. Equal UID
projections are not namespace evidence; repeated aliases such as `[42,42]` still refuse.

Strong-then-ancestor reuses the full object. Ancestor-then-strong refuses, never promotes or replaces
it; failed full proofs never fall back. All retained generations participate in ordinary and late
checks and cleanup. The initial complete chain ends at ppid=1 excluding init, at most 128 rows;
observed parent/generation/cohort drift refuses without rebasing. A later window owned by a weak
ancestor cannot turn it into a full proof. No siblings, descendants or other manager sessions are
thereby controllers or safe effect targets. These are sampled identity/exclusion checks, not an
atomic lineage snapshot or proof against unseen reparenting/exec between samples.

`restore_exited_syscalls` checks Linux little-endian x86_64 GNU LP64, real libc fstatfs/statx, and a
bounded stable upstream-compatible release >=7.2.6 (prerelease/development tokens refuse). This is
platform compatibility trust, not running-build attestation or a backport registry. Unique mount IDs
are unsigned 64-bit values. `restore_exited_proc` authenticates every component's mount/type/owner
and same-FD statx/fstat identity before reading bounded stat/status/boot content. Public-root
reauthentication detects even same-inode bind replacement. Structural kernel-owned objects may
project overflow UIDs; only process objects require caller ownership. Production never unshares,
changes namespaces or substitutes a permissive proc root. The old PID
must produce ESRCH **at `restore_host.open_pidfd` itself**, including its libc fallback. Returned
FDs (also zombies/reused slots) and every other errno refuse; `Process.live` remains unchanged.

`restore_exited_proof` brackets two strictly equal topology samples with held-generation/scope/
current ELF checks and two exact ESRCH observations. V3-only resource wrappers retain the primary
exception when native FD release also fails, without changing old-family ELF/live-process behavior.
All current windows are protected. Every stage proves its own caller ancestry; proposal caller IDs
are not reused as live proof. Peer inventory
matching uses the authenticated tuple, never a process name. The immutable historical `niri_version`
is exactly `{compositor, cli}`; only `compositor` matches the authenticated Version string, while
both members remain source-digest/raw-pin dependencies. Version and current ELF hashes are not
historical executable/build attestation. Current outputs remain the workspace/scale projection.

`restore_exited_image` follows only literal `exe` relative to the authenticated held process
directory, keeping the checked no-follow symlink pinned through pre/post route/generation checks.
An FD-taking v3 Image takes ownership before hashing; no absolute proc-exe or target-text reopen
exists on this route. System-owned executable targets need not share proc owner or mount. **The
follow is a second lookup, not atomic pinned-symlink traversal**: a privileged transient substitution
restored before postchecks can escape detection. This accepted sampled-route/nonmalicious-owner
limit is not unconditional ELF provenance. Likewise readonly component opens can encounter foreign
VFS/LSM/device callbacks before rejection; NONBLOCK/NOCTTY is not a filesystem sandbox or a hard
syscall deadline. Hashing measures current sampled ELF identity, not its historical build/libraries.

The v3 family has exactly three method discriminators:

| Method | Exact procfs keys | Admission |
| --- | --- | --- |
| `native-niri-continuing-peer-pidfd-esrch.v1` | device, inode, filesystem, init_pid_namespace | Historical only |
| `native-niri-continuing-peer-procfs-self-pidfd-esrch.v1` | device, inode, filesystem, mount_id, pid_namespace | Historical only |
| `native-niri-continuing-peer-procfs-self-pidfd-esrch.v2` | device, inode, filesystem, mount_id, pid_namespace | Sole new live method and history |

Both self methods retain independent positive uint64 mount-ID grammar and namespace equalities.
Their wire shapes intentionally match; the discriminator binds trusted runtime testimony, not
kernel attestation. Self-v1 retains its stronger historical ancestor-namespace meaning, never the
new exclusion-only semantics. For self-v2, scope.user_namespace pins only caller and full-role
processes; roles derive from caller/peer/protected membership, with no new wire fields. Init's
original meaning and every old artifact remain unchanged. Unknown methods and key mixtures refuse.
Receipt methods derive from the validated bound plan, never an ambient default. Completed old
replay remains native-free (with unchanged durability barriers), even expired. Unfinished old
approve/apply refuses before current proof, barriers or authority writes; no artifact is migrated
or relabelled and existing stages stay fenced. Stable scope excludes only the transient stage caller.

The fixed `plan.platform` discloses operator-trusted same-lifetime native endpoint/PID scope, without
serving handover, namespace-changing proxy or PID translation. Approval requires its separate exact
`--ack-platform` digest. Peer credentials cannot identify an inherited/transferred serving task:
a controlled FD-handover test demonstrates that limitation, rather than claiming to detect it.
Persistent sampling is not a transaction, and neither transient PID-slot occupancy nor same-image
exec wholly between samples is excluded. No descendant/session closure or exit time is inferred.

V3 has its own publication order: exact future receipt/caller bytes; durable `.pending` before
consume; fresh bounded semantic passes; complete capacity check **then** live/expiry veto; consume
and receipt barriers; another full live/expiry veto before rename; barrier-backed historical
admission. Failures never clean or repair a stage. First-observed generated-object pins cross all
barriers without rebasing. Exact old-source replay is historical partial with no native route query,
new consume, launch or pointer promotion, including from a different caller Store. Direct disposition
replay requires the original Store. Different-source restore still needs its own ordinary invocation
and fresh protected baseline. Existing v1/v2 schema defaults and diagnostic producers are not widened.

Fabricated tests include a handwritten ten-record legacy oracle after a validated sixteen-record
v1+v2 prefix, actual controlled sockets/procfs/pidfds, separate stage callers, real bootstrap/ELF
continuation, and an authentic diagnostic-bearing executor failure as **negative** compatibility.
Test-only private user/PID/mount namespaces exercise genuine self and active pidfd handles.
A direct child in a nested user namespace maps outer fixture UID/GID 0 to inner 1000, drops all
capabilities, independently observes init namespace EACCES, then passes actual Scope and full
current proof with a cooperative peer. Active PID namespace and proc mount stay outer. This is a
mapped nested-user fixture, not ordinary-host qualification or a selectable production backend.
The kernel integration tests require an offline development cache, private HOME/XDG/TMPDIR, a C
compiler and permitted Linux user/PID/mount namespaces with procfs/chroot. Capability failures are
test failures, not passing skips; none of these helpers is a production proof selector.
No unmodified pre-diagnostic producer or real desktop has been qualified by these tests. Independent
implementation inspection and separate native authorization remain necessary.

### Disposition diagnostics and lifecycle prerequisite

The in-memory `restore_disposition_failure` tracker is command-local, not an artifact or admission
capability. Library failures propagate as actual objects; the CLI alone projects them to bounded
static errors. Phase failure latching precedes owned-resource unwind. Cause/group traversal uses
identity, never implicit context, exception strings or notes. Diagnostic construction/write/flush
failures retain the selected nonzero exit and original failure internally, without fallback.

Disposition lock callers opt into `_preserve_disposition_failures=True`, only with read-only,
existing-only acquisition. The actual boolean defaults to false for every other caller; path,
flock, admission and creation semantics remain unchanged. Opt-in retains a pre-yield/body primary,
its prior cause and a close failure; close-only failures propagate unchanged. Lock FD ownership
retires before its sole close. The bounded raw reader attempts both descriptor closes and retains
all actual errors. Reader caches retire once and both clear callbacks run. Disposition v2/v3
reader-owning lifecycle boundaries preserve the identical primary and its prior cause across
all owned reader releases, including the initial and authoritative readers. Publication retires
its reader before release, without a second close attempt after rename. V1 has no direct
reader-owning finally boundary; its routing readers use the same preserved v3 route.
The disposition CLI tags the exact missing-socket predicate before the existing native identity
lookup, retaining ValueError type/text without message-based classification or family inference.
V3 proof-resource instrumentation only records cleanup diagnostics; accepted proof predicates
are unchanged.

This prerequisite does **not** implement paired retained-pending routing, inventory/closure rules,
anonymous-inode publication, new-family consumption or admission. It also does not yet cover all
inherited buffered Store/stream/barrier teardown paths or detailed OLD-v3 preconsumption tags.
No eligible F2 producer-to-consumer lifecycle or full accounting protocol proof is claimed.
See [failure-output limits](usage.md#disposition-failure-boundary-offline-prerequisite-candidate).

## Resolution implementation boundary

`resolution_candidate`, `resolution_graph`, `resolution_evidence`, `resolution_observer`,
`recovery_transition`, and `recovery_resolution` add exact candidate admission, observation-only
settlement proposals and append-only profile activation. `resolution_io` isolates bounded canonical
objects; `resolution_lock` establishes anchor → ledger → compositor ordering. `resolution_cli`
routes new offline previews/inspection before Store construction. Normal admission consumes one
shared explicit old-to-new edge without relabelling historical indeterminate accounting as success.

Exact retained owner-history decoding and its configuration binding are implemented here, with
fabricated oracles for original and later completed record shapes. This is **not native
qualification**. The native producer and closed owner loader are separately owned and are not
shipped here. Unknown formats block; the separate prospective codec must never be written beside
old records to manufacture settlement evidence. The detailed
[checkout-only owner contract](project/resolution-protocol.md) lists supported history, APIs and
wire fields.
That new document is not in the current sdist allowlist; runtime modules do not depend on it.

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
