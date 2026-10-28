---
summary: "Bounded default restore snapshot fallback and its compatibility corrections."
read_when:
  - "Tracing the display-unavailable default restore selection fix"
type: "diary"
---
# Restore readiness-valid snapshot selection

## Implemented boundary

Default manual/login restore selects a readiness-valid latest observation, falling back to the
preserved display-valid snapshot only for coherent display unavailability or genuine latest-pointer
absence. Explicit digests never fall back. Referenced-artifact, integrity, schema, path/permission
and pointer errors propagate without alternate selection. A dangling pointer symlink is an error,
not absence. Readiness is recomputed, not trusted from a cached display label.

Default fallback checks both latest and selected compositor identities and skips on a current-instance
match. This prevents a display-off observation from reopening an old desktop. Existing login waiting
and same-instance protection remain; manual ready-latest/explicit semantics are not newly banned.
Selected sources still enter the existing restore function, including historical admission and all
recipe/ownership checks. The corrected candidate emits one stderr JSON diagnostic containing only
pointer/digest/fallback reason, not source contents. Stdout/result JSON, receipts and pointers are
unchanged. Explicit login preserves its same-instance skip before display-readiness refusal.

## Corrections after inspection

- Provenance is emitted only for an actual default fallback, as one stderr JSON line with the
  pointer, digest and fallback reason. Explicit and ready-latest invocations keep their stdout and
  stderr; stdout, receipts and pointers never carry selection metadata.
- Readiness had conflated missing workspace references with display unavailability. The fallback
  path now refuses unknown or non-integer window workspace references, including boolean and float
  aliases; six regressions cover the unavailable and active-display cases.
- An earlier variant that put the provenance on stdout broke the v2 disposition witness. The
  stderr-only form passes the unchanged v2 executor continuation.

## Verification and limits

The focused selection, login, capture, reopen, lifecycle and v2-executor suites passed (163 cases),
with Ruff, formatting and the portable-source check, and an independent inspection accepted the
bounded selection. No native compositor, live fallback or login replay was exercised. Selection is
read-only, not an atomic freeze of the pointer files: restore rereads the selected digest and keeps
its own admission, and corruption is never caught to try another source. Since IS-2 (2026-10-27)
the selected snapshot enters the `reopen` engine; the selection rules are unchanged.
