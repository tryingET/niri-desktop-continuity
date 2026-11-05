---
summary: "Give the blackout setup a real reading pause instead of covering its entrance animation."
read_when:
  - "You change announcement timing or shorten the blackout setup."
type: "reference"
---

# Reading pause before the blackout

The operator observed that “Or, without warning…” could not be read. The cover started at
13.7 seconds while the title's entrance ended at 13.75: it never had a fully entered reading hold.

The setup now occupies 13–17 seconds, including 3.25 fully entered seconds. The blackout holds
17–21 seconds. All later scenes and absolute animation delays move four seconds later, preserving
their durations; the film and README now say 49 seconds. No unrelated behavior or version changed.

Three offline unittest regressions live beside the generator and are documented in the render
recipe. Restoring the old 13.7-second cover makes the reading-hold test fail; the corrected source
passes all three. An independent timeline inspection found no omitted later delays or scene gaps.

Final encoded samples remain nonblack through 16.9 seconds and are black at 17.1, 18.5 and
20.5 seconds. The title crop changes by only 0.044 mean RGB units between 14.0 and 16.8 seconds,
checking that it remains static instead of disappearing. This is encoded timing evidence, not a
human readability judgment. Ruff, privacy, docs and whitespace checks pass. Director's only layout
findings remain the documented counter strips. The 49-second MP4 replaces the local prepared
0.3.2 asset; original 0.3.1 footage is untouched. No publishing or live desktop effects occurred.
