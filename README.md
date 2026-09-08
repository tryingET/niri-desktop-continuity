---
summary: "Private maps and explicit continuity planning for Niri on Linux."
read_when:
  - "You install, use or contribute to the standalone tool."
---

# niri-desktop-continuity

**See where your work is before changing your desktop.**

A small, private-by-default CLI for **Niri on Linux**. Capture windows and workspaces, render an
offline map, compare observations, and inspect the consequences of a proposed operation.

**Alpha:** this is not a process backup or a solution for a frozen terminal. Restart and migration
are deliberately blocked: knowing where a window belongs does not prove its tabs, drafts or jobs
can be recovered. No other compositor or platform is planned.

## Install

Requires Python 3.11+ and a running Niri session for live observation. No Python runtime dependencies.
From a checkout or locally built wheel:

```sh
pipx install .
# Or, inside your own virtual environment:
python -m pip install .
niri-desktop-continuity --help
```

Nothing installs a service, edits desktop configuration, starts an application or runs at login.
No public package registry release has been made by this repository bootstrap.

## Capture → inspect → verify

```sh
niri-desktop-continuity capture
# Use the returned snapshot_digest:
niri-desktop-continuity preview <snapshot-digest>
niri-desktop-continuity verify <snapshot-digest>
niri-desktop-continuity history
```

`preview` writes standalone HTML and SVG and returns their paths. Open the HTML yourself; no
browser is launched. Columns run horizontally within workspace rows. Floating/unknown placement
is labelled separately. This is a schematic, not a screenshot. Every observed window remains in
the map; no guessing about application-internal tabs.

Records are private (0700 directories, 0600 files) under
`$XDG_STATE_HOME/niri-desktop-continuity`, falling back to `~/.local/state/niri-desktop-continuity`.
Use `--state-root <private-directory>` before a subcommand for separate storage.
Titles are redacted by default. `capture --include-titles` opts into private labels.

Even redacted captures contain process paths and desktop metadata. **Do not publish real state
files or previews.** The repository and packages contain synthetic tests, not anyone's desktop.

## Proposals are not permissions

```sh
niri-desktop-continuity plan <snapshot-digest> --intent restart --window-id <id>
niri-desktop-continuity preview <plan-digest> --kind plans
```

The proposal shows selection, observed shared-process impact and blockers. All restart/migration
proposals remain blocked because exact application checkpoint/restart adapters are unavailable.
Application versions remain unknown during capture: discovered binaries are **never executed**.
A version selector with no matching known version selects nothing, not a guessed application.

A separate **loss-bounded saved-conversation reconstruction** orchestration path is available
through the same CLI: `plan --intent reconstruct --adapter-config`, exact loss/omission/utility-limit approval,
`reconstruct`, and `verify`/`inspect --kind reconstruction`. It requires a separately reviewed,
owner-established pinned internal adapter profile; **no real machine adapter ships here**.
This public suite exercises fabricated installed-console-script workflows. Separately owned
Pi/Claude/Codex/btop support is **implemented and independently reviewed with isolated integration
tests; native desktop qualification unperformed**. Generic public coverage is not native certification.
See the [coverage table](docs/usage.md#conversationtool-coverage-and-evidence-limits). Exact restart/migration
remain blocked; reconstruction never claims prior memory, drafts, scrollback or hidden-tab order.
See [usage](docs/usage.md) and the [internal protocol](docs/project/2026-09-06-integrated-reconstruction-protocol.md).
Protocol v2 additionally accounts for btop utilities without inventing conversations or running-image
pins. Unobservable capability-bearing btop images require exact separate limit acceptance. Reviewed
recovery code stays pinned; installed OS/Pi/Jiti is an explicitly owner-trusted application platform,
not a total dependency capsule. V1 history remains readable without upgrading its authority.
Implementation is not live-effect approval or independent safety certification.

For saved conversations whose old windows/processes are already gone, the same lifecycle also
supports `plan --intent reconstruct --mode additive --saved-set <digest> --adapter-config ...`.
A separately pinned owner profile resolves the private saved set, distinguishes missing from
already-present refs, and may launch each missing ref once while preserving current windows/focus.
It cannot shut down processes/services or move existing windows; already-present-only sets perform
zero effects. Exact native identity, expiry, approval and replay gates remain. Layout/tab and memory
reconstruction are not claimed. See [additive reopening](docs/usage.md#additive-saved-session-reopening).
This portable contract is covered by fabricated installed-CLI tests, not live native qualification.

There is an experimental, separately approved **within-workspace single-tile column reorder**
path. It uses immutable plans, expiring exact-digest approvals, per-compositor writer exclusion,
fresh-state checks, one-use consumption and effect receipts. Cross-workspace moves, resizing,
multi-tile topology and cross-session restoration are unsupported. Niri's focus-then-move IPC is
not atomic; concurrent user input remains a risk. See [usage and safety](docs/usage.md).

## Develop

```sh
uv sync --group dev
just check         # lint, formatting, tests, portable-source check
just build         # wheel + sdist
just ci            # check + build
```

Tests never send live compositor actions. [Architecture](docs/architecture.md) explains the
boundaries; [DESIGN.md](DESIGN.md) defines the static map's visual contract. Package installation,
tests and builds do not require a private workspace, database, agent harness or company service.

Scaffolded from `tpl-project-repo`, then adapted for a standalone Python package. Copier answers
retain relative template provenance only; template updates are a maintainer concern, not an
installation prerequisite. Private template snapshot context is excluded from version control
and distribution. Apache-2.0: see [LICENSE](LICENSE).
