---
summary: "Fabricated login-restore contract coverage and separation of synthetic proof from native acceptance."
read_when:
  - "Reviewing latest-capture selection or same-compositor login skip coverage."
type: "diary"
---

# Login restore contract verification

Added fifteen Given/When/Then CLI cases in
`tests/test_login_restore_contract.py`. They cover latest snapshot pointer selection,
explicit digest selection, missing/malformed pointer refusal, headless input,
same-compositor zero-effect skip, changed compositor identities, readiness timeout,
and identity-read failure. Captures and transport objects are fabricated; no
compositor, service, real profile, user lock directory or application is contacted.

These are **coverage additions**, not a red-green production fix: the current
implementation passed them on first execution. An initial full-CI invocation was
interrupted by a controller timeout and is not passing evidence. A subsequent
complete `UV_OFFLINE=1 just ci` passed: **684 tests**, Ruff, formatting,
portable-source checks, wheel/sdist build and installed-wheel smoke. Runtime
source was unchanged.

Separate scratch-only falsifying probes showed two existing restore defects:

- Given a missing expected-app window and a newly appearing different app, when
  the matching deadline expires, the current matcher returns the unrelated
  window instead of refusing.
- Given three saved browser windows and a fabricated browser restoring two per
  launch, the current executor can launch twice, leave four actual windows,
  record three placed and report success without accounting for the fourth.

Both probes failed their handwritten safety assertions. They are not repaired by
these CLI tests, are not included as failing repository tests, and do not authorize
closing or cleaning up any window. Exact-window ownership and self-restore surplus
handling require a separate bounded implementation and independent review. The
existing fake also exercises mismatched-app fallback, so the two mechanisms have
not yet been proved independent.

Historical real-login evidence belongs in the private runtime Store and external
evidence owner, not this public repository. A receipt count is executor accounting,
not fresh native-session usability, immediate browser uniqueness, or live proof of
the same-instance skip branch. This entry claims no live invocation, installation,
service restart, release or complete qualification.
