---
summary: "Explain why fresh-session reconstruction differs from suspend and hibernate."
read_when:
  - "You revise the README, package summary or announcement's recovery claims."
type: "reference"
---

# Reboot reconstruction versus hibernation

## Reader problem

The introduction did not answer whether suspend or hibernate already met the reader's need.
The announcement's “Everything is gone” / “It comes back” sequence also hid the distinction
between reopening windows and restoring application memory.

## Changes

- Lead with a real reboot, using starting a new kernel as the concrete example.
- Recommend working suspend/hibernate for continuing the same running system; link ArchWiki.
- State new-process, application-owned content and unrecoverable-memory limits before setup.
- Align the package summary and re-render the fabricated announcement with the same distinction.

## Checks and limits

Full offline CI passed: 1,268 tests, package builds and installed-wheel smoke. Wheel metadata
contains the revised summary and comparison. The announcement generator passes Ruff lint and
format checks; the final MP4 passes source/privacy checks and is 39 seconds, 1920×1080, 30 fps,
H.264, yuv420p, standard video range. Director's changed-scene layout bounds show the explanatory
text fits between the heading and desktop. Its only reported findings are the documented
counter-strip clipping/off-canvas false alarms. These checks are not visual playback inspection;
that remains necessary before posting. No runtime behavior, release version or remote metadata
was changed, and nothing was published.
