# Changelog

User-facing changes per release. Versions follow [semantic versioning](https://semver.org);
before 1.0, a minor release may change CLI output or saved-state formats, and its entry says how.
The release process is in [docs/release.md](docs/release.md).

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
