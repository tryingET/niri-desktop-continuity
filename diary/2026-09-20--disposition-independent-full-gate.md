---
summary: "Disposition corrections independently re-reviewed; full isolated CI passed, native disposition unperformed."
type: "validation"
---

# Disposition independent re-review and full gate

Independent re-review closed the four defects documented in
[review corrections](2026-09-20--restore-disposition-review-corrections.md): durability-gated
admission, prepublication live validation, equal Store artifact durability and held host cwd proof.
The reviewer verified stable source/test hashes and independently ran 12 adversarial probes plus
149 disposition/Store regression cases, all passing without skips. No blocker was found within that
bounded scope; this is not an exhaustive security or native compatibility certification.

Parent-run `env -u NIRI_SOCKET UV_OFFLINE=1 just ci` passed:

- 1,130 tests in 692.95 seconds;
- Ruff and formatting;
- portable-source/privacy and Python 3.11 syntax checks;
- wheel and sdist builds;
- isolated installed-wheel console smoke.

The reviewed manifest remained unchanged through the full gate. Public status documentation and
this diary were updated afterward; these documentation-only changes receive separate static and
packaging checks, not a claim that the earlier full gate ran on subsequent documentation bytes.

No real compositor, private original witness/history, live fence, login installation, service or
canonical source checkout was changed by this verification. The earlier native attempt remains
interrupted, and its corrected width handling has not passed a fresh native test. Browser/general
application restoration remains an unsupported candidate gap, not completed restoration.

Next: separately authorized inspection of original synchronous invocation witnesses, then an exact
private disposition proposal for operator approval. Accounting-only disposition must retain partial
status and old immutable evidence, and cannot authorize launch/layout/retry or deployment. A fresh
native canary and later promotion each require their own approval. The non-atomic final live-check
interval, trusted witness provenance and lack of physical power-loss qualification remain limits.
