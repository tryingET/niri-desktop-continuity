# Portable resolution implementation notes

Implemented the existing-CLI candidate/resolution routes, isolated strict resolution objects,
retained historical bytes and explicit config binding, canonical append-only profile transition,
shared admission view, owner/ledger serialization, and an observe-only socket transport.
Original failed reconstruction remains indeterminate. Native effects, replay, cleanup, reboot and
success synthesis are not part of this operation.

Fabricated tests exercise zero-permit and direct-first-ACK history, new-boot eligibility versus
same-boot refusal, partial transaction prefixes and final-chain corruption, old control drift,
root/config mismatches, explicit candidate admission, cross-root replay, later legitimate history,
unknown potential writers, offline commands, and a thread-backed transport without process launch.

The actual machine historical codec/config spelling was not available as an inspectable portable
contract. Rather than infer JSON pointers or retrofit authority into old worker records, the
implementation rejects unsupported bytes and exposes a finite prospective/test codec. This is
an explicit remaining implementation/qualification limit, not a completed historical recovery path.
The machine producer/closed loader and State legacy adoption remain with their owner. Detailed
interfaces and constraints are in `docs/project/resolution-protocol.md` (checkout-only; packaging
metadata was outside this change's file scope).

No native profile/ledger/compositor was accessed, no source-policy bypass was added, and no live
activation, application effect, commit or release was performed. Test/CI results are reported by
the executing agent, not inferred from these notes.

## Later implementation and overview reconciliation

The paragraphs above describe the initial delivery stage. Subsequent implementation added exact
retained owner-history decoding, including supported later completed history, and an explicit
machine configuration binding. The prospective codec remains separate and test-only. The current
resolution protocol documents these implemented boundaries; README and architecture now agree
with it rather than describing the initial decoder gap as current. Fabricated historical-byte
oracles do not qualify a live machine attempt, prove descendant settlement, or authorize effects.
