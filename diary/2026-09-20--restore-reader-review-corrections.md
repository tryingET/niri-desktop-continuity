# Reader review corrections, before v2 integration

Review found that a stat-size reservation was followed by an unbounded legacy raw read, so growth
could exceed the reserved IO before rejection. It also found retirement gaps before barrier setup,
in batch/prospective failures and during interrupted materialization. New handwritten RED tests
reproduced the over-read, unbounded request and reusable-failed-pass behavior before production edits.

V2 now uses a separate reservation-bound, unbuffered FD reader; the legacy raw reader is unchanged.
Held descriptors, pathname and parent identities are checked before/around/after reads. No request
or returned data exceeds the reserved length, and short reads refuse without retry or an extra probe.
Public pass operations share BaseException retirement while preserving the original exception.
Tests inspect exact requests/returns at open/read boundaries and require both caches to be retired.

The prospective method remains a capacity check, not held capacity. Phase two must freeze the
complete footprint or check it last with no new dependencies before consumption. ReaderStore is
only a guarded interface; full mediation of legacy helpers and semantic closure is still pending.

Original independent probes are retained unchanged. Their three reported retirement failures now
pass; probes observing/injecting the old raw helper need new-seam instrumentation. Those unchanged
failures are reported, not hidden or relabelled as passing. Full v2 remains unconditionally refused;
no lifecycle completion, native qualification, full CI or deployment follows from these corrections.
