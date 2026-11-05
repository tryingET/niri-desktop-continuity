---
summary: "Extend the opening and snapshot slides without shortening later scenes."
read_when:
  - "You revise the announcement's first two slide durations."
type: "reference"
---

# Opening reading time

The operator requested two more seconds for the opening desktop and one more for the snapshot.
They now occupy 0–5 and 5–11 seconds. All subsequent scene starts and animations shift three
seconds later, with their durations and four-second blackout reading holds retained. Total: 52s.
The README and render instructions match.

Two added timing checks failed against the previous 49-second source; all five offline checks
pass on the correction. The existing rendered film was retimed with FFmpeg, adding settled-frame
holds after the first and second entrance animations, rather than rebuilding Director for a
hold-only change. Generator timings were updated to reproduce the same story.

Nine sampled frame mappings to the prior encode have mean RGB differences below 0.1 units,
including both added holds and all later sections. Encoded background samples confirm the new
blackout at 20 seconds and hold through 23.5. This is sampled timing evidence, not an exhaustive
visual playback inspection. Independent timing inspection accepted the intentional pre-entered
desktop animation after its initial false-positive finding was corrected.

Final MP4: 52 seconds, 1560 frames, 1080p30, H.264, yuv420p, standard range, no audio.
Ruff, privacy, whitespace and strict announcement-docs checks pass. Original 0.3.1 film is unchanged.
No runtime behavior, installed software or remote publication changed; owned intermediates removed.
