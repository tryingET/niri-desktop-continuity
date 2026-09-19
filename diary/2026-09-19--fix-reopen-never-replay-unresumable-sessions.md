---
summary: "Recipes no longer replay what cannot be resumed; AppImage and X11 windows; operator-declared reopen for handoffs."
read_when:
  - "You change launch recipes, add a session kind, or wonder why a window came back as `unknown`."
---

# 2026-09-19 — Never replay an unresumable session; declared reopen

## Why

A dry run before a planned reboot showed three recipes that would have done the wrong thing:

- Two Claude windows had been started from inside another Claude session's shell. They inherited
  its child-session environment, so they never wrote a registry entry or a transcript. With no
  registry entry the capture fell back to the leaf command — `claude "<opening prompt>"` — and at
  login would have started the same work over as new sessions. Had the process owned a child (an
  MCP server), the leaf would have been that child's command line instead.
- An AppImage application was recorded under its temporary FUSE mount (`$TMPDIR/.mount_*`), which
  does not survive a reboot.
- An X11 window was recorded as `xwayland-satellite :0 -listenfd …`: Niri reports the bridge as the
  owner of every X11 window.

## What

- A terminal surface whose process tree contains a Claude process without a registry entry is
  `unknown` (`claude-session-unregistered`); nothing in that tree is replayed.
- `app_window_recipe`: an executable under a `.mount_*` point is mapped through
  `/proc/self/mountinfo` to the AppImage its runtime serves and relaunched from the runtime's own
  argv[0] when absolute (often a stable symlink), else the image file; unresolvable → `unknown`.
  A process named `xwayland-satellite` → `unknown` (`xwayland-client`).
- `declare --pid PID [--cwd] [--label] -- COMMAND…` records, in the per-boot runtime directory,
  how to reopen the surface that runs PID when nothing can resume it natively — e.g. a fresh
  session started from a handoff document. Pinned to the process start time, 0600, consulted only
  after the Claude and Pi lookups, kind `declared`. `--clear` removes it.

## Verified

Red first: the new oracles failed on the exact replay (prompt, and the MCP child). Suite 644 passed.
Live: 26 windows captured before a reboot, 25 reopened at login in 49 s on their saved workspaces
in saved column order (one `unknown` X11 window, reported as `no-launch-command`); the two declared
surfaces came back as new sessions started from their handoffs and registered normally.

## Limits

A declaration is operator intent, not recovery: the new session starts from the handoff, not from
the old conversation. X11 applications are still not reopened. The unit reports exit 2 (partial)
whenever any saved window is `unknown`.

## Crystallization candidates

- → docs/learnings: an agent that starts another agent from its own shell hands it the parent's
  environment; start sessions through the compositor instead.
