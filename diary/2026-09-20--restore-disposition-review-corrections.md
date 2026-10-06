---
summary: "Four disposition review defects corrected offline; 552 targeted passes, independent re-review pending."
type: "validation"
---

# Interrupted disposition — review corrections

## Reconciled execution evidence

Independent review blocked the first disposition candidate. Its green tests did not establish
safe durability admission, final validation ordering, reused Store artifact durability or host cwd
coherence. The earlier diary is now explicitly marked as a rejected checkpoint, not qualification.

An interrupted engineering invocation was reconciled against retained files and test logs before
continuing. The runtime changes, regression tests and earlier completed runs were present; later
Store/corruption tests and documentation were not yet verified, and this diary was absent. No uncertain
command was assumed completed. Existing unrelated candidate changes were preserved.

## Implemented corrections

1. **Durability is not visibility.** `restore_history.load` performs pure structural/semantic
   validation under flock; it cannot grant admission. `admit` validates the entire retained special
   flow, then establishes fresh successful file and parent-directory barriers on the exact validated
   original records/artifacts/witnesses, plan, approval, consumption, receipt and canonical record.
   Descriptors bind file and directory identities, private ownership/modes, raw hashes and lengths;
   identity/content changes fail. The full evidence is revalidated after barriers. `require_clear`,
   Attempt admission/original-source replay and disposition replay all use this path under the same
   exclusive compositor flock. Failed barriers never grant authority.

   After a lost canonical-directory sync or response, later successful barriers may establish
   durability **now** for the SAME already-approved/consumed valid canonical record. This does not
   prove the original apply succeeded. Recovery does not append, consume again, reapprove, observe
   native state, update a pointer, rewrite bytes or introduce acknowledgement markers. Missing or
   corrupt evidence cannot be repaired into authority. Pure inspection never fsyncs and can report
   canonical validation with durability/admission unestablished.

2. **Veto before publication.** Live validation follows the last potentially slow original-history
   and dependency reads/barriers, before approval persistence or approval consumption. Apply repeats
   history/dependency validation after receipt persistence, then stages/fsyncs its canonical record
   and checks live processes, topology, cwd and expiry immediately before rename. The context manager
   only releases held proofs; it does not issue a fresh-state veto after canonical publication.
   A prepublication failure after consumption retains the fence, without cleanup or retry authority.
   State/process changes after publication are new state, not retroactive refusal of accounting.

3. **Equal artifacts still need durability.** `Store.put` validates an existing equal private
   immutable artifact, then fsyncs its identity-checked file and parent directory before returning.
   This closes reuse after an earlier failed file/directory fsync. Partial JSON, substituted inodes,
   unsafe files, symlinks and changed content are refused, not rewritten. Directly read disposition
   plan/approval/consumption/receipt dependencies also receive explicit durability barriers.

4. **Actual host cwd is required.** `restore_disposition_cwd.Directory` holds the recorded cwd FD,
   rechecks its pathname against the bootstrap device/inode, and compares the launched host's actual
   `/proc/PID/cwd` identity and path. The plan records both directory identity observations. Live
   validation surrounds observation and precedes publication, with pidfds and cwd FD held throughout.
   A renamed/replaced original directory, process chdir, missing or unreadable host cwd blocks.
   No inference or policy change for a utility child's cwd is introduced. Earlier candidate plans
   lacking cwd evidence must be proposed anew, never silently upgraded.

Strict executable width grammar remains unchanged. The old `.0` intent is historical data only;
no failed effect gains an observation, completion or retry. Partial receipts and original replay
still exit 2 with empty invocation effects, separate historical effects and no success-pointer update.

## Test evidence

- Genuine initial RED against the first candidate: **21 failed in 11.67s**. Eight final-history drift
  cases, eight persistent canonical file/directory admission cases, one equal-approval reuse case,
  and four real-process cwd cases exposed the four defects.
- Focused corrected runtime: **27 passed in 18.01s** (stdout evidence, not a retained log file).
- Intermediate disposition run: **123 passed / 2 failed in 71.02s**. The two failures were obsolete
  numeric fsync-count expectations after adding dependency barriers. The old test also incorrectly
  blessed visible publication after final-directory failure. It was replaced with named persistent
  barrier faults requiring blocked admission until later successful validated durability.
- Intermediate broader run: **192 passed in 89.51s**. Later added Store/corruption tests were not
  covered by that checkpoint.
- Resume verification: **43 passed / 3 failed in 24.11s**. Three newly added tests mistakenly applied
  an evidence-fsync tripwire to unrelated default writer-lock directory setup. The corrected tests
  assert no evidence barrier before validation through the existing read-only flock and then also
  assert default writer admission remains blocked. No runtime code was changed for that test issue.
- Corrected review/Store tests: **46 passed in 28.26s**.
- Final targeted gate: **552 passed in 275.71s**, no skips or xfails. This includes **149 disposition
  and Store-barrier cases**, related restore/reopen tests and selected generic Store/recovery consumers.
- Full-source Ruff and formatting checks, portable-source/privacy and Python 3.11 syntax checks,
  plus `git diff --check`, passed. Runtime modules remain below 500 lines; tests below 1000.

The new independently handwritten pre-fix nine-record transcript does not call the runtime executor,
planner or geometry predictor to construct its preparation, association, moves or old width intent.
It uses fabricated values and an independent JSON digest helper; the complete explicit flow passes
without rewriting original bytes. Other regressions cover all admission/replay paths, dependencies,
barrier-time substitutions, partial writes, expiry, read-only inspection, real pidfd exit during the
last historical read, staged-persistence drift, and absence of post-publication fresh vetoes. Real
cooperative ELF tests exercise host cwd replacement/chdir, image/argv changes and process exit.
Fixtures exit cooperatively on pipe EOF; they are not Ghostty or native desktop proof.

Final targeted command:

```sh
UV_OFFLINE=1 .venv/bin/pytest -q tests/test_restore_*.py tests/test_reopen.py tests/test_core.py \
  tests/test_recovery_backend.py tests/test_recovery_execute_faults.py tests/test_recovery_hardening.py
.venv/bin/ruff check src tests scripts/check-portability.py scripts/ci/package-smoke.py \
  scripts/demo-desktop.py scripts/release-notes.py
.venv/bin/ruff format --check src tests scripts/check-portability.py scripts/ci/package-smoke.py \
  scripts/demo-desktop.py scripts/release-notes.py
.venv/bin/python scripts/check-portability.py
git diff --check
```

## Boundaries and next gate

The final live-check-to-publication/fsync interval is not atomic against process exit or external
activity. No frozen native-state claim is made. Filesystem tests inject failures/interleavings;
physical power-loss behavior and adversarial same-UID races are not qualified. Successful later
barriers establish current durability, not authenticity of operator-imported historical witnesses.
Installed client behavior and original witness provenance remain explicit operator trust premises.

No actual native query/action, private witness/history read, live fence change, AK mutation, commit,
deployment, canonical installation change or full CI occurred. Only the isolated candidate and
fabricated test state were changed. Source corrections do not dispose of the retained live attempt.
Independent re-review/reproduction must precede the parent's full isolated gate and any separately
approved native disposition/canary. Do not manually edit or remove a fence after a refusal.
