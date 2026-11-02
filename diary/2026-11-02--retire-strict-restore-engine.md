---
summary: "The strict restore engine, its history reader and restore-disposition are gone; any record it left now refuses effects by existing."
read_when:
  - "Changing effect admission, operation_lock or how restore --apply treats earlier attempts."
  - "Writing the 0.3.0 changelog."
type: "diary"
---

# The strict restore engine is gone

`restore` has run through `reopen` since the small restorer landed. The strict controlled-Ghostty
engine stayed in the package only because something still imported it: the `LiveDesktop` transport
lived in its module, and effect admission validated its history. The owner decided on full
retirement rather than keeping a read-only history reader, given what the records actually are.

## What changes for users

For the 0.3.0 changelog:

- **Removed: `restore-disposition`** with its stages `inspect`, `propose`, `approve` and `apply`.
  It accounted for interrupted attempts of the strict engine. No release up to 0.1.2 contained it.
  0.2.1 contains it, but there it has nothing to work on, because nothing can create such an attempt.
- **Changed: a strict record now always refuses `restore --apply`, `reconcile` and `reconstruct`**
  for that compositor, with exit 2. The first two say "a strict restore record fences this
  compositor until it restarts; no action taken"; `reconstruct` keeps its one generic refusal.
  Before, a completed record let a different source proceed, and the same source returned its
  recorded result. Neither happens any more.
- **Changed: `restore --apply` also checks the compositor its source came from**, not only the
  running one.
- **Changed wording:** a stored artifact with a duplicate field or a non-finite number now says
  "duplicate JSON field" or "nonfinite JSON number" instead of naming a bootstrap frame. It is
  still the same refusal.

Nothing else moves: `capture`, `preview`, `restore` without `--apply`, `restore --apply` on a clear
compositor, `autostart`, `declare`, `hook`, planning and reconstruction behave as before.

## Why a record can be refused unread

A record is `/run/user/<uid>/niri-desktop-continuity-locks/<digest>.restore`, or a legacy `.permit`
beside it, and the digest names the boot ID and the compositor socket's device and inode. So a
record is on tmpfs, and even a surviving file would stop being consulted by a new boot or a new
compositor instance. The only writer was `restore_attempt.Attempt`, reachable only through
`restore.restore()` and `restore_producer.produce`, and nothing called either. No release wrote a
record. The plans and receipts of an old attempt do survive a reboot in the state directory: they
stay there as plain JSON that nothing consults, and retention still respects what they name.

With that, a validating reader protects nothing that a plain "does it exist" does not. The reader
cost 70 of the package's 84 modules in effect admission's import closure, including the executor
itself, because history validation rederived plans through `restore.plan_restore`.

## Removed and kept

Removed: the executor (`restore.py`, `restore_execute`, `restore_producer`, `restore_bootstrap`,
`restore_host`, `restore_layout`, `restore_attempt`), the history reader (`restore_history`,
`restore_records`, `restore_plan`, `restore_retained`, `restore_routing`, `restore_reader`,
`restore_reader_io`, `restore_state`, `restore_geometry`, `restore_dimensions`,
`restore_observation`, `restore_failure_observation`), the disposition families
(`restore_disposition*`, `restore_exited*`) and `restore_wire`. That is 41 modules and 71 test
files, with `docs/project/restore-ownership.md`, the candidate's design document. The 0.2.1 release
commit still has all of it.

Kept, and why:

- `LiveDesktop`, now in `live_desktop.py`: `reopen` needs it. Its caller deadline and `outputs` read
  went, because only the strict engine used them.
- `operation_lock` with `require_clear` and `fence_path`: `restore --apply`, `reconcile` and
  `reconstruct` all rely on them. The fence keeps the name existing records were given, pinned by
  handwritten canonical JSON. Nothing reads, repairs or removes a record.
- The source check in `reopen`. The lock covers the running compositor, so a source attempted on an
  earlier compositor in the same boot would launch again without it. Deleting the old lookup would
  have opened that quietly; it was the one replay refusal that was not already part of the lock.
- Strict JSON and exact-byte evidence reads, now in `store.py`, which always needed them.
- `prune_snapshots` still scanning the runtime directory, so a record keeps protecting its snapshot.

## How it was checked

Callers: an import graph of the package, a search for dynamic imports, and a search of the workspace
and user units, with no hit outside the package. The units run only `restore --apply --at-login` and
`capture`.

Tests: 2,059 in-process tests of the retired suites ran under a line tracer against the surviving
tests. Of the lines in kept modules they reached, 62 had no other test. 43 of those were code being
removed. The other 19 were real: `probe.compositor_identity`, which keys every writer lock, was
covered only by retiring tests, and so were `probe.query` and one readiness reason. They now have
their own oracles, as do `LiveDesktop.action` and the evidence read that moved. The tracer does not
see subprocess tests, so the installed-wheel and native suites were left out of that comparison.

Porting found one real difference between the planners. `plan_restore` sent every window without a
recipe to the spare workspace; `reopen.plan` keeps it on its saved workspace when that workspace has
a known place, and only otherwise sends it to the spare. The tests now pin what ships.

The evidence for the records themselves is from one machine, which had none. Another machine was
not inspected. If it holds one, `restore --apply` refuses there until its compositor restarts, and
that is the intended failure.

The commits run in an order that keeps each one green: pin retained behaviour first, retire the
suites while source is untouched, switch admission, remove the command, delete the modules.
