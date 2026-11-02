---
summary: "The capture command reads again after a failed or timed-out Niri query instead of giving up until the next timer run."
read_when:
  - "Changing capture's bounded retry (probe.settled_capture) or the capture command's failure handling."
type: "diary"
---

# A failed Niri query no longer costs a whole timer interval

A periodic capture shortly before a reboot failed because one `niri msg --json windows` query
timed out after 10 s while the system stalled under storage pressure. The capture command gave up,
so the login restore used the capture from one timer interval earlier. The stall was a machine
condition, not this tool's; the gap was that one failed query discarded the whole run.

`probe.settled_capture` already read again, up to three readings, when a reading was incoherent.
It now also reads again when a reading fails with a subprocess error (timeout or non-zero exit) or
an OS error, waiting 10 s instead of 1 s first, since a stall that outlived a 10 s query is unlikely
to clear within a second. It returns the first coherent reading, else the last one that succeeded
(an incoherent reading is still better evidence than none, and selection knows how to fall back
from it), and raises the last failure only when every reading failed. Validation errors such as a
missing `NIRI_SOCKET` are not retried. Worst case the command takes about 50 s instead of 10 s.

Only the capture command retries; approve, verify, reconcile and recovery keep a single reading.
Capture is read-only, so reading again has no effect to repeat.

A capture at session end was considered and not added: the failing run fell inside a stalled,
remotely requested reboot, where a session-end hook would have met the same stall, and windows
close during logout.

Tests list each reading sequence by hand (timeout then steady, incoherent then timeouts, timeout
then incoherent then steady, three different failures, an invalid reading) with the reading
returned and the pauses taken, plus a CLI run that saves the reading after a timeout. Without the
change six of them fail.

User-facing change for the next release notes: `capture` reads again (after 10 s) when a Niri query
fails or times out, and fails only when all three readings fail.
