---
summary: "Narrow optional development-state exclusion and portable distribution privacy checks."
read_when:
  - "You review the development-state exception or package privacy regressions."
type: "reference"
---

# Development-state privacy boundary

The operator approved only an anchored `/.ontology/` ignore for optional workspace-local SCI
state. Product captures and receipts still belong outside the checkout; the Store is unchanged.
No existing development-state payload or live product state was read, moved, deleted or modified.
This is not a runtime, terminal or native-adapter integration change.

The source scanner independently inventories the Git index, so force-tracked `.ontology` entries
fail even when ignored. Only the ignored, untracked root directory is excluded without descending
into it. Nested/exported development state and root symlinks fail. Arbitrary ignore rules cannot
hide other private source data or product runtime directories. Git-free exports have no checkout
cache exemptions. Existing machine-home-path and unreviewed-binary checks remain in force.

The sdist explicitly includes the three linked reconstruction contracts: design, plan and protocol.
Archive metadata validation rejects development/product state, private template context, diaries,
links and special entries in both distributions without opening private payloads. No runtime
dependency or additional CLI was introduced.

Fabricated regression fixtures cover ignored/untracked and force-tracked development state,
unignored and nested/exported variants, tracked/untracked runtime leaks, ignored hidden binary
and home-path sentinels, directory/dangling symlinks, archive privacy entries and each missing
contract independently. Only scratch Git indexes are changed by tests. Real private payloads are
not fixtures. The installed-console smoke retains its fabricated integration boundary.

## Validation evidence

The initial `UV_OFFLINE=1 just ci` passed: lint, formatting (30 files), all 188 tests, Python 3.11 source-syntax
and privacy checks, wheel/sdist build, archive checks and isolated installed-console smoke.
Execution used Python 3.13; this is not a separate Python 3.11 runtime test. Scratch installation
honored `TMPDIR`, used the built wheel offline and confirmed no Python runtime dependencies.

The first full run caught `diary/README.md` in the sdist: Hatch's unanchored `README.md` include
matched nested basenames. Switching to exact `only-include` paths fixed that leak; a handwritten
allowlist regression prevents reverting to recursive basename patterns. The subsequent full gate
confirmed all three contracts shipped and no forbidden state entries in either distribution.

Synthetic validation does not supply live-effect approval, independent safety review or actual
machine integration proof. Archive path sentinels are not a general sensitive-content classifier.

## Fail-closed traversal follow-up

Review identified that `os.walk` silently suppresses directory-enumeration errors by default.
The scanner now supplies an error callback that raises the original `OSError`; `check()` converts
source-enumeration failures to a fixed diagnostic and the script exits nonzero. No OS exception
text, absolute path or payload is included, and a partial inventory cannot report success. This
change does not provide a transactionally consistent filesystem snapshot or broaden traversal
into intentionally excluded development state.

Handwritten scratch fixtures place a fabricated home-path sentinel behind a mode-zero ordinary
directory and restore its original permissions in `finally`. The real-permission test skips only
when the process can bypass those permissions. Separate deterministic `scandir` injections cover
permission denial, disappearance and replacement by a non-directory at the root and within both
ordinary and hidden directories, in Git checkouts and Git-free exports. They run regardless of
privilege. CLI regressions assert the exact static diagnostic, failure exit and no traceback;
an explicit enumeration guard proves ignored root `.ontology` is pruned without opening it.

`UV_OFFLINE=1 uv run --frozen pytest -q tests/test_portability.py tests/test_portability_packages.py`
passed with no skips. Final full validation uses `UV_OFFLINE=1 just ci`. No recovery or adapter
implementation changed; actual optional development state and live product state remain untouched.
