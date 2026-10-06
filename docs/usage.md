---
summary: "CLI usage, privacy and experimental layout-action safety."
read_when:
  - "You capture a desktop or consider approving a layout change."
---

# Usage and safety

## Read-only commands

`capture` observes Niri outputs, workspaces, windows and layer surfaces, plus same-user process
identity metadata. It samples twice and rejects coherence if topology, focus, active workspace,
layer list or window-host process identity changes. This is bounded observation, not an atomic
snapshot across processes. It never reads terminal contents or browser profiles, and never
executes a discovered application binary. Session identity comes from Claude Code's per-PID
registry and Pi's presence files; a Claude transcript is scanned only for its title records, to
match sessions to windows. Niri IPC is the only invoked runtime CLI.

`capture --include-titles` stores private window labels and session titles. Default labels
identify applications and window IDs only, and reopen recipes carry no session title. Other
process metadata, including recipe command lines, can still be sensitive. Keep captures private.

### Save selected windows

`capture --window-id INT [--window-id INT ...]` saves exactly the named windows from that
same capture. IDs must be nonnegative integers, unique and present in that observation; invalid,
duplicate or absent selections fail before any snapshot or pointer is written. IDs are local to
that compositor observation, not persistent application identities. No app/title guessing occurs.
Without the flag, full-capture snapshot and result semantics are unchanged.

Selection preserves source window order, complete selected recipes (including `reopen.extra`),
and **all** supporting outputs, workspaces, layers, identities, process observations, inventory,
warnings and capture timestamps. Readiness is recomputed for the saved windows; source coherence
is retained. Selected snapshots and capture results add exactly this metadata object:
`"capture_selection": {"kind": "window-ids", "window_ids": [30], "observed_window_count": 3}`
(fabricated IDs/count). IDs in this field are sorted; window records remain in source order.
The immutable snapshot digest binds this provenance and the saved content. It does not reference
an unsaved full snapshot or claim complete desktop coverage. Even selecting every observed ID
explicitly retains this provenance. The ordinary model, Store and restore planner consume it;
full-desktop `verify` still compares all windows and can report unselected live windows as extras.

**Selection is not selective probing.** Capture still reads whole-desktop/process/session metadata,
including potential Claude transcript-title reads before redaction. Unselected process metadata
remains in the saved snapshot. `--include-titles` controls retention, not those reads. Selection is
neither a privacy sandbox nor resource/lock isolation.

These are ordinary Store snapshots: they promote `latest-observed` and, when ready,
`last-display-valid`. Default preview/restore in that Store will therefore use the selected snapshot.
Use an explicitly reviewed private Store for qualification, not the login capture Store; never
hand-edit generated snapshots or receipts. A different `--state-root` does **not** bypass the
canonical compositor fence on apply or resolve an earlier ambiguous attempt.

One selected window may carry extra-tab recipes and produce multiple planned entries. Before any
one-window canary, review the exact saved recipes and immutable dry-run receipt: require **exactly
one planned entry, no extras**, a harmless admitted Ghostty recipe and the intended destination.
Dry-run records placement only; it does not certify admission, executable availability or safety.
Do not drop extras to manufacture a one-launch plan. The proposed sequence, not permission to run it:

1. With separately authorized whole-desktop read access, use the existing candidate CLI:
   `niri-desktop-continuity --state-root <private-store> capture --window-id <observed-id>`.
2. Retain its exact `snapshot_digest`; run
   `niri-desktop-continuity --state-root <same-store> restore <snapshot-digest>` without `--apply`.
   Review the returned `receipt_digest` and immutable `receipts/<receipt-digest>.json`, the saved
   recipe (including extras), protected baseline, compacted workspace/name intent and host admission.
3. Stop for separate explicit operator approval of any effectful canary. Neither capture nor dry-run
   grants it. No canary, native qualification, login deployment or retry is authorized here.

### Preview and verification

`preview [digest]` renders a stored snapshot offline (default: the latest capture); `--kind plans`
renders current and desired maps plus admission blockers and always needs a digest. A snapshot
preview labels every tile with how it reopens and adds an **After a reboot** ledger: per window
(and per extra tab session) whether `restore --apply` would reopen it, its kind, exact command and
directory, or the reason it will not. Recipes are shown as recorded, not re-verified. HTML and SVG escape all observed strings and contain no scripts,
network assets or working approval buttons. Preview has no application-control backend.

`verify <desired-snapshot-digest>` compares against a fresh live observation. Exit 0 means its
observable layout predicates match. Exit 2 means mismatch, unavailable output, invalid identity
or another refusal. Focus is reported separately. Native application state stays unverified.
`history --kind snapshots|plans|receipts --limit 20` lists artifact identities, not private labels.

## Save and reopen

`capture` attaches a reopen recipe to every window (`reopen`): kind `app` (process argv and cwd),
`claude` (`claude --resume <id>` inside the same terminal, from `~/.claude/sessions/<pid>.json`),
`pi` (the presence directory's `resumeArgv`), `command` (the terminal's leaf process), `shell`
(terminal in the same directory) or `unknown` with a reason. Only Ghostty is read as a terminal:
the terminal recipes use its `--working-directory` and `-e`, so other terminals are recorded as
`app` (their own command line, nothing that ran inside). Titles are used only to match a
session to its window when one terminal process owns several windows; they, and the session
titles used for matching, are not stored unless `--include-titles` is given. Sessions found in extra tabs of a window become `extra` recipes.

`restore [digest]` prints a recorded-recipe placement plan (default: latest capture). Dry-run and
preview do not certify executable availability or ownership. **The disposition and association
corrections passed bounded independent review and full isolated CI (1,671 tests, builds and
installed-wheel smoke). A fresh native attempt opened a host but stopped before association and
width handling; it remains unresolved. Synthetic tests do not authorize live use, retry or cleanup.**

