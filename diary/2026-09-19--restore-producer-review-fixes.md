---
summary: "Narrow producer review corrections; ordinary restore integration remains deliberately red."
read_when:
  - "You review the producer's raw evidence, decoder, executable admission or shared lock changes."
type: "diary"
---

# Producer review corrections

## Scope and disposition

Independent review supplied counterexamples for environment normalization, JSON numeric overflow,
FIFO admission and shared read-only locking. Fixed only that producer slice and its tests/docs.
The sole reconstruction implementation change is four explicit read-only lock call arguments in
`recovery.py`; approval and execution still use the default guarded mode. No reconstruction effect
logic, ordinary restore integration, settlement or native qualification was added.

The candidate copy of the login-contract fixture now accepts the explicit `effectful` keyword and
asserts that dry-run requests `False`. This small adaptation was separately authorized; no other
login assertions changed. The original copied validation diary remains byte-for-byte unchanged.
The canonical installation, its original test/diary and its environment were not touched.

## Corrections

1. `Process.environment()` decodes and structurally validates raw proc initial-environment data;
   it does not rewrite the backend or drop forbidden keys. Both prepare peers explicitly construct
   the sanitized desired map. `LaunchProof.validate()` compares the raw host observation exactly
   to that map. Handwritten x11/socket/service-control additions now invalidate proof rather than
   disappearing through normalization. Missing termination, duplicate or empty keys also refuse.
   This observes the kernel-exposed initial environment region, not current dynamic libc/Python
   environment state, and does not prove that an application never changed its environment.
2. JSON `parse_float` rejects overflow to infinity, including nested object/array values, in addition
   to the existing rejection of nonfinite constants. Finite floats and absolute frame deadlines
   retain their behavior.
3. Image open uses `O_NONBLOCK` before fstat/ELF admission. An owned FIFO without a writer refuses
   promptly and never dispatches. Absolute deadlines are checked around opening/hashing and hash
   chunks, including producer and bootstrap image validation. These checks do not promise to
   interrupt hung filesystem/kernel syscalls. No timeout process termination was introduced.
4. Removed the ambient ContextVar bypass. `operation_lock(..., effectful=False)` still validates
   identity and actually acquires the exclusive flock; only the retained restore-marker effect
   gate is omitted for physical read-only work. The default remains `True`. Nested callbacks get
   no ambient exemption, and active writers exclude readers. Dry-run and recovery propose,
   validate, inspect and verify use explicit read-only admission. Recovery approve/execute,
   reconcile and transitions remain effectful. No marker is cleared and no effect authority is
   conferred by the read-only mode.
5. Documented the trusted-bootstrap/interpreter/import boundary. Credentials, image pins and
   nonce binding are not authentication of Python module origin or a sandbox against a malicious
   same-UID process. Process proof remains distinct from window ownership and exec-history proof.

## Exact evidence

All logs and the incremental review diff are retained outside the repository for the handoff.
Only fabricated state, private locks, local sockets and bounded test hosts were used.

| Run | Result |
| --- | --- |
| Review RED before source mutation | 33 failed, 8 passed in 12.96 seconds |
| Targeted review + producer/handshake + login/reopen GREEN | 135 passed in 48.67 seconds |
| Existing ordinary-restore regressions, unchanged and unsuppressed | 6 failed in 0.97 seconds |
| Single final `UV_OFFLINE=1 just ci` | exit 1: 6 failed, 773 passed in 500.75 seconds |
| Separate source/entrypoint smoke, wheel/sdist build and installed-console smoke | exit 0 |

The review run adds 41 cases. Some lock-mode RED cases encountered the missing explicit keyword;
independent dry-run callback, invalid-identity and actual recovery-consumer tests demonstrated the
behavioral defects as well. Recovery tests use the existing fabricated endpoint fixture and compare
its effects ledger before/after read-only calls under retained markers. Actual recovery effect
admission and reconcile remain refused. The original installed-bootstrap/fabricated-ELF positives
also passed; no compiler-dependent case was skipped in these runs.

The six full-CI failures are exactly the known ordinary-executor regressions: matching-label unowned
arrival, mismatched fallback, missing-browser relaunch, incomplete interrupted accounting, partial
success pointer, and missing pre-dispatch intent. There are no xfails or suppressions. Packaging
checks ran separately because full CI stops at these tests; they are not a substitute full pass or
new native producer qualification. The final gate was run once, with no short cutoff.

## Integration blockers remain

There is still no full multiwindow attempt lock owner or subordinate per-launch journal. The current
producer owns its own flock, cannot nest inside restore's existing lock, and retains a fence that
refuses a second launch even after process proof. Looping the single-launch producer is not a working
multiwindow integration. Do not clear markers or bypass flock to make it appear composable.

Ordinary restore's six defects, complete-plan/output accounting, protected-cohort topology/layout,
completed replay/settlement and native session usability remain unimplemented. Native Ghostty,
Wayland connection behavior, no-forwarding/no-unobserved-reexec assumptions and login lifecycle
remain unqualified. No live compositor, real lock directory, native profile or service was accessed;
no process was killed, and no deployment, commit or task-state mutation occurred.

Next: independent rerun/review of these narrow corrections. Full restore integration is a separate
bounded decision, not completed or authorized by this passing producer subset.
