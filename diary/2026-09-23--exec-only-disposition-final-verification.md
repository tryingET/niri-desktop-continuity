---
summary: "Exec-only accounting disposition v2 independently reviewed and full CI verified offline; no native application."
type: "validation"
---

# Exec-observed-unassociated disposition — final offline verification

## Delivered scope

The existing CLI now supports explicit `--family exec-observed-unassociated` on disposition
inspection/proposal. The closed v2 family accounts only for the exact five-record ordinary-restore
history after observed bootstrap/exec and before association or layout. It preserves original
`launch-indeterminate` witnesses and reports partial accounting, not historical completion.
Default v1 width-family behavior remains separate. No native records, windows or installation were
read or changed for this offline work; applying the new family needs separate exact approval.

## Design decisions and honest integrity limits

A bounded envelope-routing prerequisite precedes new-family materialization. Its explicit legacy
routing allowance is separate from per-v2-prefix limits of 32,768 unique paths, 512 MiB unique raw
bytes and 16 MiB per file. Those are not total-I/O or RAM limits. Repeated passes, barriers, legacy
suffix work and decoded-object amplification remain additional costs. Reservation-bound reads and
irreversible reader retirement prevent a failed materialization from reusing cached evidence.

Persisted manifest/witness pins remain binding. Newly generated artifacts without such a durable
pin have semantic/cross-reference checks and first-observation stability within a validation/barrier
interval—not independently authenticated creation inodes. A later plan can bind prior artifacts as
observed then. The terminal trust remains owner-controlled append-only state and trusted workflow,
not cryptographic protection against an owner rewriting the entire graph. No new trust anchor,
acknowledgment marker chain or private adapter was introduced.

The existing noncanonical `.pending` stage precedes consumption under the approved flock. Independent
review approved this ordering because failed attempts stay fenced even against another approval.
The final capacity check is followed by live/expiry vetoes before consumption; another mandatory
veto precedes publication. No stage grants terminal authority or permission to retry or clean up.

## Independent review and corrections

Earlier implementation evidence remains retained, including safely withdrawn drafts and wrong-wire
fixtures. It is not qualification for the corrected family. Genuine correction REDs covered the
actual witness status, approved seven-field segment/references and partial literals, the final
pre-consumption veto, and exact boot/PID/start identity instead of permanent numeric-PID exclusion.

The final reviewer independently ran 168 v2 cases and 71 external fault/admission probes on each
of Python 3.13 and 3.14. One external obsolete-literal case was explicitly deselected, not counted
as passing. The independent tester separately retained its original probe, corrected only the
approved exact literal in a copy, and passed 264 cases per interpreter plus installed-wheel checks.
Both verified stable source inventories and reported no remaining material blocker in scope.

The positive continuation is substantive: a fixture derives the original five-record interruption
through the unchanged executor/default producer. After v2 accounting, another fresh source launches
a second cooperative ELF through ordinary restore, performs fabricated placement, verifies width,
preserves protected dimensions, restores focus and commits the ordinary receipt/pointer. Replay of
the interrupted source remains partial with no new effects. This is synthetic execution, not usable
native Ghostty/Niri or conversation-state proof.

## Parent full gate

The first parent CI invocation accidentally inherited `umask 077` from private evidence setup.
Two existing tests attempting to create unsafe `0755` directories instead created `0700` directories:
1,669 passed and two failed. The source remained unchanged. Both cases passed with the normal test
mask; the subsequent complete gate used an explicit `umask 022` while retaining private evidence
storage.

Final `env -u NIRI_SOCKET UV_OFFLINE=1 just ci`:

- **1,671 passed in 909.87 seconds**, no reported skips;
- Ruff and formatting, with 146 files formatted;
- portable-source/privacy and Python 3.11 syntax checks;
- wheel/sdist build and isolated installed-wheel smoke.

All 236 reviewed source-inventory entries remained unchanged through the complete gate. Status
documentation and this diary were updated afterward, followed by separate static and packaging
checks. The earlier full suite is not claimed to have run on those later documentation bytes.

## Unperformed and retained

No native inspection/application, new restore attempt, termination, cleanup, actual fence change,
service/login change, canonical-source promotion, commit or deployment occurred. Native eligibility
and current process survival were not rechecked. The new accounting implementation does not settle
the actual interruption by itself. Corrected native restore/session verification, browser/general-app
coverage and deployment remain separate unresolved work. Filesystem/native operations are non-atomic;
maximum-size, exhaustive crash/interleaving, signal/kernel and power-loss behavior are not proved.
