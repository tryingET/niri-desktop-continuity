---
summary: "Tiny inventory-only integer bound and permanent veto for every validation exception."
read_when:
  - "You review oversized JSON integers or exception propagation during inventory checks."
type: "implementation"
---

# Inventory exception edge correction

The previous full-read manifest and source inventory matched before editing; historical artifacts
remain unchanged. Genuine RED used json.loads to produce positive and negative 10**400 in disabled
output metadata. Prelaunch refused effects, but its implicit float conversion raised OverflowError
without latching the inventory failure, letting error fallback consume a recovered reply. Additional
fault cases demonstrated the same gap for non-ValueError exceptions, including BaseException.

The inventory validator now checks integers explicitly against the exact largest finite Python-float
magnitude, retaining admitted integers unchanged. Larger magnitudes raise ValueError without float
conversion; even just-out-of-range integers are refused rather than rounded into range. Float
finiteness behavior and restore_state.number are unchanged. Layout latches every failed inventory
check before propagating the original exception, including interruptions. Constructor validation
starts latched, clearing only after a valid incoming inventory is frozen. No exception is swallowed,
no recovered sample is consumed after failure, and no success/effect authority is fabricated.

Handwritten tests require preparation only, zero launches/permits/effects, unchanged frozen inventory
and an unconsumed recovery reply. Fault injection checks exact exception identity and persistent
refusal. Boundary tests use a handwritten binary64 limit rather than the production validator.
Only focused new regressions, existing observation/coherence and decoder/history semantic tests run
on both test interpreters, plus static checks. No broad suite or installed-wheel rerun is claimed.

Independent re-review is pending; this diary does not close the finding. No full CI, native/private
state action, task mutation, schema/fence/history/geometry/effect change, deployment or commit occurred.
Polling, conservative metadata equality and non-preemptible-call limitations remain unchanged.
