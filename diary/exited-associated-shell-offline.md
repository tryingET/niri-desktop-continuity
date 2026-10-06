# Exited associated-shell accounting — offline implementation

Implemented a distinct closed v3 accounting family, not a present-host fallback or a widening of
v1/v2. An independent historical oracle reached a genuine semantic refusal before implementation;
it now passes read-only inspection. The fixture never derives expected history from the v3 model.

Historical CLI version is an exact two-member object; the direct socket Version remains a string.
The source stays immutable. Only its compositor member supplies version compatibility; the client
member remains validated, pinned provenance. New protected-dimension diagnostics remain unchanged
and are explicitly outside the legacy seven-field witness grammar.

The live-proof boundary now has dedicated read-only transport, scope and proof modules. Tests use
private cooperative processes and AF_UNIX replies, plus a test-owned namespace/init anchor where
ordinary proc permissions prevent opening the host init namespace. Production never changes
namespaces or accepts that test harness through CLI/environment. ABI admission is explicitly narrow.
A transferred-FD counterexample documents the limit of peer credentials rather than hiding it.

Lifecycle tests distinguish historical semantics, raw pin preservation, actual kernel proof,
late authority vetoes, crash fences and ordinary supported continuation. A real executor/bootstrap
failure produces diagnostic-bearing evidence and is a negative compatibility test, not a doctored
legacy witness. The original diagnostic runtime and tests are retained unchanged.

These changes do not authorize native observations/accounting, retry, layout, process termination,
cleanup or deployment. Synthetic qualification, independent implementation inspection and separately
approved native work remain distinct. Exhaustive boundary coverage and final CI results belong to
the retained private execution report, not an assertion of completion in this diary.

Independent inspection found that an optional comparison argument conflated omitted input with
explicit JSON null. A recorded null peer version consequently passed historical admission despite
the closed string contract. The correction uses a distinct omission sentinel; explicit null and
other invalid values must refuse through the decoder, admission, effectful lock, attempt, both
replay paths and inspection. Eight null-case assertions reproduced the defect before the fix.
This illustrates why valid content addresses and green producer tests cannot replace adversarial
checks of recorded proof at every accepting consumer.
