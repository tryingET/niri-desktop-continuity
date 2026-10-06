---
summary: "Isolated restore-ownership candidate stopped at an out-of-scope worktree validation defect."
read_when:
  - "You resume the launch-bound ordinary restore candidate."
type: "diary"
---

# Restore ownership preflight

Read the candidate contributor contract, local engineering policy, README, architecture, proposed
ownership design, and the affected runtime/tests. No runtime source changes were made.

## Observed validation

- Created and synchronized the candidate's own virtual environment with offline frozen dependencies.
  Used a separate scratch cache seeded from relevant cached development/build packages; did not use
  or mutate the canonical installation or its environment.
- Ran `UV_OFFLINE=1 just ci`, with complete output retained outside the repository in scratch.
- Lint passed; formatting passed for 76 files.
- Pytest: **684 passed in 578.97 seconds**, including the 15 copied login contract cases.
- Full CI exit status: **1**. Portable-source validation reported
  `.git: hardcoded user home path`.
- The package build and installed-console smoke were not reached. This is not a passing full gate.

## Scope stop

The source scanner excludes `.git` directories, but adds the ordinary `.git` pointer file used by
worktrees to its source inventory. That metadata contains an absolute checkout-management path.
Fixing the scanner and its regression tests, or changing Git metadata, is outside the exact allowed
paths. No validation bypass or metadata rewrite was attempted.

Stopped before implementation and RED/GREEN regression work. The existing passing tests do not prove
launch ownership, crash fencing, truthful accounting or protected-cohort layout safety. The design
remains proposed; no supported positive milestone has been implemented or qualified.

The two copied parent validation files were preserved byte-for-byte. No task-state changes, commits,
peer launches, live desktop calls, native application launches, process termination, service changes,
deployment or canonical-runtime edits occurred.

## Disposition

The controller supplied an independent local clone with a real Git directory, no hardlinks and its
own offline environment. The unchanged source scanner passes there. No scanner, suppression or
Git-metadata workaround was needed. The established full baseline was not repeated before coding.

Implementation resumed with genuine outcome-based RED tests. A real process-producer/accounting
slice now exists; ordinary restore/layout integration is still incomplete. See
[implementation record](2026-09-19--restore-producer-slice.md) for evidence and limits. The earlier
stop above records the original worktree preflight, not the current clone's validation status.
