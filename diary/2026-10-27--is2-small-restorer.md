---
summary: "IS-2: ordinary restore returns to the broad 0.1.2 restorer with its three defects fixed, desktop-entry routes and hook-announced agent sessions."
read_when:
  - "Changing how restore launches apps, adopts windows, or resumes agent sessions."
type: "diary"
---

# IS-2 small restorer

The strict controlled-Ghostty candidate had narrowed ordinary restore to Ghostty only, while the
0.1.2 restorer it replaced brought back every app. A design review found that 0.1.2 had three
concrete defects and that the strict line, and the IS-1 specification built on it, answered them
with general machinery: per-app route approvals, association classes, proof schedules, and for
agents, process-descriptor and binary-hash readers. IS-2 fixes the three defects in the broad
restorer instead and makes every app and agent a data row.

## Changes

- `reopen.py` (new) runs `restore`. A saved app instance (the windows of one process) is one group,
  launched once. Only new windows with the group's app ID are adopted, serially per group, until the
  saved count arrives, arrivals stop for 5 s, or the timeout passes. There is no relaunch after a
  wait, and no fallback to an unrelated window. Running apps are skipped. Ghostty windows launch with
  the user's configuration; `--config-default-files=false` from earlier controlled restores is
  dropped.
- `routes.py` (new): a user `routes.json` route, then the desktop entry matched by name,
  `StartupWMClass` or executable, then the captured command line without `://` operands. On a
  real desktop the captured Brave command line was a sign-in URL, and the Grok Bot one a deep
  link that would repeat an action; the AGNT window process was `electron .` inside a dated checkout,
  bypassing its launcher. Entries avoid all three.
- `launch.py`: one agent-name table refuses agent surfaces without an announced session
  (`agent-session-unannounced`). `hook AGENT` reads a `SessionStart` hook's `session_id`, finds the
  agent ancestor and writes the existing start-pinned declaration with the agent's resume template.
  A thread switch fires the hook again, which the descriptor-based Codex candidate could not see.
- Widths: 0.1.2 requested the saved *tile* width as Niri's fixed column width, which is the
  *window* width, so columns came back wider by their border. The strict line measured the
  decoration; `reopen` now does the same (tile minus window width of the seed). The strict installed
  console test caught it when it was repointed at the new engine.
- Captures made by older code may hold an agent tab as a plain `command` recipe with its prompt;
  `launch.refusal` refuses those at plan and preview time, so they are never replayed.
- Effect admission still takes `operation_lock(effectful=True)`, so unresolved strict histories block
  `--apply`. A source with a completed strict attempt returns that historical answer, as before.
- The default snapshot selection with its display-unavailable fallback was carried over from the
  separately deployed selection change, with its tests repointed at the new engine.

## Evidence

New handwritten oracles in `tests/test_reopen_engine.py` cover launch once, partial arrival, foreign
windows, running apps, deep links, wrapper launchers, executable matching, two profiles, routes,
terminals, dry run, fences, agent refusal, hooks, Desktop Entry `Exec` parsing and border-adjusted
widths. The installed-console test now drives the new engine through the real console and real
`niri msg` subprocesses against a fake Niri model. Strict-engine tests that reached the strict
executor through the CLI now call it directly, because they test the disposition family, which keeps it.
Results: the full suite in this worktree (Python 3.14 from `/usr`, clean environment, short real
`TMPDIR`) passed 2,979 tests, including all namespace-jail cases; the four installed-wheel cases that
need an offline build cache were not run. The final agent-command safety net and preview text were
added afterwards and verified with 234 focused tests (engine, preview, reopen, login, selection,
portability). A read-only plan of the newest display-valid snapshot on a real desktop resolved every
one of its 68 windows and tabs (61 terminal launches, 7 apps from their desktop entries) with no
configuration. No real compositor, routes file or lock directory was touched by tests, and no
restore, installation or login change was performed.
