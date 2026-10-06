---
summary: "Accounting-only retained width disposition candidate; targeted green, independent review/full gate pending."
type: "validation"
---

# Explicit interrupted ordinary-restore disposition

**Historical checkpoint, blocked by independent review.** The tests below missed four defects:
visible-but-unsynced canonical admission, late live-state veto after publication, unsynced equal
Store reuse, and missing host cwd binding. In particular the rename/durability claim below was
incorrect; its passing fault proxy did not prove admission safety. Do not treat this checkpoint as
qualification. See [review corrections](2026-09-20--restore-disposition-review-corrections.md).

## Implemented candidate

The existing binary now routes `restore-disposition inspect|propose|approve|apply`. This is a
separate, closed disposition-only authority using generic Store artifacts, not reconstruction or
reconciliation approval. It supports only the reviewed nine-record v3 pending positive integral
`.0` width family. The shared structural reader validates original private paths, directory identity,
contiguous chain, semantic references and raw-byte manifests. Every earlier record remains subject
to strict semantics. The old width prediction is checked as historical data, never normalized into
an executable action; other pending/legacy/unknown shapes remain blocked.

Original interrupted accounting must match original synchronous CLI-result and exit files sharing
one explicitly selected private witness directory, which may be outside the original Store. File and
directory inode pins bind these original paths without moving them. The original Store remains
independently mandatory. The result is exactly the original receipt fields plus source/receipt digests; exit
bytes are exactly `2\n`. Exact pending command, `CalledProcessError` and exit 2 must agree. Approval
requires exact digest confirmation, literal `operator-accepted-partial` and explicit attestation that
these are the original synchronously collected invocation files. Trust includes installed client
behavior and operator-controlled witness provenance, not kernel-signed authentication. Hashes alone
cannot prove original execution or an old IPC worker's exit; a timeout cannot qualify.

Proposal binds fresh double-read topology/focus, unique original window/host association, protected
current process pins, retained pidfds and the launched boot/PID/start/image/argv evidence. Legitimate
post-incident geometry changes are allowed before proposal; fresh state is not historical preservation
proof. Approval/apply independently require that exact current baseline and unexpired TTL (at most
900 seconds). Raw diagnostic titles/environments stay in their original artifacts, referenced only.

Under one existing exclusive flock, apply revalidates, durably consumes approval, persists the partial
receipt, stages/fsyncs one canonical record, then renames and directory-syncs it. Before rename, partial
or orphan staging stays fenced. Surviving canonical bytes after rename constitute the commit even if
final directory sync/response is lost; absent/damaged history never grants admission. Committed replay
is historical and effect-free. No prior byte is edited, no failed intent becomes observed, and neither
fence removal nor success-pointer projection occurs. The receipt preserves unproved completion,
unresolved pending outcome, unproved native session and no retry authority. Original rows/effects
remain referenced; original-source restore replay exits 2 with empty invocation effects and separate
historical effects. A different source may obtain only its own ordinary fresh-baseline admission.

## Observed verification

- Initial regression RED against the previous candidate: **2 failed**, demonstrating absent CLI
  and inability to structurally read the exact retained invalid-width prefix.
- Added **103 disposition tests**, including the handwritten nine-record/action oracle, explicit CLI
  lifecycle, original-byte preservation, ordinary replay exit 2, new-source admission, no pointer
  update, wrong/missing/substituted witnesses, unsupported history, raw/inode/Store drift, stale
  topology/focus/compositor/process/image/argv, controller/surplus/unknown ownership, expiry and flock.
- Persistence tests cover partial writes, proposal/approval file and directory fsync failures,
  consumption/receipt/staging boundaries, all seven apply fsync points, canonical rename and lost
  response. Inspection rejects all explicit write/create/fsync attempts in its test.
- Six default-process cases use actual Linux `/proc`, pidfds and a cooperative compiled ELF with
  fabricated Niri/history: positive approval/commit; exit, path replacement, unknown protected PID,
  running exec and running argv changes. The fixture exits on pipe EOF, with no kill cleanup.
  Effect tripwires guard feature execution after fixture setup.
- First broad targeted run: **413 passed / 5 failed**. Four exposed a changed existing lock error
  diagnostic; its original wording was restored. One exposed a test observation during fixture exec;
  the fixture now waits for stable changed argv without treating the transient as positive proof.
- Final targeted command below: **431 passed in 188.25 seconds**, no skips or xfails. This includes
  expiry during the last original-byte revalidation, before approval persistence/consumption, and
  original controller witnesses outside the Store with independently pinned directory identity.
- Full-source Ruff check and formatting check passed; portable-source/privacy and Python 3.11 syntax
  checks passed. Changed modules remain below 500 lines and new test files below 1000.

```sh
UV_OFFLINE=1 .venv/bin/pytest -q tests/test_restore_*.py tests/test_reopen.py
.venv/bin/ruff check src tests scripts/check-portability.py scripts/ci/package-smoke.py \
  scripts/demo-desktop.py scripts/release-notes.py
.venv/bin/ruff format --check src tests scripts/check-portability.py scripts/ci/package-smoke.py \
  scripts/demo-desktop.py scripts/release-notes.py
.venv/bin/python scripts/check-portability.py
```

## Limits and next gates

No actual native query, desktop action, private history/witness read, fence disposition, commit,
deployment, login installation change or release occurred. Existing candidate changes were retained.
The actual original witness files and native host behavior have not been verified by this work.
Synthetic ELF evidence is not Ghostty ownership/session usability or native desktop qualification.
The prior 981-test full gate precedes these source changes; **full CI was deliberately not run**.

Next: independent source/adversarial review, then one full isolated gate. Only the separately
authorized operator may validate original native witnesses and execute the exact reviewed disposition,
followed by a separately approved fresh canary. A refusal is not permission to rewrite evidence or
manually remove a fence. Ordinary `restore --apply` remains an explicit manual action, not newly
protected by an automatic exact-plan approval argument. No native completion claim is made here.
