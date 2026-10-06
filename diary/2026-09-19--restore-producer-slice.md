---
summary: "Real launch-process producer and durable fencing slice; ordinary restore integration remains red."
read_when:
  - "You review or resume the bounded restore-ownership candidate."
type: "diary"
---

# Restore process-producer slice

## Decision and scope

After the independent clone resolved the earlier worktree/scanner issue, implementation resumed
without repeating the full baseline. Deliver the independently tested producer/accounting slice;
do not claim completion of ordinary restore or reduce its layout capability to make tests pass.
The installed runtime and its environment were not modified. No commits or deployment were made.

## Historical slice record

The implementation and run counts below describe the initial slice handoff. Independent review
subsequently found environment-evidence normalization, numeric-overflow decoding, FIFO blocking and
read-only lock admission defects. The [review-fix record](2026-09-19--restore-producer-review-fixes.md)
supersedes those mechanisms and records the narrow corrections; this initial green subset was not
proof that these later counterexamples passed.

## Implemented at initial handoff

- Controlled Ghostty host admission for shell, command, declared, Pi and Claude recipes: exact
  fresh-host flags, explicit existing cwd, literal command tail, unsupported host options refused.
  Custom Ghostty configuration is discarded; default configuration is still read before discard.
- Short-lived installed Python bootstrap through Niri, with closed bounded Unix framing, absolute
  monotonic expiry, peer credentials, coordinator/process start pins, pidfds and exact binding.
- Mandatory same-process ELF descriptor exec; no child fallback. All inherited control descriptors
  close before the host. IPC-client wait has no automatic kill-on-timeout behavior.
- Real running-image/hash/device/inode, boot/PID/start, argv and sanitized environment observations.
  Portable Python builds lacking the os binding use libc's pidfd_open, not a PID-only substitute.
  The real handshake tests exposed Python locale coercion: binding now uses the Niri-provided
  initial environment as observed through the pinned helper's proc entry on both sides.
- Durable original-Store receipts plus canonical compositor bootstrap and exec-permit intent files.
  File and parent-directory fsync precede dispatch/permit bytes. Shared writer admission rejects
  retained, partial, corrupt and orphan markers across Store roots. Dry-run planning does not
  acquire effect exclusion; copied login-skip contracts remain unchanged.

The producer returns **process evidence only**. Every dispatched attempt remains unresolved and
fenced, even after process observation or exit. No success pointer, settlement, retry, rollback,
resolve command or process termination was added. Native-session and placement dimensions remain
explicitly unproved. Environment payloads are not written to receipts.

## Exact validation evidence

Full logs are retained in external scratch and supplied with the review handoff, not copied into
public source. All tests use fabricated state and private lock directories.

| Run | Result |
| --- | --- |
| Initial ordinary-executor outcome RED, before runtime mutation | 5 failed in 0.84 seconds |
| Initial producer admission/protocol contracts | 13 failed in 0.66 seconds (modules absent) |
| Final targeted producer/protocol + unchanged reopen/login suite | 94 passed in 28.43 seconds |
| `UV_OFFLINE=1 just ci` | exit 1: 6 failed, 732 passed in 554.64 seconds |
| Separate unchanged source/entrypoint smoke, wheel/sdist build, installed-console smoke | exit 0 |

The full gate's six failures are deliberately retained, unsuppressed integration regressions:
same-label unowned arrival, different-label fallback, browser timeout relaunch, missing interrupted
entries, partial success pointer, and dispatch without durable intent. The sixth regression was
added during slice development; the first five were genuine pre-implementation RED. The old
executor is not repaired by green producer tests. Packaging checks were run separately because
full CI stops at the failing tests; they are not presented as a passing full gate.

Forty-eight new passing slice tests cover controlled admission, literal argv/cwd, service-control
environment stripping, frame bounds/duplicate fields/nonfinite values, expiry, credentials,
start-pin changes, real pidfds/image validation, script refusal, dispatch routing, no timeout kill,
real bootstrap/exec, descriptor closure, syscall-order intent durability, cross-Store fencing,
no-peer timeout, partial/wrong/possibly-delivered permits, persistence errors, compositor replacement
and corrupt/orphan markers. The remaining 46 targeted cases are unchanged reopen/login tests.

The strongest producer positives launch the installed bootstrap from the candidate's own environment
and exec a separately compiled bounded ELF fixture. Its handwritten report oracle observes the
actual PID, literal argv, cwd, environment values and open FDs. No fake callback supplies ownership.
The fixture never opens a desktop connection or native profile and exits on its own. A local C
compiler is optional for development but required to run this group; no ELF test was skipped in
these reported runs. The separate installed-wheel smoke covers existing console workflows and
packaging; it does not independently qualify Ghostty or the new producer's native behavior.

At this initial handoff, both copied parent validation files retained their original byte-for-byte
hashes. The later review dispatch authorizes a candidate-only login fixture signature adaptation;
the copied original diary remains unchanged. No test in this initial run contacted
real Niri, a real lock directory, Ghostty, native profiles or services; no processes were killed.

## Not integrated / required next work

Ordinary restore still uses the old spawn/label-detection/layout executor. No positive owned-window
placement or protected-cohort topology oracle has been delivered in this slice. Full-plan records,
unsupported entries, surplus/missing outputs, grouped producers, cross-Store completed replay,
settlement ordering, workspace-name/final-focus accounting and owned column/floating reconstruction
remain work. No native browser support or native session-resumption proof is claimed.

Pidfds detect permanent exit, not exec generations. Current-image polling cannot detect every
unobserved same-image re-exec; Niri PID is not a Wayland connection-generation token. Exact native
Ghostty trust/no-forwarding/no-fork/no-connection-transfer/no-unobserved-reexec assumptions require
review and native qualification before converting process evidence into any window/layout grant.
Existing same-user environment and installed Python/native images are trusted, not sandboxed.

Next: independently review the producer and its protocol/accounting evidence, then integrate one
real supported Ghostty path with complete plan/output accounting and a handwritten topology oracle.
Replace the old unsafe expectations as the corresponding behavior is actually fixed; keep the
current failing regressions visible until then. Native canaries and promotion require separate
operator approval. This partial candidate is **not ready to merge or deploy**.
