---
summary: "Add an unexpected-power-cut alternative without overstating recovery or dismissing hybrid sleep."
read_when:
  - "You revise crash, outage or hibernation claims in the announcement."
type: "reference"
---

# Planned reboot or sudden blackout

The 0.3.2 film now has nine contiguous scenes in 45 seconds. A separately labelled alternative
shows the working desktop cutting to black at 13.7 seconds: “POWER OUT.”, “A saved snapshot may
survive.”, “Unsaved work does not.” Reopening explicitly requires a successful boot and a usable
saved snapshot. No repeated flashing, actual crash, power operation or desktop capture is used.

The README concedes completed hibernation and hybrid sleep surviving power loss, distinguishes
plain RAM suspend, and names pre-loss capture, storage survival, successful boot and lost changes
since the last successful capture. This is not OS/disk repair or hardware crash qualification.
Store fsync/pointer durability supports intent, not an unconditional storage-survival guarantee.

Independent source inspection found no must-fixes. Ruff, privacy/source, strict announcement-docs
and whitespace checks pass. Handwritten checks cover timeline, copy and measured text/result-row
fit; Director still reports only its documented counter-strip findings (exit 2). Key stills, sheet
and draft were rendered, not visually inspected. Final encoded background pixels change from
RGB (10,19,22) at 13.6 seconds to (0,0,0) at 13.8 seconds and remain black through 16.5 seconds.
That checks the cut, not visual readability. Final film: 45 seconds, 1080p30, H.264, yuv420p,
standard range, no audio. Visual playback review remains necessary before publication.

Only local source/docs and the prepared film changed. Original 0.3.1 footage, package version,
installed runtime and live desktop are untouched. No publication or OS action occurred.