`--apply` admits only shell/command/declared/Pi/Claude recipes for a controlled fresh Ghostty ELF,
with existing explicit cwd and literal command tails. It forces non-single-instance Wayland and
discards custom configuration after defaults have been read. Scripts, wrappers, conflicting flags,
missing directories and all general application/browser recipes are unsupported before launch.
A browser's zero-launch result is not working browser restoration evidence.

One attempt holds the compositor flock through every bootstrap, exec permit, process/window proof,
layout observation and terminal commit. Niri launches the installed bootstrap; the application does
not inherit the service/control/writer descriptors. A retained pidfd and running-image/argv/environment
proof, plus a fresh unique Niri PID-associated window, authorize only the trusted fresh Ghostty
connection contract. No label fallback, forwarded host, protected overlap or surplus output is accepted.
The no-fork/no-forward/no-connection-transfer/no-unobserved-exec host behavior remains an explicit
trust assumption, not general PID causality or native session usability proof.

The association baseline includes all queried outputs, including unchanged disabled outputs without
workspaces. It is bound from the incoming coherent capture and checked on every subsequent read,
not only association. New outputs, malformed metadata or disabled metadata drift stop the attempt;
error fallback does not consume a later recovered reply after inventory failure. Missing inventory
or output-query transport refuses before launch.
Output/object ordering is ignored, but field presence, array order and other observed metadata are
conservatively pinned. Strict window workspace references now intentionally reject boolean/float
aliases of integer IDs. Cleanup failures still surface, but no longer skip later proof closes or
lock exit; standalone ownership transfer closes orphan descriptors if context exit fails. These are
offline review corrections, not native qualification or permission to retry.

The subsequent offline association correction allows a maximum of three narrowly eligible split
samples while awaiting the launched host: original windows and workspace metadata are unchanged,
except the focused workspace references one new missing window ID. This grants no association or
effect. The same pending reference must resolve in one strict whole sample with exact host proof;
observed drift, foreign output, disappearance, query failure or deadline expiry stops without retry.
The deadline is shared by queries and all process checks, not renewed by polling. A slow association
write may remain in history after timeout; it never permits layout or success. Held original directory,
pathname and launched-host cwd are checked, not a child utility's cwd or session usability. Other
reads/decoders stay strict. Polling cannot detect events entirely between observations, and blocking
kernel/storage calls can delay refusal. This correction has no native qualification or deployment
approval; the earlier full-CI result does not qualify the changed bytes.

Owned singleton columns are ordered after protected groups, consumed only from the exact immediate
right singleton, and sized using measured window/tile decoration differences. Floating positions use
fresh measured positions and signed fractional relative deltas. Sequential placement lets Niri
materialize normal trailing-empty destinations from a single empty login workspace. Logical targets
remain bound to stable workspace IDs across permitted empty cleanup and per-output reindexing,
including an optional empty workspace above the first. Cross-workspace insertion follows the active
column; moving the freshly focused donor with `--focus false` preserves source-workspace focus.
There is no arbitrary workspace-creation feature and source monitor affinity is not restored.
One consistent recorded width governs an entire restored column; unspecified members report
`inherited-column`. Conflicting recorded widths refuse before launch. If none was recorded, preserve
the admitted seed width and let other members inherit it. Separate extra-tab columns preserve their
own fresh widths. Missing floating positions retain measured native conversion positions.
Requested dimensions start `requested-pending`; verified equality, not intent, grants
`requested-observed`. Inherited widths also remain pending until verified. Floating positions use the
current output's physical-pixel grid, with `requested-quantized-observed` when rounding changes the
saved position. Unknown scale cannot supply a position proof. Saved tile height is not restored.
Requested sizing with unknown decorations is blocked unless the requested size is already observed.
A resize requires a positive decimal integer window-width token whose measured-decoration
reconstruction equals the requested tile width exactly and survives Niri's size floor and tile clamp.
Fractional requested widths are not silently rounded: representable decorated widths are admitted;
others stop before that seed's placement actions, after launch/association. Column donors inherit the
seed's observed width without requiring an independent resize. Native constraints/scale-dependent
size differences can still fail strict postconditions. Floating-position grammar and pixel-grid
policy are separate and unchanged. Old decimal-width intents never become executable; the narrow
explicit accounting-only disposition below does not migrate or observe them as successful.
Names change only on admitted nonprotected workspaces without conflicting existing names. Unknown
geometry, mixed cohorts, late unowned arrivals, lost proof or failed postconditions stop all later
effects, including focus cleanup. The original focus is restored only after successful observations.
Index-addressed moves and names revalidate the intended stable ID/output/index after durable intent;
observed drift stops without dispatch, rewriting or retry. **Remain idle:** the final check and Niri
action remain non-atomic, even against automatic workspace cleanup. Strict postconditions still apply.

Canonical append-only history is independent of `--state-root` and XDG settings. Original Store
identity, full source-derived plan, coherent baseline, pre-effect classifications, controlled literal
specs, associations, intents and observations are retained. The closed v3 history binds current output
scales and workspace references, and validates action
predictions against observations, exact observed effect accounting, and terminal geometry against
both the durable final observation and requested topology/dimension coverage. Unsupported/already-open
classifications cannot be invented at terminal time. Historical validation does not reprobe old host
files or working directories. Older candidate history formats remain blocked, not silently upgraded. Missing/corrupt/orphan/legacy
records or unresolved effects block every cooperating effectful writer, across sources and Stores.
Do not remove markers, retry, relaunch or clean up uncertainty. The accounting-only disposition
below supports one exact historical family; there is no generic resolve command.
A valid terminal releases future writer admission without erasing history. Exact completed-source
replay returns historical accounting, with zero effects and no fresh native verification; another
source needs a fresh protected baseline. Final receipt is durable before canonical terminal, then
`last-reopened` is projected only for full success. A missing pointer never grants replay authority.
Fully accounted unsupported entries yield `partial` (exit 2), distinct from `interrupted`; neither
updates the success pointer. Resume-argv matches are skipped as already open, not newly verified
sessions. Exit 0 means complete supported placement/accounting, not recovered memory or usability.

