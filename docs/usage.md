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

## Privacy and trust model

Private files are content-addressed and integrity checked, with distinct latest-observed,
last-display-valid and last-layout-verified pointers. Headless observations cannot promote a
stronger pointer. Existing permissive/symlink state roots are refused, not silently repaired.
Same-user malicious code can author local plans and approvals; these are accidental-use safety
gates, not authentication against an attacker who already controls your user account.
