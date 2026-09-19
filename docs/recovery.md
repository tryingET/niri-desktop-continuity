---
summary: "Beyond reopening: blocked restart proposals, loss-bounded reconstruction, additive reopening, resolution and layout reorder."
read_when:
  - "You plan a restart, a reconstruction or a layout change rather than reopening a saved desktop."
---

# Planning, reconstruction and resolution

Reopening a saved desktop after a reboot (`restore`) is covered in the [README](../README.md) and
[usage](usage.md#save-and-reopen). This page gathers the separate, explicitly approved paths for
windows that are still *running*. They share one CLI, immutable plans and exact-digest approvals;
most are experimental and some need a separately owned adapter that does not ship here.
Command details, safety rules and evidence limits are in [usage](usage.md).

## Proposals are not permissions

```sh
niri-desktop-continuity plan <snapshot-digest> --intent restart --window-id <id>
niri-desktop-continuity preview <plan-digest> --kind plans
```

The proposal shows selection, observed shared-process impact and blockers. All restart/migration
proposals remain blocked because exact application checkpoint/restart adapters are unavailable.
Application versions remain unknown during capture: discovered binaries are **never executed**.
A version selector with no matching known version selects nothing, not a guessed application.

## Loss-bounded saved-conversation reconstruction

A separate **loss-bounded saved-conversation reconstruction** orchestration path is available
through the same CLI: `plan --intent reconstruct --adapter-config`, exact loss/omission/utility-limit approval,
`reconstruct`, and `verify`/`inspect --kind reconstruction`. It requires a separately reviewed,
owner-established pinned internal adapter profile; **no real machine adapter ships here**.
This public suite exercises fabricated installed-console-script workflows. Separately owned
Pi/Claude/Codex/btop support is **implemented and independently reviewed with isolated integration
tests; native desktop qualification unperformed**. Generic public coverage is not native certification.
See the [coverage table](usage.md#conversationtool-coverage-and-evidence-limits). Exact restart/migration
remain blocked; reconstruction never claims prior memory, drafts, scrollback or hidden-tab order.
See [usage](usage.md#loss-bounded-reconstruction-separate-from-exact-restart) and the
[internal protocol](project/2026-09-06-integrated-reconstruction-protocol.md).
Protocol v2 additionally accounts for btop utilities without inventing conversations or running-image
pins. Unobservable capability-bearing btop images require exact separate limit acceptance. Reviewed
recovery code stays pinned; installed OS/Pi/Jiti is an explicitly owner-trusted application platform,
not a total dependency capsule. V1 history remains readable without upgrading its authority.
Implementation is not live-effect approval or independent safety certification.

## Additive saved-session reopening

For saved conversations whose old windows/processes are already gone, the same lifecycle also
supports `plan --intent reconstruct --mode additive --saved-set <digest> --adapter-config ...`.
A separately pinned owner profile resolves the private saved set, distinguishes missing from
already-present refs, and may launch each missing ref once while preserving current windows/focus.
It cannot shut down processes/services or move existing windows; already-present-only sets perform
zero effects. Exact native identity, expiry, approval and replay gates remain. Layout/tab and memory
reconstruction are not claimed. See [additive reopening](usage.md#additive-saved-session-reopening).
Reviewed owner profiles can project desired shared-window groups/member sequence and privacy-safe
admission reasons into the existing plan/preview/inspect flow. This is requested grouping, not exact
original tab-order proof or a way to move sessions already open in separate windows. Failed attempts
can leave new windows/focus changes: inspect first, never erase evidence or retry unresolved history.
This portable contract is covered by fabricated installed-CLI tests, not live native qualification.

## Abandonment and profile transition (resolution)

The CLI also has an experimental **abandonment and same-ledger profile-transition** lifecycle.
It preserves failed history and never grants replay or native effects. Candidate admission and
activation require separate exact approvals. Exact retained owner-history decoding is implemented
and tested with fabricated historical-byte specimens; **native qualification remains unperformed**.
Unsupported history blocks, and the separate prospective test codec cannot manufacture historical
authority. The observer/native producer and machine integration remain separately owned and are
not shipped here. See the checkout-only [resolution contract](project/resolution-protocol.md)
for supported history, settlement decisions and limits.

## Within-workspace column reorder

There is an experimental, separately approved **within-workspace single-tile column reorder**
path. It uses immutable plans, expiring exact-digest approvals, per-compositor writer exclusion,
fresh-state checks, one-use consumption and effect receipts. Cross-workspace moves, resizing,
multi-tile topology and cross-session restoration are unsupported. Niri's focus-then-move IPC is
not atomic; concurrent user input remains a risk. See
[usage and safety](usage.md#experimental-layout-only-actions).
