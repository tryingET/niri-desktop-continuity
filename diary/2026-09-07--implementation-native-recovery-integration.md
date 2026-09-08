# Native recovery integration boundary and utility accounting

## Decision and implementation

Amended the design/protocol before implementation: retire exhaustive OS/ELF/Pi/Jiti static
capsules. Keep reviewed Python recovery-control sources closed and pinned, with a declared
owner-trusted installed application platform and independently checked critical file pins.
Machine recipe reuse belongs behind the existing internal endpoint, not a second operator CLI.
No machine source, configuration, native profile or private runtime state was read or changed.

Preserved v1 wire/profile shapes and exact version bindings. Added exact protocol v2 btop utility
identities/proofs, critical platform pins, separate utility-limit approval, independent native
omissions, explicit image coverage and zero-conversation utility-only success. A capability-btop
identity must have no fabricated observed image Pin. Every proof predicate remains mandatory;
accepted limitations cap success. Native image corroboration remains an adapter obligation,
not something public schema validation proves.

Canonical prepared/ready/used/events/terminal records route their exact version. Completed
accounting checks the plan/approval and recomputed receipt too. Non-authorizing diagnostics can
retain historical schema/profile identities after an owner upgrade, without invoking foreign
code or relaxing strict accounting admission. No history is migrated or rewritten.

The effect cap, expiry, locks, fences, pending-heartbeat refusal, replay gates, sanitized diagnostics
and no-retry/no-kill policy remain. All changed files are within the public owner scope; preexisting
uncommitted source is retained, with no Git/authority mutation or publication.

## Evidence and limits

Handwritten utility tests cover observed/capability branches, independent omissions/limits,
zero-session selection, mandatory proof predicates, identity/ref/branch mismatches, interrupted
fresh verification, damaged accounting, platform drift and cross-version confusion. Installed
console smoke now includes v1, v2 observed-image, combined omissions/limits and utility-only cases,
plus damaged v2 accounting. These use fabricated scratch endpoints, not native effect transports.

Full `UV_OFFLINE=1 just ci` passed in a scratch source copy: 262 tests, Ruff lint/format,
Python 3.11 syntax/source privacy and entrypoint checks, wheel/sdist builds and installed-console
v1/v2 smoke. The new utility suite contributes 51 tests. Validation used Python 3.13.12; 3.11
compatibility is syntax-checked, not a separately executed 3.11 runtime suite.

Initial scratch runs exposed copy/setup issues: the sdist input list omits `.gitignore`, which
existing privacy fixtures read; a source export also correctly rejects in-tree validation caches.
The final copy included the existing `.gitignore`, kept venv/Ruff caches outside the export,
disabled ordinary bytecode/pytest caching and made scratch source directories read-only against
isolated fixture subprocess bytecode. No tests/checks were skipped or changed to obtain a pass.
The original source, private state and Git metadata were not cleaned, copied or repaired.

At that implementation checkpoint, independent review had not yet run. Native btop/Ghostty
compatibility, production profile provisioning and live reconstruction were not claimed.

## Independent review, corrections and final validation

Independent review reproduced two defects: utility admission failed to exclude all selected host
PIDs, and inspection could report historical success despite adverse current adapter accounting.
The coordinator now refuses host collisions before approval. Inspection preserves historical status
but reports indeterminate current accounting for interrupted, unresolved or incomplete replies.
Eleven permanent handwritten regressions cover both utility branches and v1/v2 diagnostics, with
immutable terminal evidence and no retry authority.

Independent re-review passed 163 tests, including 22 reviewer cases, and accepted both fixes with
no residual blocker in that scope. The controller ran `UV_OFFLINE=1 just ci` in the actual checkout:
273 tests passed, as did lint/format, Python 3.11 syntax/privacy, sdist/wheel builds and installed
v1/v2 console smoke. Runtime remained Python 3.13.12, not a separately tested 3.11 interpreter.

Source integration and isolated validation are complete. The separately owned machine endpoint
has its own reviewed Pi/btop implementation evidence; it is not included in this public package.
No production configuration/profile, global installation, live reconstruction or publication was
performed. Source remains uncommitted; source/authority ownership is not changed by this note.