### Restore read-query policy

Built-in Windows, Workspaces and Version reads retry only `Popen` construction raising exact
`BlockingIOError` with `EAGAIN`: at most three constructions per invocation, with 0.05/0.10-second
backoffs. Outputs remains a mandatory single-dispatch read. Communication, decoding, custom queries,
bootstrap/spawn and layout actions are never retried; IPC clients are never timeout-killed or
implicitly cleaned up. Each eligible read has one ten-second aggregate admission/observation budget,
intersected with an already-forwarded association deadline; construction, backoff and decoding count.
This rejects late observations, not a hard wall-clock return bound. Existing association polling and
its separate failure-diagnostic read may each invoke another query; three is not a whole-restore cap.
Selected custom methods retain the existing `deadline=` association contract, without signature
fallback. Post-action reads still do not share their postcondition loop's deadline; this policy does
not repair that existing limit. Exhaustion leaves the original error and unresolved ownership/history,
not a new launch or permission to retry effects. Historical native EAGAIN causation and desktop/session
usability remain unproved; source or synthetic results do not authorize deployment or live effects.

### Protected-dimension interruption evidence

A new protected-size refusal may include `first_rejected_observation` in its interrupted receipt.
It is the first refused state's bounded **dimensions-only** projection, with original-baseline
size differences, proof phase and timing of the existing windows/workspaces/outputs queries.
`final_observation` remains a separate, later diagnostic read: it may show the same change,
recovery, a different change or unavailable data. Never substitute it for the rejected sample.

