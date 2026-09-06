---
summary: "System4D: Engine (states/invariants/lifecycle) for this project."
read_when:
  - "When defining invariants and lifecycle"
---

# System4D — Engine

## Invariants
- Observed, desired, approved, executed and verified remain distinct.
- IPC acknowledgment is not proof; unknown effects must not be replayed.
- Application restart remains blocked without exact recovery coverage.
