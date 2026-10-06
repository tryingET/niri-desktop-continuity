# Root-init-free v3 scope implementation

Replaced the live init anchor with genuine pinned self coordinates and singleton NSpid/NStgid,
per-component UNIQUE mount provenance, retained process directories and active pidfd namespace
refresh. Structural kernel ownership is distinct from same-user process and system ELF ownership.
The v3-only ELF route uses a held parent, pinned link, guarded second lookup and FD-taking Image.
The second lookup retains the documented transient privileged-substitution race; no sandbox claim.

Kept the original wire golden and added a separate new-method golden, explicit unfinished-old
refusal, completed old replay and mixed-history coverage. Receipt methods bind to their plan.
Repeated complete proof cycles and both late publication vetoes remain in place.

A genuine pre-implementation product test passed its accessible-init control and failed at init
EACCES in a mapped nested-user fixture. The unchanged expected-positive test now passes; the full
actual current proof also passes there with a cooperative peer. This is isolated kernel evidence,
not ordinary-user host qualification or permission for live accounting/deployment. Independent
inspection, exact native authorization and desktop/session qualification remain separate.
