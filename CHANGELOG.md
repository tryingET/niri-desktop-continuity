# Changelog

User-facing changes per release. Versions follow [semantic versioning](https://semver.org);
before 1.0, a minor release may change CLI output or saved-state formats, and its entry says how.
The release process is in [docs/release.md](docs/release.md).

## [0.2.0] - 2026-10-29

### Changed

- `restore` and the login service run a new reopen engine. Each saved application instance is
  launched once, and only new windows of that application are adopted, until its saved count
  arrives, arrivals stop for 5 s or the spawn timeout passes; nothing is launched a second time and
  no unrelated window is taken. Every window goes back to its saved workspace, column order and
  width. Running applications are skipped (`already-running`), and windows open before the run are
  never moved or closed. The restore receipt now lists launch groups and each window's route
  (`terminal`, `desktop:<entry>`, `argv` or `user`), and a run that places only some windows ends
  `reopened-partially` (exit 2). Column widths no longer come back wider by their border.
- Applications launch from a route in `$XDG_CONFIG_HOME/niri-desktop-continuity/routes.json`, then
  from their desktop entry, then from the captured command line without `://` operands, so a
  browser no longer reopens a sign-in or deep-link URL it was started with.
- Ghostty tabs reopen with your own Ghostty configuration.
- A terminal tab without an agent session is saved as the job in its foreground, as it was started
  (`bash start.sh`, `just dev`), not a helper the program detached (such as a server started with
  `setsid`). A background job (`cmd &`) is no longer reopened as the tab's command.
- A coding agent (Codex, angelX, Aider, Gemini and others) comes back only through a session it
  announced; a tab running one without an announced session is not reopened, so its opening prompt
  is never replayed. Captures from older versions that saved such a tab as a command are refused.
- Without a digest, `restore` uses the latest capture, or the last display-valid one when the latest
  saw no usable display (for example a screen that was off); a digest you give never falls back.
- `restore --apply` refuses while the session is locked, because Niri launches nothing then;
  `--at-login` waits for the unlock.

### Added

- `hook AGENT` for an agent's `SessionStart` hook (Claude Code, Codex, or any agent with
  `-- COMMAND ... {id}`): it records the session a terminal tab holds, so the tab resumes after a
  reboot, and records again when the session changes.
- `capture --keep-days N` and `autostart --enable --keep-days N` keep the snapshots of the N most
  recent days that have captures. A day without captures does not count, and a snapshot that a
  pointer, receipt or other record names is always kept. Without the option nothing is deleted.

## [0.1.2] - 2026-09-19

### Changed

- Releases are built and published by CI from the pushed tag alone: the GitHub Release now carries
  the wheel, sdist and `SHA256SUMS` from the same build that goes to PyPI. The 0.1.1 GitHub Release
  has no attached files (releases here are immutable); its notes list the PyPI digests.
- No change to the tool's behavior.

## [0.1.1] - 2026-09-19

### Changed

- Terminal sessions are read only in Ghostty, by design. Other terminals (kitty, WezTerm, foot,
  Alacritty) now reopen as plain applications with their own command line, instead of receiving
  Ghostty's `--working-directory` and `-e`, which they do not accept. Captures made by 0.1.0 keep
  their old recipes until the next `capture`.

### Added

- On PyPI: `pipx install niri-desktop-continuity`. Each release is built once in CI from its tag,
  attached to the GitHub Release with `SHA256SUMS` and uploaded to PyPI through trusted publishing.
- README links and images are absolute, so the page reads the same on PyPI.

## [0.1.0] - 2026-09-19

First public release. Alpha, for [niri](https://github.com/YaLTeR/niri) on Linux, Python 3.11+,
no runtime dependencies. Install from the release wheel or with
`pipx install git+https://github.com/tryingET/niri-desktop-continuity@v0.1.0`.

### Save and reopen your desktop

- `capture` saves windows, workspaces, column layout and a private reopen recipe per window:
  a Claude Code session (resumed by id), a Pi session, an application command line and working
  directory, a terminal's last command, a shell in the same directory, or a command you gave
  `declare`. Anything else is recorded as `unknown` with a reason.
- `restore` prints the placement plan; `restore --apply` launches each recipe through niri, puts
  the window on its saved workspace, rebuilds the saved column order and widths and re-applies
  workspace names. Windows open before the run are never moved or closed; every run leaves a
  receipt. Browsers, Thunderbird and Obsidian are launched once and restore their own windows.
- `autostart --enable` adds opt-in systemd user units: a capture every 15 minutes and a reopen at
  login when the capture came from a different niri instance. `--disable` removes them.
- `declare --pid PID -- COMMAND` reopens a terminal session that cannot be resumed as a fresh
  command, for example a new session started from a handoff note.
- Applications restart in their saved working directory. Chromium and Electron command lines,
  which those programs rewrite into one process title, are split at a real program file.

### Check before you restart

- `preview` writes an offline HTML/SVG map of the latest capture (or a given digest). Every tile
  says how the window comes back, and an **After a reboot** section lists each window's kind,
  exact command and directory, or why it will not reopen.

### Safety and privacy

- A Claude process without a session registry entry is never replayed from its command line.
  X11 windows (`xwayland-client`) and unresolvable AppImage mounts are reported, not guessed.
- State is private (`0700`/`0600`); window titles and session titles are stored only with
  `capture --include-titles`. No network requests, telemetry or daemon; discovered binaries are
  hashed, never executed.

### Also included, experimental

- Blocked restart proposals, a single-column reorder with exact approvals, and loss-bounded
  reconstruction and resolution lifecycles that need a separately owned adapter (none ships
  here). See [docs/recovery.md](docs/recovery.md).

### Known limits

- Reopening is not restoring memory: unsaved drafts, scrollback and hidden tab order are lost.
- X11 applications are not reopened. Placement is by workspace index; the monitor is not restored.
- Arguments that contained spaces cannot be recovered from a rewritten process title.
- Stay idle while `restore --apply` arranges columns; niri has no atomic focus-and-move.
