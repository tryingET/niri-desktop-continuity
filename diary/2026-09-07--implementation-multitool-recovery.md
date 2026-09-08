---
summary: "Generic multi-conversation regressions and installed CLI smoke; machine tool semantics remain separately owned."
read_when:
  - "You review public Pi/Claude/Codex conversation coverage and its machine handoff."
type: "implementation"
---

# Multi-conversation public recovery coverage

## Historical implementation status (before final review)

The implementation, validation and handoff sections below preserve the earlier chronology.
Their IN PROGRESS status is historical and is superseded by the final documentation closeout below.

### Implemented scope

No runtime/schema defect was found for multiple opaque saved conversations. Runtime sources,
v1/v2 shapes, six native predicates, CLI, dependencies and approval/replay gates are unchanged.
No app-name field, native producer implementation, new protocol version or dependency capsule.
Existing source work was preserved; no checkout Git/AK/configuration/private-state operations,
global installation or live effects were performed. Tests use fabricated scratch state only.

- `tests/test_recovery_backend.py`: `provision(..., saved_refs=("c" * 64,))` retains the default.
  Each entry creates a separate native process, even for repeated refs. PID/start ticks are
  102/43, 105/46, 106/47, etc., reserving host 101, omission 103 and utility 104. Process records
  sort by pin digest; unique opaque refs and handwritten native proofs sort by ref.
- `tests/test_recovery_multitool.py`: 70 cases cover three refs remaining three, consistent
  renaming, three processes sharing two refs, all six predicates independently false for each
  of three refs in v1/v2, missing/extra/duplicate proof, observed/capability utilities, separate
  exact omission/limit decisions, retained receipts, no replay and no fresh-history upgrade.
- `scripts/ci/package-smoke.py`: eight installed-console cases retain the original five and add
  three refs alone, with observed btop, and with capability-btop plus an exact omission. The
  actual wheel console script runs outside the checkout; the fabricated socket endpoint remains
  a real subprocess. Test-only profile/capture/lock seams stay inside its disposable environment.
- README, architecture, usage and integrated design/plan/protocol distinguish generic public
  coverage, existing Pi/btop machine evidence and **IN PROGRESS** Claude/Codex integration.
  Architecture no longer incorrectly says no machine adapter has been implemented: that adapter
  exists under a separate owner and does not ship in the public wheel.

Missing native records remain valid incomplete proof (`partial`). Missing utility records and
extra/duplicate native records are schema refusals (`indeterminate` after execution). The v2
`saved_conversations_recovered` field remains an aggregate complete-proof/history count; zero on
partial execution does not mean individually passing records were counted as failed or salvaged.

### Validation evidence and isolation

The full contract is `UV_OFFLINE=1 just ci`. Public source files were copied without Git/private
state and byte-compared with the checkout; test environments/caches/builds live in owned scratch.
Observed gate results: Ruff lint/format passed, **343 tests passed** (prior baseline 273), portable
source/Python 3.11 syntax and entrypoint checks passed, wheel/sdist builds and archive privacy checks
passed, and all eight installed-console v1/v2 smoke cases passed with no runtime dependencies.
The test interpreter was Python 3.13; syntax checking is not a Python 3.11 runtime execution claim.

The first full scratch invocation passed lint/format and all tests, then correctly rejected bytecode
created by an existing isolated subprocess inside the export. Only those inactive, generated scratch
caches were removed; scratch `src/` directories were made read-only to prevent recreation. The
remaining gates then passed without changing source bytes or weakening the scanner. Checkout Git
and its index/private development state were not inspected; export validation is not index proof.
Existing privacy regressions use Git only in their own fabricated temporary repositories.

### Machine handoff and nonclaims

`saved_refs` is an ordered per-process sequence of already scoped opaque 64-character hex refs;
use three distinct refs to model three conversations, repeated refs to model shared identity.
`utility="observed-image"` or `utility="capability-btop"` selects v2; `missing=True` adds the
separately approved native omission. `utility_only=True` with a utility still removes native records.
This is a fixture API, not an application detector or native identity hashing recipe.

The machine owner must independently test equal native IDs across Pi/Claude/Codex, proving
app-kind namespace separation and distinct resume targets while same-app identities deduplicate.
Native file/header/cwd/runtime/bootstrap/surface/causal-window evidence must be retained and measured
independently. Public opaque refs and fabricated booleans cannot prove those producer semantics.
Claude/Codex status remains IN PROGRESS pending machine-owner implementation/proof and finalization.
Existing Pi sandbox resume evidence is not Ghostty/service/provider/live-layout proof; btop machine
boundary tests are not native live recovery. No production profile, live approval, restart, semantic
completeness, full native coverage, release or independent safety certification is claimed here.

## Final documentation closeout — replaces historical status above

Pi/Claude/Codex/btop are **implemented and independently reviewed with isolated integration tests;
native desktop qualification unperformed**. This replaces the earlier IN PROGRESS Claude/Codex
status, not the historical test record. The separately owned private `machine.v3` implementation
uses unchanged public v1/v2 schemas and the existing CLI. The public package ships no machine adapter.

Supplied final evidence, recorded as separate non-additive sets:

- Independent public review accepted the bounded fixture/documentation slice: 161 tests, including
  70 new cases, and eight installed-console smoke cases. Parent actual-checkout `UV_OFFLINE=1 just ci`
  passed 343 tests, a new build and installed-console smoke.
- Independent machine final review accepted six native fixes after 187 application tests and eight
  independent cases. Recorded source/full validation passed 686 tests with five native Pi skips.
  The later combined parent run remained running; no newer count or completion is asserted.
- Isolated machine tests verified app-kind-scoped native-ID collisions, same-kind deduplication and
  actual native-shape callback/log fixtures. Real Claude/Codex sandbox prototypes supplied genuine
  callback, file-descriptor and initialization evidence. The faulty Claude harness prevented clean
  exit; one isolated sandbox remains held awaiting operator cleanup approval. No permanent real
  Claude/Codex native opt-in tests were delivered. Neither clean Claude compatibility nor full
  native/runtime certification follows.

Only the allowed public documentation was finalized in this pass. Shipped design/plan links now
resolve to the shipped usage coverage/validation summary, not excluded diaries. Diary paths are
literal checkout-only chronology; diaries remain excluded from distribution. Existing scope, losses,
identity/ownership checks, approval, expiry, focus, writer-lock and replay gates are unchanged.
Unknown or unproved helpers remain blockers. No production profile, global installation, live
Ghostty/service/layout qualification, live approval, cleanup, commit or release is claimed.

Changes remain uncommitted; this documentation pass performed no installation, runtime/machine/Git/
configuration operations or tests. Final build/strict-docs validation is left to the parent; the
reported prior results are not validation of these final Markdown edits.
