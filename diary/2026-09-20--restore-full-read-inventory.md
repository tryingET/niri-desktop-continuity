---
summary: "Full-inventory veto on every restore read, bound to the incoming coherent capture."
read_when:
  - "You review prelaunch or post-effect output-inventory drift handling."
type: "implementation"
---

# Full-read inventory correction

Prior manifests and public source hashes matched before editing; historical evidence remains unchanged.
Handwritten RED schedules on both supported test interpreters exposed a remaining gap: changed disabled
manufacturer, malformed VRR flag or added disabled output at the prelaunch refresh were discarded by
workspace-only projection, permitting a launch. The first Layout read could also replace already
observed coherent-capture metadata. Ordinary read/fresh and unavailable-inventory probes exposed the
same incomplete guard. Initial malformed metadata was already rejected; it is not claimed as a RED.

The sole production change is in restore_layout: freeze validated full metadata from the incoming
coherent capture and compare every subsequent sample against it, including the constructor's first
read, prelaunch/pre-effect fresh reads, effect postconditions and error fallback. Full-inventory failure
is sticky for that Layout: it preserves the frozen baseline and refuses further reads without consuming
a later recovered reply. Missing capture inventory or output-query transport is refused, never invented.
Equivalent list/name-bearing mapping representations and numeric scale equality continue to work.
Only association may classify the previously approved narrow split family; no other read gains retry
or relational tolerance. Geometry/history/schema, absolute deadlines and exceptional teardown remain
unchanged. A post-effect failure retains uncertainty; there is no retry, rollback, cleanup or success.

Fabricated integration schedules assert zero host launches, zero bootstrap/exec permits and an
unconsumed recovery reply after prelaunch failure. Additional schedules cover pre-effect and
postcondition refusal without corrective effects or error-read laundering. Existing installed-wheel
single-host split continuation includes an unchanged disabled output and real cooperative ELF exec.
The test oracles do not derive expected inventories from the production classifier. A legacy
zero-launch fixture needed an explicit output-query method matching the inventory it already exposed
in its fabricated capture; no production unavailable-inventory fallback or test-assertion change was
used to restore those tests.

Independent re-review remains required; this record does not close the reviewer's finding. No full CI,
native canary, private profile/history/fence, service, settlement, deployment, commit or task-state
mutation was performed. Polling and non-preemptible-call limits remain unchanged.
