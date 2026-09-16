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
snapshot across processes. It never reads terminal contents, browser profiles or session logs,
and never executes a discovered application binary. Niri IPC is the only invoked runtime CLI.

`capture --include-titles` stores private window labels. Default labels identify applications
and window IDs only. Other process metadata can still be sensitive. Keep all captures private.

`preview <digest>` renders stored snapshots offline; `--kind plans` renders current and desired
maps plus admission blockers. HTML and SVG escape all observed strings and contain no scripts,
network assets or working approval buttons. Preview has no application-control backend.

`verify <desired-snapshot-digest>` compares against a fresh live observation. Exit 0 means its
observable layout predicates match. Exit 2 means mismatch, unavailable output, invalid identity
or another refusal. Focus is reported separately. Native application state stays unverified.
`history --kind snapshots|plans|receipts --limit 20` lists artifact identities, not private labels.

## Save and reopen

`capture` attaches a reopen recipe to every window (`reopen`): kind `app` (process argv and cwd),
`claude` (`claude --resume <id>` inside the same terminal, from `~/.claude/sessions/<pid>.json`),
`pi` (the presence directory's `resumeArgv`), `command` (the terminal's leaf process), `shell`
(terminal in the same directory) or `unknown` with a reason. Titles are used only to match a
session to its window when one terminal process owns several windows; they are not stored unless
`--include-titles` is given. Sessions found in extra tabs of a window become `extra` recipes.

`restore [digest]` builds a placement plan from a snapshot (default: the latest capture) and prints
it. `--apply` executes it: for each entry `niri msg action spawn`, wait for the new window (up to
`--spawn-timeout`, default 25 s), `move-window-to-workspace --focus false`, then per workspace
`move-column-to-index`, `set-column-width` and `consume-window-into-column` in saved order.
Saved workspace names are re-applied. Windows present before the run are protected: never
moved, and reopened columns are placed after them. Sessions already open (same resume argv) are
skipped. Exit 0 means every entry was placed; exit 2 means a partial result, recorded in the
receipt (`history --kind receipts`). The operator should stay idle during the run: column
arrangement uses focus and Niri has no atomic focus-plus-move.

`restore --at-login` first waits up to 60 s for Niri and does nothing when the saved identity
matches the running compositor instance. `autostart --enable [--interval-minutes N]` installs
`niri-desktop-continuity-capture.timer` and `niri-desktop-continuity-restore.service` (wanted by
`graphical-session.target`); `autostart --disable` removes them; `autostart` alone reports status.
Recipes are launch commands, not process memory: unsaved drafts, scrollback and hidden tab order
are not recovered, and applications restore their own content.

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

## Privacy and trust model

Private files are content-addressed and integrity checked, with distinct latest-observed,
last-display-valid and last-layout-verified pointers. Headless observations cannot promote a
stronger pointer. Existing permissive/symlink state roots are refused, not silently repaired.
Same-user malicious code can author local plans and approvals; these are accidental-use safety
gates, not authentication against an attacker who already controls your user account.
