---
summary: "Require explicit incoherence and complete typed same-instance evidence before default restore fallback."
read_when:
  - "Changing capture coherence, the capture command's retry or default restore snapshot selection."
type: "diary"
---

# An incoherent last capture must not cost the whole desktop

An incoherent latest observation can block default restore even when an earlier display-valid
capture of that instance exists. Incoherence can reflect topology, focus, layer or process changes,
or process-probe warnings. The earlier login-refusal report did not establish which predicate
failed; a focus switch is a possible cause, not a proved explanation of that incident.

Existing source behavior, unchanged by this hardening:

- The `capture` command takes up to three readings, 1 s apart, and saves the first coherent one or
  else the last. Only this command retries; other consumers still use a single `probe.capture`.
  Output gains `samples` when more than one reading was taken. Exact-output callers are **not**
  universally unaffected: they must allow this conditional field, and later readings can change
  saved content, timestamps and digest. Capture-only bounded retry is not changed here.
- Default restore has display-unavailable/missing-pointer fallback and an incoherent same-instance
  fallback. Explicit digests never gain fallback semantics. Selection writes no pointers.

The narrow hardening requires literal `coherent: false` on latest, not merely readiness's broader
"not true" classification. Both latest and fallback must carry complete typed compositor identities:
nonblank, NUL-free `boot_id`/`niri_socket` strings and nonnegative integer `socket_inode`/`socket_device`
pins, never booleans or floats. Full identity metadata must match without type coercion, projection
or normalization. Boot IDs remain opaque strings, not a new UUID grammar; socket paths are not
resolved, inspected or reopened. No persisted schema changes. These checks apply only to the new
incoherent fallback family, not a general snapshot-schema rewrite.

Tests use handwritten refusal/recipe oracles: missing/nonboolean coherence; missing, null, wrongly
typed, blank/NUL string and negative-pin fields on each side and both; all four typed identity
conflicts; metadata aliases and differing socket spelling. Positive fixtures include a fabricated
61-window desktop, manual/login current-instance skips and explicit-digest compatibility. Corrupt
or missing sources still refuse. A real lock/history path in a private test runtime refuses the new
incoherent fallback with retained torn `.restore`/`.permit` evidence before any capture or effects.
Restore stdout/receipt and selection diagnostic shapes remain unchanged.

Scope: isolated source and fabricated focused tests only. No installation, live compositor/state,
login service or runtime qualification is established. Independent inspection and delivery remain
separate; source tests do not authorize live effects.
