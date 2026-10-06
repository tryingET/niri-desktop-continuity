---
summary: "Bounded CLI capture selection with fabricated RED/GREEN evidence; full gate and native qualification pending."
read_when:
  - "You review selected captures before a separately approved restore canary."
type: "validation"
---

# Selected-window capture

Added repeatable `capture --window-id INT` only in the isolated candidate CLI. Exact IDs must be
nonnegative, unique and present in the same capture before any snapshot/pointer commit. No flag
preserves original snapshot bytes/result shape. Selection retains source window order, entire recipes
including extras, and all supporting observations. A closed generated `capture_selection` object
records the exact sorted IDs, selection kind and observed window count in snapshot/result; its
ordinary immutable digest binds those facts without referencing an unsaved source artifact.
Readiness is recomputed; source coherence is retained. CLI grew from 354 to 386 lines. No probe,
model, Store, restore ownership/history or runtime dependency changes belong to this slice.

## Observed validation

- Before CLI changes: **23 failed / 1 passed**. Failures were missing selector/diagnostics;
  unchanged full-capture bytes/result passed.
- Initial GREEN: **24 passed**. Two further cases cover single-entry dry-run/workspace intent and
  explicit-all-ID provenance; unsupported-kind tests also check existing admission refusal.
- Final new test file: **26 passed**. Combined bounded run with three existing Store/readiness/CLI
  regressions: **29 passed in 6.93 seconds**, no skips. These counts overlap, not additive coverage.
- Repository-wide Ruff lint and formatting checks (103 files), portable-source/privacy/Python 3.11
  syntax checks and whitespace diff checks passed. No package rebuild or installed-wheel test ran.
- Tests invoke actual `cli.main`, production probe normalization with fabricated IPC/process/recipe
  boundaries, immutable Store and ordinary restore dry-run/planner. Handwritten ID/count/read-call
  oracles cover whole-desktop probing, ordering, exact metadata, extra recipes, error noncommit,
  source nonmutation, supporting data, readiness and immutable receipt linkage. Process launch and
  desktop-action traps stay unused. Stores/locks live in private temporary fixtures; no C compiler,
  native profile/session reads or real compositor access is needed.

Selection is **not selective probing** or resource isolation: whole-desktop/process/session metadata,
including potential Claude transcript-title reads before redaction, remains read. Supporting process
observations remain saved. Ordinary Store pointers promote the selected snapshot; a private Store is
not a canonical compositor-lock/history bypass. One selected window may still plan multiple launches.

## Remaining gates

Independent review and a fresh full CI/build/installed-wheel gate remain with the controller. The
previous **900-pass** full gate is historical and does not qualify these changed runtime/test bytes.
No full suite was run for this slice. Native Ghostty/layout/session/login qualification remains
unperformed. No commit, deployment, service change, native effect or cleanup was performed.

Proposed next steps only: review this delta; run the full gate once; separately authorize read-only
capture of an actual exact window into a private Store using the existing CLI; retain snapshot digest
and existing restore dry-run's immutable receipt digest. Require exactly one planned entry, no extras,
a harmless admitted recipe and reviewed destination/protected baseline. Then stop for separate
explicit effectful-canary approval. Dry-run is neither admission proof nor approval. Never edit a
snapshot/receipt, drop extras, clear a fence or retry ambiguity to make the canary possible.
