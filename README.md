# niri-desktop-continuity

[![ci](https://github.com/tryingET/niri-desktop-continuity/actions/workflows/ci.yml/badge.svg)](https://github.com/tryingET/niri-desktop-continuity/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/niri-desktop-continuity)](https://pypi.org/project/niri-desktop-continuity/)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](https://github.com/tryingET/niri-desktop-continuity/blob/main/LICENSE)

**Reboot, log in, and your [niri](https://github.com/YaLTeR/niri) desktop comes back.** Windows
reopen on their workspaces in their column order, Claude Code and Pi sessions resume by id, and
anything that cannot be reopened safely is reported, never guessed.

![Offline preview of a fabricated demo desktop: a project workspace with Claude Code and Pi sessions, a dev server and an X11 IDE, then a browser workspace; each tile says whether it reopens after a reboot](https://raw.githubusercontent.com/tryingET/niri-desktop-continuity/main/docs/assets/preview-map.png)

<sub>The offline preview page for a fabricated demo desktop (not anyone's real one): the first two
of its five workspaces, 23 windows in all. Every tile says how it comes back after a reboot, or
why it will not.</sub>

## Status

This branch brings every application back again. It is the 0.1.2 restorer with its three known
defects fixed: each saved app instance is launched **once** (no second launch after a wait), only
**new windows of that app** are adopted (never an unrelated window), and coding agents are **never
replayed** from their command line. Apps start from their own menu entry, so wrappers, AppImages and
sign-in or deep-link URLs are handled the way you launch them. Saved column widths now account for
window borders, a fix carried over from the strict line. The strict controlled-Ghostty candidate
that preceded it no longer drives `restore`; its reconstruction and disposition commands remain.
Offline tests pass. A real login restore of a mixed desktop has not been run on this branch yet.

## Why

niri's scrolling columns make it easy to build a desktop that is worth keeping: a workspace per
project, terminals running agents and dev servers, a browser and notes beside them. A reboot or a
crash throws all of it away, and rebuilding it by hand, window by window and column by column, takes
longer than the reboot did.

This small tool saves the shape of your desktop every 15 minutes and, at your next login, puts it
back. From a real reboot of the maintainer's desktop:

- **26 windows saved, 25 reopened at login in 49 seconds**, every one on its saved workspace in
  its saved column order.
- Claude Code and Pi sessions **resumed by id**.
- Two sessions that could not be resumed came back as **fresh sessions started from their handoff
  notes** (`declare`), instead of replaying their opening prompts.
- The one miss, an X11 app, was **reported in the receipt, not guessed**.

## Quickstart

Requires Linux, niri and Python 3.11+, with [Ghostty](https://ghostty.org) as your terminal. No
runtime dependencies.

```sh
pipx install niri-desktop-continuity
# or: uv tool install niri-desktop-continuity
```

Every release is also on [GitHub Releases](https://github.com/tryingET/niri-desktop-continuity/releases)
with checksums; what changed is in the [changelog](https://github.com/tryingET/niri-desktop-continuity/blob/main/CHANGELOG.md).

Save your desktop and check what would come back:

```sh
niri-desktop-continuity capture    # save windows, workspaces and a reopen recipe per window
niri-desktop-continuity preview    # write an offline HTML map of the latest capture; open the printed path
niri-desktop-continuity restore    # dry run: the placement plan, as JSON; nothing is launched
```

Reopen it: automatically at every login, which is all most desktops need:

```sh
niri-desktop-continuity autostart --enable --keep-days 3  # capture every 15 min, keep 3 capture days, reopen at login
niri-desktop-continuity restore --apply      # by hand: reopen the latest capture now
```

At login the restore service runs `restore --apply --at-login` for you; it waits for Niri, and
skips when the capture came from the same Niri instance. By hand you need `restore --apply` only
when saved windows are gone while you stay logged in, for example after closing them by mistake,
or to reopen an older capture by its digest. It launches each saved application that is not
running and each saved terminal tab that is not open. A plain shell or command tab cannot be
recognised as already open, so on a desktop where it still runs it opens a second time.

A session that cannot be resumed (for example, a Claude Code session started from inside another
one, which keeps no transcript) is not reopened. If you would rather it came back as a fresh
session, say so while it is still running:

```sh
niri-desktop-continuity declare --pid <pid> -- claude "Continue from docs/handoff.md"
```

`<pid>` is any process in that terminal (for example from `pgrep -a claude`). The declaration
lives until the next reboot, applies only to that exact process, and `declare --pid <pid> --clear`
removes it.

## Check before you restart

`preview` writes a standalone HTML page and prints its path. Its **After a reboot** section lists
every saved window: whether it reopens, as what, with the exact command and directory, or why it
will not.

![The "After a reboot" section of the preview for the same demo desktop: 21 of 23 reopen; an unregistered Claude session and an X11 IDE will not, each with its reason](https://raw.githubusercontent.com/tryingET/niri-desktop-continuity/main/docs/assets/preview-after-reboot.png)

<sub>Same fabricated demo desktop, first workspace's rows. `restore` prints the same plan as
JSON.</sub>

## How it works

Each `capture` reads niri's IPC and same-user process metadata, and records a private *reopen
recipe* per window:

| Kind | How it comes back |
|---|---|
| `app` | launched **once** per saved instance from its desktop entry; its new windows fill the saved places |
| `claude` | Ghostty, running `claude --resume <id>` in the session's directory (Claude Code's session registry) |
| `pi` | Ghostty, running Pi's own resume command (Pi's presence directory) |
| `declared` | Ghostty, running the command you gave `declare`, or the session an agent announced with `hook` |
| `command` | Ghostty, running its last command again (for example `btop` or `npm run dev`) |
| `shell` | Ghostty, opened in the same directory |
| `unknown` | not reopened, with the reason, for example `xwayland-client` or `agent-session-unannounced` |

`restore --apply` takes one lock per compositor, then launches the groups one after another. An app
group is every saved window of one process (for example six Brave windows): it is launched once, and
new windows with that app's ID are adopted until the saved number arrived, they stop arriving, or the
spawn timeout passes. An app that is already running is not launched again and its windows are not
touched. Each saved Ghostty window is its own launch, with your normal Ghostty configuration. Adopted
windows go to their saved workspaces and columns, with saved widths and floating positions, after any
windows that were already open. Every run writes one receipt; exit 2 means some window did not come back.

**Where apps launch from.** First an entry in `$XDG_CONFIG_HOME/niri-desktop-continuity/routes.json`,
then the desktop entry whose name or `StartupWMClass` equals the app ID, or whose program is the
captured executable, then the captured command line without URL or deep-link operands. A second
instance of the same app (for example a second browser profile) keeps its own command line, because one
menu entry cannot tell two profiles apart. `restore` without `--apply` prints each window's route.

```json
{"routes": {"brave-browser": {"argv": ["brave", "--profile-directory=Work"]}}}
```

**Agent sessions.** An agent comes back only through a session it announced. Claude Code and Pi are
read directly. Any agent with session hooks announces itself with one hook line in its own settings,
for example in Claude Code's `settings.json` under `hooks.SessionStart`:
`{"type": "command", "command": "niri-desktop-continuity hook claude"}`. Codex takes the same command
in `~/.codex/hooks.json` (trust it once with `/hooks`; sessions in Codex's shared daemon cannot be tied
to a tab, so use `--no-daemon` where a tab should come back). angelX has tool hooks only, so its tabs
are refused until it can announce a session. Any other agent passes its own resume command:
`niri-desktop-continuity hook myagent -- myagent --resume {id}`. A new session or thread switch
replaces the record, so the newest session wins.
Details: [usage](https://github.com/tryingET/niri-desktop-continuity/blob/main/docs/usage.md#save-and-reopen).

## What it never does

- **Never closes a window, and never moves one that was open before the run.** Reopened columns
  go after them.
- **Never launches an app twice** in one run, and never adopts a window of another app.
- **Never replays what it cannot resume.** A coding agent (Claude, Codex, Pi, angelX, Gemini, Aider
  and others) without an announced session is not relaunched from its command line, which would
  start the same work over. A captured sign-in URL or `app://` deep link is never opened again.
- **Never guesses.** An X11 window (niri reports only the `xwayland-satellite` bridge), an
  unresolvable AppImage mount or an unreadable process is reported with a reason, not launched.
- **Never runs anything at login unless you opt in.** `autostart --enable` writes three systemd user
  units, `--disable` removes them. Nothing else installs a service or edits your configuration.
- **Never executes a discovered binary while capturing.** Executables are hashed, not run.
- **Makes no network requests of its own.** No telemetry, no daemon. The preview is static HTML
  with no scripts or remote assets, and no browser is launched for you.
- **Never reads terminal contents or browser profiles.** Session ids come from Claude Code's
  session registry and Pi's presence files. From a Claude Code transcript it takes only the
  session title, to tell apart windows of one terminal process.

Records stay private: `0700` directories and `0600` files under
`$XDG_STATE_HOME/niri-desktop-continuity` (default `~/.local/state/niri-desktop-continuity`, or
`--state-root <dir>`). Window titles and session titles are redacted unless you
`capture --include-titles`. Recipes still contain command lines and working directories, so treat
captures and previews as private and do not publish them.

## Honest limits

- **niri on Linux only.** No other compositor or platform is planned. Alpha software.
- **Reopening is not restoring memory.** Applications bring back their own content. Unsaved drafts,
  scrollback, shell state and the order of hidden tabs are not recovered.
- **X11 applications are not reopened**, because niri does not reveal which X11 program owns a
  window.
- **Sessions inside terminals need Ghostty.** Other terminals (kitty, WezTerm, foot, Alacritty)
  reopen like any app, from their own entry, without their sessions. In Ghostty, Claude Code, Pi and
  hook-announced agents resume by id; other programs get their last command run again, or a shell in
  the same directory. Sessions found in extra tabs of one Ghostty window reopen as separate windows.
- **Apps decide how many windows they reopen.** A browser that restores fewer windows than were saved
  leaves the rest reported as `not-detected`; it is never launched a second time. Extra windows stay
  where the app put them.
- **Placement follows logical workspace order on the current output.** Normal Niri empty-workspace
  creation/cleanup is supported; there is no arbitrary workspace-creation feature or source-monitor
  affinity restoration. Protected workspace names are not changed.
- **Saved widths and floating positions come back; tile heights do not.** A window that cannot be
  placed in its saved column goes to the end of its workspace.
- **Stay idle while it arranges columns** (usually under a minute). niri has no atomic
  focus-and-move, so input during the run can land in the wrong column.
- Exact restart or migration of a still-running window is **not** supported and stays blocked.

## Beyond reopening

The same CLI also plans blocked restart proposals and has a loss-bounded saved-conversation
reconstruction path, which needs a separately owned adapter that does not ship here. It also has
an experimental single-column reorder. None of these is needed to save and reopen a desktop. See
[planning, reconstruction and resolution](https://github.com/tryingET/niri-desktop-continuity/blob/main/docs/recovery.md).

## Develop

```sh
uv sync --group dev
just check         # lint, formatting, tests, portable-source/privacy check
just build         # wheel + sdist
just ci            # check + build
just screenshots   # re-render docs/assets from the fabricated demo desktop (Chromium + ImageMagick)
```

Tests never contact a real compositor; [releasing](https://github.com/tryingET/niri-desktop-continuity/blob/main/docs/release.md) describes versions, tags and
rollback. [Architecture](https://github.com/tryingET/niri-desktop-continuity/blob/main/docs/architecture.md) explains the module
boundaries, [DESIGN.md](https://github.com/tryingET/niri-desktop-continuity/blob/main/DESIGN.md) is the preview's visual contract and [usage](https://github.com/tryingET/niri-desktop-continuity/blob/main/docs/usage.md) has
every command's details. Screenshots come only from `scripts/demo-desktop.py`, and
`just check` refuses PNG metadata that could carry private text.

Scaffolded from `tpl-project-repo`, then adapted for a standalone Python package. Copier answers
retain relative template provenance only; template updates are a maintainer concern, not an
installation prerequisite. Private template snapshot context is excluded from version control
and distribution. Apache-2.0: see [LICENSE](https://github.com/tryingET/niri-desktop-continuity/blob/main/LICENSE).


The offline `exec-observed-unassociated` disposition v2 candidate uses explicit
`restore-disposition inspect|propose --family exec-observed-unassociated`; omission preserves v1.
It records partial accounting only, never retries or certifies restored native state. Review
corrections require the actual `launch-indeterminate` witness, exact seven-field segment, tuple-based
process identity and a live/expiry veto after the final capacity check. Earlier wrong-wire fixture
results are not intended-family proof. The corrected implementation passed independent rereview,
installed-wheel lifecycle checks on Python 3.13/3.14 and full isolated CI (1,671 tests).
No live use or deployment is authorized by these offline results.
See [the family contract](docs/usage.md#exec-observed-unassociated-disposition-v2-offline-candidate).
