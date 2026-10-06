---
summary: "Offline v2 reviewer corrections; prior wrong-wire fixtures are not family qualification."
read_when:
  - "Reviewing exec-observed-unassociated witness, segment, identity or consumption ordering."
type: "implementation-note"
---

# Exec-observed-unassociated reviewer corrections

The prior integration fixture used `process-exec-observed`, whereas the unchanged ordinary executor
returns `launch-indeterminate` when association fails after exec observation. Its prior passing
results remain evidence of that incorrect fixture, not intended-family qualification. Original
source/evidence were preserved before these corrections; no actual retained witness was rewritten.

Corrections are confined to the v2 model and publication ordering, plus tests/documentation:

- Require the exact original launch-indeterminate row. Reject the earlier row spelling.
- Repeat live topology/process validation and expiry after the last complete capacity/dependency
  check, immediately before consumption; preserve the separate prepublication veto and stage fence.
- Bind exactly seven segment fields: start/count/previous, exec intent/observed payload digests,
  observed process receipt and frozen baseline digest. Reject old four-field and mixed wires.
  Partial labels are exactly `historical_association="not-recorded"`, `outcome="unresolved"`.
- Compare historical process identity by boot/PID/start, not PID alone or incidental metadata.
  Protected/controller live-PID guards and the existing history boot rule are unchanged.

New oracles first demonstrated nine contract failures and then a genuine executor-derived witness
refusal. Initial executor-harness errors (cooperative program exited on bootstrap's /dev/null stdin)
are retained separately, not counted as behavior REDs. The corrected cooperative helper waits for
its fixture-owned quit file; product code performs no cleanup or process termination.

The positive continuation invokes the actual ordinary CLI/executor and default producer handshake,
with fabricated Niri spawn/observation transport and real cooperative ELF/process proofs. A forced
ValueError at the read-only association entry creates the original result/exit/five records. After
partial accounting, a fresh source launches a second host, places/verifies its width, preserves
protected dimensions, restores focus, and commits the ordinary receipt and pointer. This is not an
unsupported/manual terminal or mere lock-acquisition proxy.

Corrected installed-wheel checks assert the literal witness, seven-field segment and partial labels.
Related reader/v1 checks, focused v2 tests and static checks are run separately from parent full CI.
Independent rereview, parent full CI, native qualification and deployment are still separate gates.
No maximum-size stress, exhaustive fault/signal/power-loss proof or atomic native freeze is claimed.
