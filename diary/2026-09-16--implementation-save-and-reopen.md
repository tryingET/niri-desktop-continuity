---
summary: "Reopen recipes at capture, a spawn/place/arrange executor, and opt-in login units."
read_when:
  - "You change launch, restore or autostart."
---

# 2026-09-16 — Save and reopen

## Why

After a hard reboot nothing reopened the desktop. The previous owner of that job (an
infrastructure repo) had reduced its login unit to a dry run and its hourly observer overwrote the
last good capture minutes after login. This tool already captured everything needed except *how*
to reopen a window.

## What

- `launch.window_recipes` derives one recipe per window from the observed process tree. Terminal
  windows look through their direct children (one per surface) for a Claude session registry file
  keyed by PID, a Pi presence file keyed by PID, or a leaf command. Single-instance terminals that
  own several windows are matched by title at capture time; titles are not stored.
- `restore.plan_restore` is pure: compact saved workspaces with usable recipes to consecutive
  indices, send unknowns to a new last workspace, protect every live window.
- `restore.restore` spawns, waits for the new window (app-id match first, any new window after the
  timeout), moves it with `--focus false`, then rebuilds columns per workspace after the protected
  columns. Extra sessions from tabs become windows in the same workspace.
- `autostart` writes and enables a capture timer and a `graphical-session.target` restore unit that
  runs `restore --apply --at-login`; `--at-login` skips when the capture came from this compositor.

## Verified

Fabricated oracles for recipes, plan and executor (`tests/test_reopen.py`). Live: a 24-window
capture reopened as 26 windows in 41 s with the saved column order on four workspaces.

## Limits

Browsers and editors restore their own content; a second window of an already running browser is
a fresh window. Hidden tab order, drafts and scrollback are not recovered. A capture taken during a
partial restore replaces the latest pointer; older digests stay restorable.
