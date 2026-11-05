---
summary: "A distinct 0.3.2 video makes desktop snapshotting and the OS-update boundary visible."
read_when:
  - "You change the announcement's snapshot, reboot or recovery claims."
type: "reference"
---

# Save your place. Update your OS. Reboot. Reopen.

## Reader problem and change

The earlier wording-only correction did not make the saved-desktop versus hibernation distinction
visually central. The new 45-second, eight-scene 0.3.2 composition gives desktop snapshotting and
operator-owned OS updates their own scenes. It shows `capture`, layout/reopen recipes, known
agent-session IDs and opt-in periodic capture, then a fresh-kernel reboot and new-process reopening.
The README links the new film. The original committed 0.3.1 film is retained unchanged.

## Inspection and checks

Independent source inspection led to explicit unsaved-draft/running-job exclusions and an idle-input
instruction. Director's measured result-row bounds disproved the estimated clipping concern.
The reviewer initially saw the new MP4 absent while rendering ran in parallel; the subsequent
final-file existence/format check establishes delivery, not that earlier observation.

Ruff lint/format, privacy/source checks, strict announcement docs checks and whitespace checks pass.
Handwritten checks cover contiguous 0–45-second scenes, version/copy/opt-in boundaries, header
separation and complete result rows. Director reports only the documented counter-strip findings;
its layout-check exit remains 2, not an unqualified pass. Final MP4: 1920×1080, 30 fps, H.264,
yuv420p, standard video range, no audio, 45 seconds. Contact sheet, key stills and a draft were
rendered; these text/layout checks do not establish visual playback inspection.

No real desktop snapshot, OS update, restore, installation, remote write or release publication
occurred. The 0.3.2 video is an asset prepared for that release; package versioning is unchanged.
