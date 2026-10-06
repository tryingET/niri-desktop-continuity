---
summary: "Bounded restore corrections: physical pixel grids, honest dimension coverage, shared widths and stale references."
type: "implementation"
---

# Bounded restore corrections

This changes only the isolated candidate. The preceding **842-test CI result is superseded after
these source changes**, not current qualification. No full CI run was performed in this dispatch.
Independent re-review remains required; nothing was promoted, committed or deployed.

## Source facts and implementation

Pinned public Niri revision: `62c230a662ac913a54fc49c86fda0406da3f3ba9`.

- `src/layout/floating.rs` 338–348 rounds IPC positions to physical pixels and back to logical
  coordinates. Lines 964–1011 adjust the unrounded internal position. `src/utils/mod.rs` 208–228
  emits the output's actual fractional scale; `niri-ipc/src/lib.rs` 1210–1271 exposes
  `Output.logical.scale`. Rust floating-point round uses ties away from zero.
- `restore_dimensions.py` projects requested floating coordinates onto that observed grid. Signed
  dispatch deltas use 17-digit round-trip precision, not 12-digit truncation. Predictions and terminal
  verification compare exact observable positions; there is no tolerance exemption. Unknown scale
  cannot prove a requested position. Receipts distinguish `requested-quantized-observed` from an
  unchanged requested coordinate. This does not claim recovery of Niri's hidden unrounded position.
- Requested dimensions start pending, including not-yet-processed supported entries. Explicit
  comparisons against proof-checked observations grant coverage; neither intent nor overall success
  grants it. Early decoration refusal retains pending width; a later position failure retains the
  independently verified width but leaves position pending. Already-observed width needs no guessed
  decorations or redundant resize.
- The admitted column resolves one width before launch. Consistent explicit widths govern every
  member; unspecified members report `inherited-column` only after verification. With no recorded
  width, preserve the admitted seed width and let other members inherit it. Separate extra columns
  retain their own initial widths. Conflicting explicit widths refuse before any launch or layout.
- Transfers and names bind the caller's intended stable workspace ID/output/index, then check that
  exact reference before intent and again after its durable write, immediately before dispatch.
  Observed reindexing, ambiguity or output drift stops without stale dispatch, intent rewrite or
  retry. The checks do not recompute a new destination from an already-stale numeric argument.
- Canonical history is closed **v3**, with typed output scales and workspace-reference bindings.
  Offline loading recomputes pixel targets, column policy, action bindings and terminal coverage.
  Candidate v1/v2 histories remain blocked, not healed or migrated. Public recovery protocols and
  producer/bootstrap contracts are unchanged; this is not a new public recovery protocol.

## Evidence

Raw logs are retained under `$TMPDIR`, outside the source tree:

| Log | Observed result |
| --- | --- |
| `ndc-bounded-red.log` | **12 failed** before source edits: fractional/tie grids, premature coverage, shared widths/conflict, stale transfer and naming |
| `ndc-bounded-reference-red.log` | **2 failed, 22 deselected**: an earlier reindex could silently bind another admissible neighbor before intent |
| `ndc-bounded-binding-characterization.log` | **6 passed, 16 deselected**: initial earlier-race examples happened to hit existing protected/cohort refusals; not RED evidence |
| `ndc-bounded-targeted-final.log` | **262 passed in 156.24s**, no skips/xfails reported |
| `ndc-bounded-independent-final.log` | **22 passed in 23.54s**, no deselections/skips/xfails reported |
| `ndc-bounded-static-final.log` | Repository lint, formatting, Python portability/privacy and `git diff --check` passed |

The 262-test command selected every `tests/test_restore*.py` module plus `test_reopen.py` and
`test_login_restore_contract.py`: the preceding 204 affected cases, 53 new bounded cases and five
supplied follow-up oracles. It includes both existing editable and **freshly built wheel** console
runs, production Niri spawn transport/bootstrap, retained pidfds and cooperative fabricated ELF hosts.
The wheel test checks installed import origin. Cached build dependencies were supplied explicitly;
this is a fresh current-source build, not testing the preceding candidate's wheel.

The separate 22-case run includes all 17 supplied independent assertions unchanged and the five
follow-up assertions copied into `test_restore_followup_oracles.py`. Those five have only schema
version/import isolation and cosmetic formatting/name updates; their behavioral obligations remain.
They overlap the 262-case run. This is **implementer-run evidence, not independent sign-off**.

Current-schema attacks first establish an accepted v3 terminal, writer admission and historical
replay. They then relink hashes and intent receipt references while corrupting scale, target bindings
or inherited/pending coverage. Float attacks include an off-grid epsilon and a consistent different
physical pixel with matching action/effect records. Rejection therefore does not rely on simply
presenting an obsolete version or dangling reference. Valid clean-login, lifecycle, focus, optional
extra width, replay and wheel cases remain green.

Handwritten grid cases cover scales 1.5 and 1.25, negative/nonbinary coordinates and Rust half ties;
near-half cases prevent an incorrect add-half implementation. A fabricated `LiveDesktop._query`
response exercises the real output-mapping shape. Unknown/invalid scales and scale drift after
intent cannot authorize floating dispatch. Both transfer and naming have before/after-intent
reindex, ambiguous-index and changed-output cases, plus admissible-wrong-neighbor regressions.

All effect-bearing tests use fabricated desktops/hosts and private runtime fixtures. The initial RED
and early progress runs used that fixture isolation; final affected/probe runs additionally set
process-level private HOME/XDG roots and unset display routes. No real compositor was contacted.
The copied login diary remains byte-for-byte unchanged (SHA-256
`329c6126d14bdb172d6073acd3069959472c82035807bc6bc68d4a9525e1ff29`).

## Remaining limits

- The final observation/check and IPC dispatch are **not atomic**. Automatic compositor cleanup can
  still race after the final check; an idle operator is necessary but not sufficient to eliminate it.
- Hidden unrounded floating residue or native constraints can fail strict postconditions. There is
  no correction retry, rollback, timeout kill, marker clearing or settlement command.
- Saved tile height is not restored. Native Niri/Ghostty geometry, session usability, browser/general
  application ownership and login deployment remain unqualified. Trusted fresh-host connection
  behavior is still an assumption, not general PID causality.
- The canonical installation, native profiles/services and external task state were not changed.
  Synthetic green tests and source-informed models do not authorize promotion or live effects.