The optional closed `restore-protected-dimensions.v1` field uses `null` for unavailable pairs or
query/clock timing; `{"schema":"restore-protected-dimensions.v1","unavailable":true}` means the
first retention failed or exceeded bounds. No fullscreen, work-area or layer data is inferred.
Absence on old receipts or other refusal paths is not evidence of unchanged dimensions.
The [exact schema and limits](architecture.md#protected-dimension-refusal-diagnostics) also explain
classification and reused-baseline timing limits. Monotonic query intervals correlate local reads,
not compositor causality or wall time. Titles, command lines and paths are not in this new projection.

This field supplies diagnostics only. The original refusal, unresolved history, effect accounting
and no-retry/no-cleanup boundary remain. Successful/legacy receipts are unchanged, and neither
existing `restore-disposition` family admits these new protected-dimension interruptions.
Offline tests do not authorize live effects or deployment.

### Explicit retained partial disposition (candidate; independent review pending)

Update: bounded independent re-review and full isolated CI have passed. This heading is retained
for existing links. One separately approved native width-failure disposition was independently
verified as partial accounting, not restored geometry or native success. A later unassociated-host
interruption remains fenced and is outside this narrow disposition family.

`restore-disposition` is **accounting only**, not repair, cancellation, retry or native success.
It supports only a strict nine-record v3 ordinary attempt ending in the reviewed pre-fix positive
integral `.0` column-width intent, following one owned-column move. All earlier records must pass
strict current semantics. Unknown shapes, old v1/v2, follow-up observations, generic pending actions,
timeouts, missing witnesses, unknown ownership and process/controller overlap remain blocked.
The strict executable integer grammar is unchanged.

Use the **original Store**, with two original private single-link witness files sharing one private
directory. That directory may be outside the Store (for example, the original controller's private
qualification directory); both file and directory inode identities are bound, without moving files:

- `--client-result`: the original synchronous CLI result JSON object, exactly the immutable
  interrupted receipt's fields plus `snapshot_digest` and `receipt_digest`. No envelope, extra keys
  or reconstructed result is accepted. It must identify `CalledProcessError` for the exact pending
  `niri msg action set-column-width ...` command with exit status 2.
- `--client-exit`: the original synchronously collected invocation exit file, exactly `2\n`.

The operator must attest original provenance, not manufacture files from the receipt. Hashes and
inode/path/owner checks detect subsequent changes; they **do not independently authenticate the
historical exit**. Trust includes the installed Niri/client and the operator-controlled original
witness collection. Flock alone and a receipt error string are insufficient. This is not kernel-signed
proof, a sandbox against the account owner, or proof of a usable native session.

```sh
niri-desktop-continuity --state-root <original-store> restore-disposition inspect <attempt> \
  --interrupted-receipt <digest> --client-result <original-result-path> --client-exit <original-exit-path>
niri-desktop-continuity --state-root <original-store> restore-disposition propose <attempt> \
  --interrupted-receipt <digest> --client-result <original-result-path> --client-exit <original-exit-path> --ttl 300
# Review the exact private plans/<plan-digest>.json and its declared uncertainty first.
niri-desktop-continuity --state-root <original-store> restore-disposition approve <plan-digest> \
  --confirm <same-plan-digest> --accept operator-accepted-partial --attest-client-returned
niri-desktop-continuity --state-root <original-store> restore-disposition apply <approval-digest>
```

Inspection performs no filesystem writes; proposal only adds a private plan, never approval or a
canonical record. All stages use the existing exclusive flock without granting desktop action
capability. Proposal/approval/apply bind fresh coherent topology and focus, the unique originally
associated host, live pidfds/start pins, its recorded ELF and literal argv, held recorded directory
identity and the launched host's actual `/proc/PID/cwd`, and every currently protected window's process
identity. This does not inspect or infer a utility child's cwd. Missing, moved or replaced host cwd
blocks; earlier candidate disposition plans without this binding must be proposed anew. They query topology/process metadata, not saved-session
registries or profile payloads. Current geometry may legitimately differ from the incident;
fresh capture does **not** prove historical preservation. Stay idle during review/approval/apply;
any bound-state drift requires a new proposal. Plans expire within 900 seconds (default 300).

Apply revalidates independently, durably consumes the approval, persists a disposition receipt,
and commits one `operator-disposition` record. It never changes prior bytes, observes the failed
intent as successful, unlinks the fence, updates `last-reopened`, launches, moves or kills anything.
Accounting failures before canonical commit stay fenced; no automatic retry or cleanup occurs.
A durable staged record is renamed to the canonical record, but **visibility is not directory
durability**. Pure history loading and inspection confer no admission. Every accepting path, including
ordinary writer admission, original-source replay and disposition replay, validates the entire special
flow and establishes fresh successful file and parent-directory barriers on exact identity-checked
artifacts, dependencies and the canonical record under the same flock. A failed barrier blocks.

Later successful barriers on that same already-approved, consumed, valid canonical record can establish
durability **now**, without new approval, consumption, append or native observation. This is historical
partial accounting recovery, not proof that the original apply succeeded. Missing, damaged or replaced
bound evidence is refused, never repaired. Read-only inspection may report `canonical=validated` and
`durability=unestablished`; it does not fsync or claim admission. Missing/partial/staged-only history
remains blocked. Existing equal Store artifacts also require fresh file/directory fsync on reuse.

Mandatory live checks follow the last slow history/dependency reads, before approval persistence or
consumption, and repeat after staging persistence immediately before canonical publication. Expiry is
rechecked after those reads. Pidfds and the cwd descriptor stay held through publication. There is no
post-publication fresh-state veto that reports refusal after publishing authority: subsequent live
changes are new state. The last check through publication/fsync is still **non-atomic** against process
exit or external desktop activity; this command has no desktop effects and does not claim otherwise.

The receipt remains `operator-accepted-partial`, with `historical_completion=unproved`,
`pending_outcome=unresolved`, `native_session=not-proved`, `disposition_effects=[]` and
`retry_authorized=false`. **Apply and historical original-source restore replay exit 2**, not success.
Original-source replay reports invocation `effects=[]`, separate `historical_effects`, and the original
row receipt reference. Only fully valid canonical disposition releases future writer admission.
Keep all original evidence files: removing or changing them blocks admission again.

A different source still needs its own freshly observed baseline and separately authorized operator
action. Ordinary `restore --apply` remains the existing explicit manual apply surface; it does not gain
an automatic exact-digest approval argument from disposition. Native qualification and login deployment
remain separate approval gates. Do not manually edit history to bypass a refusal.

`restore --at-login` first waits up to 60 s for Niri and does nothing when the saved identity
matches the running compositor instance. `autostart --enable [--interval-minutes N]` installs
`niri-desktop-continuity-capture.timer` and `niri-desktop-continuity-restore.service` (wanted by
`graphical-session.target`); `autostart --disable` removes them; `autostart` alone reports status.
Recipes are launch commands, not process memory: unsaved drafts, scrollback and hidden tab order
are not recovered, and applications restore their own content.

What is never replayed: a Claude process without a registry entry (for example one started from
inside another Claude session, which inherits its child-session environment and keeps no
transcript) is `unknown` (`claude-session-unregistered`); its command line is often an opening
prompt, and running it again would start the same work over. A window reported by the X11 bridge
`xwayland-satellite` is `unknown` (`xwayland-client`). An AppImage program running from its
temporary `.mount_*` directory is recorded as the AppImage file that serves the mount (the
runtime's own launch path when absolute), or `unknown` (`appimage-mount-unresolved`).
Chromium and Electron overwrite their command line with one space-joined process title. It is
split where a leading part names a real program file (arguments that contained spaces cannot be
recovered; the preview marks such commands), otherwise `unknown` (`process-title-unresolved`).

`declare --pid PID [--cwd DIR] [--label TEXT] -- COMMAND [ARG...]` tells the next captures how to
reopen the terminal surface that runs PID when nothing can resume it, e.g. a fresh session started
from a handoff: `declare --pid 4242 -- claude "Continue from docs/handoff.md"`. The declaration
lives in the per-boot runtime directory (`/run/user/<uid>/niri-desktop-continuity-declared`, 0600),
is pinned to the process start time so a reused pid never matches, applies only when no native
Claude or Pi session is found, and becomes kind `declared`. `declare --pid PID --clear` removes it.

## Planning

`plan <snapshot-digest>` defaults to review-only inspection. Optional `--window-id`, `--pid`,
`--app-id` and `--version` filters intersect. Unknown or conflicting selectors fail closed.
`--intent restart|migrate` always yields a blocked proposal. `--replacement` hashes an exact
executable but does not run it. Observed descendant/cgroup impact is not a promise of exhaustive
kill scope or process recoverability. Plans expire after 300 seconds by default (`--ttl 1..900`).
Historical previews remain readable after expiry; their presence is not renewed authority.

## Experimental layout-only actions

**Not a frozen-terminal recovery procedure. Not proven by a read-only map.** The first effect
model supports only same-workspace single-tile column reorder on one output, preserving the
focus at admission. It does not restore historical focus from a different checkpoint.

```sh
niri-desktop-continuity plan <current-snapshot> --intent reconcile --desired <desired-snapshot>
niri-desktop-continuity preview <plan-digest> --kind plans
# Only after the operator reviews the exact plan and agrees to the limitations:
niri-desktop-continuity approve <plan-digest> --confirm <same-full-plan-digest>
niri-desktop-continuity reconcile <approval-digest> --apply --acknowledge-non-atomic-focus
```

The operator must remain idle during the operation. Niri has no atomic focus-plus-move/CAS
transaction: external input in the final IPC gap can move an unintended column. This is a real
residual risk, not eliminated by the acknowledgment flag. Unsupported topology is blocked before
any action. An already-matching plan performs no IPC effects.

All cooperating tool instances share an exclusive nonblocking lock under `/run/user/<uid>`,
keyed by boot and compositor socket device/inode, independent of `--state-root`. This does not
lock out other Niri clients or the user. Validation occurs inside the lock, approval is consumed
once, expiry is checked before each dispatch, and each effect intent is durably recorded first.
A no-effect acknowledgment is not success. Observed drift or a timeout stops without replay or
rollback. A crash may leave only an effect-indeterminate intent and consumed marker. Re-observe
and make a new decision; never delete the marker to replay an unknown operation.

No live mutation canary is implied by the synthetic test suite. The public tool makes no claim
of tested cross-version app restart, guaranteed focus safety, or restoration on another machine.

## Loss-bounded reconstruction (separate from exact restart)

The existing CLI implements orchestration for `saved-conversations-v1` over exact protocol v1/v2; **no real machine adapter
ships with this package and no live reconstruction is certified by its tests**. The machine owner
must first establish and independently review a pinned profile/internal endpoint according to the
[protocol](project/2026-09-06-integrated-reconstruction-protocol.md). An absent profile reports
`reconstruction-adapter-unavailable`; an absent explicit config reports
`reconstruction-adapter-config-required`. Other untrusted adapter/config/protocol diagnostics are
suppressed in favor of a static refusal. No shell/argv, native payload or environment is exported.

```sh
niri-desktop-continuity plan <snapshot> --intent reconstruct --adapter-config <private-config>
niri-desktop-continuity preview <plan> --kind plans
# Only after reviewing the exact plan and accepting the named losses:
niri-desktop-continuity approve <plan> --confirm <plan> --accept-losses saved-conversations-v1
niri-desktop-continuity reconstruct <approval> --apply --acknowledge-non-atomic-focus
# The returned attempt_digest is the approval digest, not the receipt digest:
niri-desktop-continuity inspect <attempt> --kind reconstruction
niri-desktop-continuity verify <attempt> --kind reconstruction
```

These commands describe the interface, **not permission to run a live operation**. Plan and approve
perform fresh read-only observations. Capture/preview remain inert with respect to adapter effects.
The preview's desired map is explicitly the original target topology; replacement window identities,
native surfaces and recovery groups are not predicted by this renderer. Its admission warnings show
sanitized native coverage, losses and any required omission digests. Read the typed plan/proof rather
than interpreting the schematic as native recovery evidence.

Memory, drafts, scrollback, shell state and hidden-tab order are unsupported losses. Unknown ownership,
unknown native process identity or controller/protected overlap always blocks. The only image
unobservability exception is the separately typed v2 btop utility below. An otherwise fully
identified owned process without a native session association also blocks by default. If the operator
separately chooses to omit **only that exact association**, make a fresh proposal with
`plan ... --omit-association <process-pin-digest>` (candidate digests are returned by planning), then
repeat each with `approve ... --accept-omission <same-process-pin-digest>` in addition to the exact
plan and baseline loss contract. No specific omission has been accepted by this documentation.
Boot/birth/image drift invalidates the typed decision; generic loss acceptance never substitutes.

### Conversation/tool coverage and evidence limits

Pi, Claude and Codex saved conversations use the **same existing CLI and opaque `session_refs`**;
btop is a separate v2 utility, never a conversation. No public v3, app-name field, second CLI,
machine import or new runtime dependency is needed. The separately owned private `machine.v3`
implementation uses unchanged public v1/v2. Interface capacity alone is not native compatibility.

| Surface | Current evidence / status | Not established |
|---|---|---|
| Generic public v1/v2 contract | Fabricated three-reference workflows; distinct refs stay distinct, same-ref processes deduplicate, consistent renaming preserves results; every native predicate and malformed/missing proof tested; installed CLI/socket subprocess smoke | Which tool produced a ref, app-kind namespacing, native identity semantics or live recovery |
| Pi machine integration | Separately owned implementation/review and isolated installed-CLI tests; owner-reported real Pi resume with fabricated sessions in a filesystem/network sandbox | Ghostty/service/provider/live layout proof or production qualification |
| btop machine integration | Separately owned observed-image/capability-limit implementation and isolated machine-boundary tests | Native btop/Ghostty reconstruction or live effects |
| Claude + Codex machine integration | **Implemented and independently reviewed with isolated integration tests; native desktop qualification unperformed**. App-kind-scoped equal-ID separation, same-kind deduplication and actual native-shape callback/log fixtures verified | Permanent real-native opt-in tests, clean Claude compatibility, full native/runtime certification or production qualification |

The machine implementation's isolated tests verify tool-kind-scoped identities, same-app
deduplication and distinct-app separation, including equal native IDs across apps. Independent
file/cwd/runtime/bootstrap/surface/causal-window evidence remains mandatory for each admitted ref.
Public tests deliberately do not implement or certify that producer mapping. They cannot infer
semantic conversation identity, completeness or provider usability from a digest or six booleans.
Unknown or unproved helpers remain blockers. No native/full-coverage or live-effect approval follows.

### Recorded validation and qualification limits

The following supplied review/validation results are separate evidence sets, not additive totals:

- Independent public review accepted the bounded fixture/documentation slice: 161 tests, including
  70 new cases, and eight installed-console smoke cases. The parent actual checkout subsequently
  passed `UV_OFFLINE=1 just ci`: 343 tests, a new build and installed-console smoke.
- Independent machine final review accepted six native fixes after 187 application tests and eight
  independent cases. Recorded machine source/full validation passed 686 tests with five native Pi
  skips. The later combined parent run was still running at this documentation update; no newer
  total or completion is claimed.
- Real Claude/Codex sandbox prototypes supplied genuine callback, file-descriptor and initialization
  evidence. The Claude prototype could not exit cleanly because of a faulty harness; one isolated
  sandbox remains held pending operator cleanup approval. No cleanup is authorized here, and this
  is not clean Claude compatibility evidence. No permanent real Claude/Codex native opt-in tests
  were delivered.

No production profile, global installation, live Ghostty/service/layout qualification or full
native/runtime certification is established. The public package ships no machine adapter. These
results do not validate this final documentation edit; build/strict-docs validation remains with
the parent. Checkout-only chronology: `diary/2026-09-07--implementation-multitool-recovery.md`
(deliberately excluded from the sdist; not a shipped evidence dependency).

### V2 btop utilities and trusted application platform

A v2 owner profile explicitly declares an installed owner-trusted application platform and critical
file pins. The Python recovery-control implementation stays closed/source checked; exhaustive
OS/ELF/Pi/Jiti dependency closure is not required. This is neither a sandbox nor native proof.

V2 plans separately list btop utilities and `owned_utilities` / `image_unobservable_utilities`
coverage. An ordinary observed image requires a real running-process Pin. A capability-btop identity
must explicitly use a null image Pin, retained installed-file/capabilities/birth/parent/argv/cgroup
corroboration and a sole owned leaf; unknown ownership or overlap still blocks. It is not a Pi
session and must never be represented by a fabricated conversation or association omission.

For each capability-btop utility_ref shown by the plan warning, approval additionally requires
`--accept-utility-limit <utility_ref>`. Repeat this flag for each exact limit. Missing, duplicate,
extra or wrong-branch limits refuse. Baseline losses and any native omissions must also be accepted
separately. No specific limit is accepted by these instructions.

All utility proof predicates remain mandatory. Limits cap success at
`verified-with-accepted-limitations`, even when native omissions also exist. Receipts retain both
decisions, expose `overall_image_coverage_complete=false` and `image_coverage=observable-subset-only`,
and never claim complete overall native coverage. Image dimensions cover only observable images.
A utility-only selection can succeed with `saved_conversations_recovered=0`; it does not recover
a conversation. Interrupted history cannot be upgraded by fresh proof. Synthetic v1/v2 installed
console workflows are tested; separately owned machine integration has isolated evidence as above,
not native btop/Ghostty reconstruction or live-effect proof.

### Canonical accounting and execution

Canonical attempts live in the fixed owner's ledger, not the chosen CLI state root. Approval is
consumed once with a durable canonical prepare/consume/ready fence. Copies, different state roots
and re-approval cannot bypass it. Partial/indeterminate canonical history and incomplete legacy
accounting block new reconstruction. Historical v1 evidence stays inspectable after an owner profile
upgrade, with its original schema/profile identity and adapter accounting unknown; this does not
authorize cross-profile execution or reconcile old accounting. Do not delete markers, change profiles/ledgers or invent a nonce
to retry. A crash after intent may leave stopped processes or unresolved children; no automatic
rollback, service repair, signal, launch fallback or cleanup is authorized.

The worker receives one expiring effect permit at a time and retains the writer lock if its parent
disconnects. It must cease new effects on disconnect/lease expiry; only already-dispatched observation
and durable recording remain permitted. The CLI never timeout-kills the worker and waits for exit,
so a defective worker can block rather than silently release exclusion. Launched applications must
not inherit the lock. The operator must remain idle; Niri focus-plus-move is still non-atomic.

Final receipts separately report native file/cwd/runtime/bootstrap/surface/causal ownership, new
images, old-tree exit, services, layout/focus, labels/holds and protected preservation. Complete
mandatory proof yields `verified`; accepted association omissions cap it at
`verified-with-accepted-omissions`, always with incomplete overall native coverage. Neither means
provider usability, semantic completeness, human acceptance or memory restoration. Partial or
indeterminate execution exits 2. Fresh verification never upgrades an interrupted effect history
or modifies its canonical terminal marker. In v2, `saved_conversations_recovered` is an aggregate
complete-proof/history count: a partial attempt reports zero even if other native records pass,
not a per-conversation salvage tally. Missing native records yield partial; missing utility records
violate the exact proof set and make execution indeterminate. Inspect reports history/accounting,
not fresh native proof.
Default `verify <snapshot>` and ordinary layout reconciliation retain their existing meaning.

## Additive saved-session reopening

Use this distinct mode when the selected saved conversations remain available but their old
windows/processes are gone. It does **not** restart Ghostty, reconstruct tabs, move existing windows,
or demand invented old-process, shutdown or service proofs. The public package ships no native
adapter; its fabricated tests are not live machine qualification.

```sh
niri-desktop-continuity plan <current-snapshot> --intent reconstruct --mode additive \
  --saved-set <owner-private-saved-set-digest> --adapter-config <private-config>
niri-desktop-continuity preview <plan> --kind plans
niri-desktop-continuity approve <plan> --confirm <plan> --accept-losses saved-conversations-v1
niri-desktop-continuity reconstruct <approval> --apply --acknowledge-non-atomic-focus
niri-desktop-continuity verify <attempt> --kind reconstruction
niri-desktop-continuity inspect <attempt> --kind reconstruction
```

The existing lifecycle uses the separately versioned `desktop-continuity.saved-reopen.v1` owner
profile. `--mode replacement` remains the default and preserves v1/v2 behavior. Additive mode requires
an exact saved-set digest, never arbitrary argv, transcript content or a native path. The owner
resolves that private immutable set and proves each exact saved file/ID/cwd, native runtime/bootstrap,
and current absence or existing native association (including recovered descendants). Live-window,
PID, app/version and association-omission selectors are not accepted in this mode. All currently
observed windows are protected; no former PID or window must be fabricated.

Planning reports selected, missing, already-present and unresolved saved-conversation counts.
The offline HTML preview includes a saved-scope ledger with the complete saved-set digest, each
exact opaque ref and its disposition/count. It distinguishes a missing-session plan from a zero-launch
already-present plan without exposing native paths or adapter-private manifests. The map remains a
schematic; the scope ledger, not inferred tabs or unchanged topology, identifies planned launches.
When a reviewed owner profile projects desired grouping, the same preview shows each proposed
shared-window group, exact member creation sequence and grouping provenance. Plan JSON, receipts
and inspect retain those closed projections. **Desired creation order is not captured native tab
order**, and shared-window recovery does not certify tab-versus-split structure. Older observations
without grouping remain explicitly ungrouped/unknown; no retrospective grouping is inferred.
Privacy-safe per-ref reason codes and a separate capacity diagnostic explain refusals when supplied;
no native paths, exception text or transcripts are displayed.

Unresolved refs block that exact selection rather than silently disappear or acquire loss approval.
A revised owner-selected subset requires a new saved-set digest, plan and exact approval; it cannot
bypass unresolved effects. At execution the coordinator permits each admitted missing ref once, then
one restoration of the admitted focus. Shutdown, service, layout, duplicate launch, already-present
launch and unbound refs are refused before a permit. An already-present-only set performs **zero
effects** but still consumes its approval and receives fresh native verification. No-op evidence does
not authorize replay.

`verified` requires all selected native identities, pinned images, focus and protected preservation.
For already-present refs the ownership/image proofs concern those current processes, not fictitious
new launches. `saved_conversations_restored` counts admitted missing refs only after complete proof
and intact history; partial/indeterminate history reports zero, not a per-ref salvage tally.
`saved_conversations_already_present` and `saved_conversations_unresolved` retain admission counts;
they are not fresh success claims if overall native verification fails. Layout is explicitly not
reconstructed: normal tiling insertion can change geometry, and uncertain former tabs remain an
owner-declared loss, not guessed tab targets. Memory, drafts, scrollback and provider usability stay
unsupported/unverified. Ordinary capture/preview never launches anything.

All exact profile/source pins, native identity checks, expiry, focus revalidation, per-compositor
writer exclusion, canonical prepare/consume/ready fencing and no-retry/no-cleanup rules remain.
A correlated pending-effect heartbeat can keep a cooperative long preflight alive without granting
another effect or extending the absolute plan expiry. The five-second liveness lease still expires
on missed/late replies; disconnect or expiry cancels new effects without killing applications.

**Failed does not mean nothing happened:** partial recovery can leave new windows open and focus
changed. Inspect the canonical attempt before any separately reviewed operator reconciliation.
Never delete receipts/the ledger, change state roots or retry to hide unresolved effects. Additive
inspect includes this guidance. There is no automatic repair or cleanup. This mode cannot regroup
already-open sessions across windows; do not close them merely to make them eligible for reopening.

The portable contract permits at most 256 selected refs and 255 missing refs (one effect slot is
reserved for focus). Private adapters may have smaller persistent-store capacities; exhaustion
requires owner-managed retention/disposition, not automatic pruning. The portable tool remains
Python 3.11+; a private adapter can require a different pinned interpreter and must disclose it.
This is a bounded source-owned recovery mode, not a general application launcher or a workaround
for the independent requirements of destructive reconstruction. Native qualification is separate.

## Exited associated-shell disposition v3 (offline candidate)

This accounting-only family is explicitly selected with
`restore-disposition inspect|propose --family associated-shell-protected-dimensions-interrupted`.
It is **not native qualification or permission to run these commands against a real desktop**.
Omitting `--family` still selects v1; the existing unassociated-host family remains v2.

Only the exact original ten-record associated-shell attempt with two observed actions (workspace
transfer, then owned-window focus), requested width already observed, and the original seven-field
`ValueError: protected dimensions changed` receipt is eligible. Original synchronous result/exit
files remain mandatory. A new diagnostic-bearing receipt is explicitly **ineligible**, including
an unavailable `first_rejected_observation`. Never strip fields, reconstruct witnesses, normalize
the old source or substitute a later diagnostic sample for the unretained rejected sample.

Inspection is historical only: no socket/process/namespace observation, fsync, artifact creation
or admission. Proposal needs the continuing authenticated peer, validated process/namespace scope,
all current windows protected, and exact ESRCH at pidfd_open for the old PID. The original associated
window ID and every window reporting that PID must be absent. A live replacement at the same numeric
PID refuses, even with another start time. New live proofs require Linux little-endian x86_64
GNU LP64, a conventional stable upstream-compatible release >=7.2.6, libc statx UNIQUE and active
pidfd namespace ioctls. Unsupported ABI/release/interfaces or uncertain scope refuses without fallback.
Genuine self coordinates establish the proc/caller namespace relation without opening init namespaces;
a nested matching PID scope is supported. Same-user process ownership and complete non-init ancestry
remain required. The release check is compatibility under platform trust, not build attestation.

Old-method v3 plans remain historical only: exact completed replay/inspection still works, including
expired completions. An unfinished old-method approval/apply refuses before live proof or new
accounting writes. Nothing rewrites old bytes, changes `init_pid_namespace` meaning or clears a fence.
New plans emit only `native-niri-continuing-peer-procfs-self-pidfd-esrch.v2`, with the unique mount
ID and derived PID namespace pin. Both the original init method and procfs-self `.v1` are historical
only, with unchanged meaning and bytes. Their completed histories remain replayable together.

Caller, continuing peer and every protected-window owner always need full namespace proofs, acquired
before any ancestor-only row. Other ancestors need genuine singleton PID coordinates, four matching
UIDs, stable boot/start/parent, held-directory provenance and live pidfds, but no target namespace
ioctl. Their user namespace and executable continuity are not asserted. A capability-bearing manager
can therefore qualify as an exclusion-only ancestor while still refusing as a peer or protected
owner. This is not a permission fallback: inaccessible required metadata, failed full-role proofs,
unknown/incomplete ancestry and all observed drift still refuse. Weak proofs never gain full roles;
a later cohort change requires refusal, not promotion. No manager's other sessions become owned.
Current ELF checking uses guarded root-relative lookups; transient privileged substitution between
checks is an accepted sampling limit, not proved impossible. Readonly opens are not a sandbox.
See [scope and image limits](architecture.md#exited-associated-shell-v3-offline-candidate).

Proposal prints the complete fixed `platform` object and its `platform_digest`. Inspect the private
plan, including current peer image/scope and all limitations, before any separately authorized step:

```sh
niri-desktop-continuity --state-root <original-store> restore-disposition approve <plan-digest> \
  --confirm <same-plan-digest> --accept operator-accepted-partial --attest-client-returned \
  --ack-platform <exact-platform-digest-from-that-plan>
```

The acknowledgement is specifically same-lifetime native endpoint/PID scope, without serving
handover, namespace-changing proxy or PID translation. This is accepted historical platform trust,
not measured historical executable continuity. Current ELF/Version checks do not attest a build;
SO_PEERCRED does not identify a different task serving an inherited socket. Both original CLI-version
members remain immutable source evidence, but only `compositor` is compared to direct IPC Version.

Apply and exact completed replay return `operator-accepted-partial`, exit 2, invocation effects `[]`,
separate two-action historical effects, unproved historical completion/preservation and unresolved
outcome. No original source is relaunched or promoted to `last-reopened`. Direct replay needs the
original Store; ordinary old-source replay also works from a different Store without current native
proof. Each live stage proves its own caller. A changed baseline requires a new proposal/approval;
no retry can bypass a `.pending` stage or consumed attempt. No process is killed or window moved.
A distinct source remains an independent ordinary restore, not newly authorized by this accounting.

## Disposition failure boundary (offline prerequisite candidate)

`restore-disposition` parser, cancellation and result-output failures now use one bounded ASCII
JSON line on stderr, with `error="restore-disposition-refused"` and a closed
`restore-accounting-failure.v1` diagnostic. Private argument values and exception text are not
printed. Explicit help still exits 0. Runtime cancellation never becomes success: KeyboardInterrupt
exits 130; SystemExit preserves only actual integers 1–255 (otherwise 1); conflicting cancellation
codes give 1. Untagged IO failures exit 2; unclassified failures exit 1. A failed diagnostic write
has no raw fallback or retry. Other commands retain their existing error boundary.

This is **not retained-pending completion support**. Both failed-preparation family selectors are
still rejected; a retained `.pending` still blocks admission. Detailed preconsumption phase tags,
complete guard-site reason tagging, stream/barrier teardown coverage and the S/F plus S2/F2 protocol
remain unimplemented. The original restore witness is unchanged. Coarse diagnostics do not supply
eligible failed-client evidence, prove linkage or grant authority.

Existing v2/v3 canonical rename attempts report `publication="unknown"` until admission verifies the
carried staged inode at the canonical name. V1 conservatively remains unknown after rename because
it has no such carried staged-inode check. Publication is not durability. Postcommit output/cleanup
failure emits no usable successful result and never rolls back; an explicit exact historical replay
still performs the existing barriers without a new native proof. No live use or deployment follows.

## Privacy and trust model

Private files are content-addressed and integrity checked, with distinct latest-observed,
last-display-valid and last-layout-verified pointers. Headless observations cannot promote a
stronger pointer. Existing permissive/symlink state roots are refused, not silently repaired.
Same-user malicious code can author local plans and approvals; these are accidental-use safety
gates, not authentication against an attacker who already controls your user account.


## Exec-observed-unassociated disposition v2 (offline candidate)

The corrected implementation passed independent code review, full isolated CI (1,671 tests),
and installed-wheel lifecycle checks on Python 3.13/3.14. These instructions are not live-use,
retry, cleanup or deployment authorization. The original nine-record width procedure above remains
v1 when `--family` is absent. For the distinct five-record exec-observed/unassociated family, select
it explicitly on the existing commands:

```sh
niri-desktop-continuity --state-root <original-store> restore-disposition inspect <attempt> \
  --family exec-observed-unassociated --interrupted-receipt <original-receipt> \
  --client-result <original-private-result-file> --client-exit <original-private-exit-file>
niri-desktop-continuity --state-root <original-store> restore-disposition propose <attempt> \
  --family exec-observed-unassociated --interrupted-receipt <original-receipt> \
  --client-result <original-private-result-file> --client-exit <original-private-exit-file>
```

Inspection reads existing evidence only: family eligibility is not fresh ownership, durability,
approval or admission. Proposal requires fresh coherent current topology and real process/image/
argv/cwd evidence. Review its exact plan digest; the existing `approve` command requires
`--confirm <that-plan-digest> --accept operator-accepted-partial --attest-client-returned`.
The attestation is specifically that the witness files are original synchronous invocation output,
not reconstructed evidence; it is not kernel authentication. Existing `apply <approval-digest>`
consumes that approval and appends only partial accounting. It never dispatches a Niri action,
launches/terminates an application, updates `last-reopened`, retries or verifies native sessions.

Only the exact original `ValueError: foreign active window`, exit `2\n`, one `launch-indeterminate`
row with its original process-only receipt, and empty-effect witness qualify. The earlier unreviewed
`process-exec-observed` row is not an alias; never rewrite real witness files to make them eligible. Other errors, associations/layout/terminal claims, extra entries,
source/attempt/launch-identity reuse, uncertain ownership and protected/controller overlap refuse.
Historical launch identity is `(boot_id, pid, start_ticks)`, not PID alone. The exact partial labels
are `historical_association="not-recorded"` and `outcome="unresolved"`.
Current protected geometry may legitimately differ from the historical baseline; this is not
proof that it was preserved. The current topology is not a full physical-output inventory.

Successful accounting, its historical replay and completed-partial inspection report partial
status/exit 2, never original restore success. Active inspection/proposal/approval return exit 0
without granting restore execution. Original-source ordinary restore remains a historical partial
replay with empty invocation effects; a new ordinary operation needs its own fresh baseline and
separate explicit operator action. An incomplete `.pending`/consumed flow stays fenced, even with
a different approval; do not delete, rebuild or "repair" its evidence.

Persisted historical pins are immutable expectations. Latest generated artifacts without such a
pin have semantic/cross-reference protection plus FIRST-observation identity protection during each
validation/barrier interval—not independently proved creation-time inodes across invocations.
A later plan binds them as observed then. Owner-controlled append-only state and trusted app/operator
workflow are the terminal trust boundary, not a signed log against a malicious account owner.
See [architecture](architecture.md#exec-observed-unassociated-v2-offline-verified)
for exact closure, staging, identity and per-pass resource limits.
