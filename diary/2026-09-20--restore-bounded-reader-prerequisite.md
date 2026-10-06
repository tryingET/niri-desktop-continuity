# Restore bounded-reader prerequisite

Implemented separate envelope routing and per-validation-pass dependency budgets without changing
the legacy width family. The new-family semantic hook remains unconditionally refusing; there is
no v2 proposal, approval, apply or replay completion in this slice.

The initial handwritten routing regression failed because the old structural reader opened the
first ordinary payload before routing the remaining envelopes. Routing now pauses at each new-family
boundary and resumes only after the prefix validation hook. Repeated-boundary tests replace that
refusing hook solely to test IO ordering; they are not full-lifecycle proof. The earlier five-record
lifecycle RED remains retained as unfulfilled evidence, outside collected source tests.

Separate counters expose routing, unique dependency reservations, repeated validation reads and
barrier attempts. Tiny injected limits exercise pre-read rejection and prospective commit capacity.
Tests cover raw/identity drift, per-pass memo retirement, original Store/path distinctions,
legacy-only suffix compatibility, and refusal through the actual load/admit/writer/replay paths.
Existing handwritten v1 lifecycle/replay fixtures remain the legacy semantic oracle.

Resource limits and the phase-two integration obligations are documented in
[architecture](../docs/architecture.md#bounded-reader-prerequisite-v2-authority-still-blocked).
512 MiB bounds unique raw closure bytes per validation pass, not all IO or decoded Python memory.
No native qualification, deployment, Store change or broad full-CI gate is claimed by this slice.
