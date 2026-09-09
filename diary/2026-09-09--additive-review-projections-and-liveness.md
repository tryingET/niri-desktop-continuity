---
summary: "Closed additive grouping/diagnostic review projections and correlated pending keepalives, with frozen replacement semantics and synthetic verification."
read_when:
  - "Reviewing additive approval visibility, backward compatibility or IPC lease behavior."
type: "reference"
---

# Additive review projections and liveness

## Implemented

Added optional closed grouping and privacy-safe diagnostic projections to the existing additive
observation/admitted contract. Grouping names exact opaque refs in desired member sequence and
reviewed provenance; it must partition the saved set exactly. Diagnostics explain each unresolved
ref with one controlled reason code and expose capacity separately from identity uncertainty.
No native paths, exception strings or application titles enter these projections.

Plan JSON, offline preview, receipts, fresh verification and canonical inspect preserve the
projection. The preview uses the existing table/typography/colors and labels requested grouping
separately from native topology. Historical observations without projections gain no defaults,
new receipt fields or implied grouping. Existing sessions remain protected: no tab transfer or
shutdown authority was added. Preview warnings and inspect guidance explain that failure can
leave windows/focus changes and forbids retry, ledger deletion or changing roots as a workaround.

The additive protocol now accepts a correlated pending heartbeat containing only the exact
pending sequence and intent digest. The reply echoes those fields. It retains the existing
permit/event and never grants another launch or focus action. Empty/mismatched/extra-field
pending heartbeats refuse. Replacement v1/v2 still reject all pending heartbeats.

## Independent review corrections

Review found that a slow coordinator journal could consume the lease after the receive-time
check yet still issue a permit. The transport now rechecks after journaling/encoding, caps sending
by both remaining monotonic lease and absolute deadline, and checks before resetting its timestamp.
Late/trickled frames cannot revive expired liveness. Worker-side liveness enforcement remains an
independent owner responsibility; transport success is not native effect proof.

Review also caught a compatibility regression in unconditional final-result expiry validation.
Frozen replacement v1/v2 may finish final observation after effect expiry; that behavior is retained.
Additive's explicit final expiry gate is separate. No expired reply grants another physical effect.

A test-strength issue was corrected: projection drift tests now prepare valid fabricated canonical
accounting and include unmodified positive controls for admit/execute/verify/inspect. Failures cannot
pass merely because unrelated accounting is absent. A handwritten pre-projection receipt/approval
field oracle is read through canonical history validation rather than upgraded by defaults.

## Verification and boundaries

Final `UV_OFFLINE=1 just ci` passed: **466 tests**, Ruff, formatting, Python 3.11 syntax,
portable-source/privacy checks, wheel/sdist builds and installed-wheel smoke. Independent follow-up
review found both source blockers closed; its optional test-strength finding was then corrected
and verified with 17 history/drift cases including all four unmodified positive controls. All
endpoints, desktop state and effects are fabricated; these results are not real Ghostty/bootstrap/
census or native canary qualification.

Design reference: `DESIGN.md`. Foundry lint returned zero errors and one preexisting orphan-token
warning; agent-context export informed the existing-table implementation. No token values or design
contract changed. No services, live profiles, windows, native processes, or installed machine tools
were modified by this portable slice. No commit or publication was performed during implementation.
