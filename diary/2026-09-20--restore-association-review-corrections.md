---
summary: "Offline review corrections for full output inventory and exceptional descriptor ownership."
read_when:
  - "You review association output baselines or exceptional proof teardown."
type: "implementation"
---

# Association review corrections

The historical coherence checkpoint and all inventoried source hashes matched before mutation.
That checkpoint remains retained as history, not relabelled as covering the corrected bytes.

Genuine pre-edit RED on both Python 3.13 and 3.14 reproduced immediate and split-to-whole association
failure with an unchanged disabled output that has no workspace. The canonical output-scale projection
was incorrectly used as the full output inventory. A separate validated inventory is now frozen by the
initial read before launch and compared without altering canonical state/geometry/history schemas.
Unchanged disabled outputs pass. New/removed outputs and disabled metadata drift refuse. Outer output
and JSON object order are ignored; field presence and arrays are deliberately conservative. JSON
numeric equality does not alias booleans. Known field types and bounded finite JSON are checked before
freezing; unknown metadata receives no invented native semantic interpretation.

The earlier strict decoder's actual-integer workspace reference check is retained and explicitly
covered for `true` and `1.0`. This is an intentional compatibility narrowing, not literally unchanged
acceptance of old accidental aliases. The canonical shape and geometry rules are unchanged.

The two supplied independent cleanup probes failed unchanged on both interpreters: an early proof-close
error skipped later proofs/lock exit, and failed standalone context exit orphaned a detached proof.
Attempt now attempts every proof close and finally exits the lock; a sole failure propagates unchanged,
while multiple failures and a body exception remain visible in a BaseExceptionGroup. Successful cleanup
does not suppress the body exception. Standalone transfer is guarded until successful context exit;
orphan close occurs even for BaseException, with any close error chained to the exit failure. Neither
path kills hosts, retries cleanup, clears history or weakens admission. Real cooperative fixture hosts
remain alive at close assertions and exit autonomously/cooperatively.

Handwritten tests cover full-inventory positives/drift/malformed entries/order invariance and metadata
numeric types. The installed single-host wheel continuation includes a disabled output. Extended
lifecycle tests exercise OSError, KeyboardInterrupt, SystemExit, multiple failures and orphan-close
failure. The exact supplied probes retain their assertions. Test-only import formatting is not a
behavior fix. All tests are offline with fabricated routes/processes/private lock directories.

Independent re-review and the parent-owned full CI gate remain required. No full CI, native canary,
private history, profile, live fence, service, settlement, deployment, commit or task-state mutation
was performed. Polling and non-preemptible-call limitations are unchanged.
