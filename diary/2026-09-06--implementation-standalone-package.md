---
summary: "Initial standalone Niri/Linux package, safety gates and isolated distribution validation."
read_when:
  - "You review the initial package extraction and its proof boundaries."
type: "implementation"
---

# Standalone package

Scaffolded using `tpl-project-repo`, then bounded to a standalone Apache-2.0 Python tool for
Niri/Linux only. No cross-platform framework or runtime dependencies. Internal task/database
helpers and unrelated vendored tooling were not retained in the public product. Immutable local
template context was left untouched and excluded from Git and distributions. Copier provenance
uses a relative source, never a maintainer's absolute filesystem path.

Runtime and map assets are packaged together. The application-discovery probe hashes binaries
without executing them; versions remain unknown. Private state and per-compositor writer-lock
namespaces belong to the standalone tool. No private machine integration is imported. Existing
approval, expiry, replay, focus/state validation and effect-indeterminate receipt behavior remain.
All restart/migration is blocked and real layout action is still an explicit experimental canary.

Validation includes 44 synthetic/unit tests, Ruff/format checks, a Python 3.11 syntax and portable
source gate, built wheel/sdist inspection and installed-wheel rendering in an isolated temporary
home with no compositor or inherited application environment. Source archive checks run without
Git metadata and include every helper called by their CI scripts. A separate extracted-source
`just check` passed, confirming the source distribution is not tied to a Git checkout.

A read-only live capture and second comparison also matched all windows/focus in that observation;
its private artifacts were not copied into this repository. This is observation proof, not proof
of restoration, application-state continuity or safe arbitrary restart. No real layout action,
service/configuration change, global installation or publication was performed.

Independent review identified the initially omitted source-archive helper and Git-only checking;
both were fixed before final packaging. The reviewed wheel also ran under Python 3.11 outside
the source checkout. No terminal memory or personal session data was used as a public fixture.
