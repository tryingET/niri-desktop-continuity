---
summary: "Native agent resume test (pi, Claude Code, nodecode) in a nested Niri, and the foreground-job rule for a terminal tab's command."
read_when:
  - "Changing how a terminal tab's command is recorded."
  - "Testing agent session resume on a real compositor."
type: "diary"
---

# Agent resume test and the foreground job

## Native agent resume (2026-10-28)

A nested Niri, started with the outer Niri's environment, held three Ghostty tabs: pi and Claude
Code, each after one short turn, and nodecode on a separate profile. Capture recorded
`pi --session <file>` from pi's presence file and `claude --resume <id>` from Claude's registry;
the `SessionStart` hook had declared the same Claude session. The tabs were closed and
`restore --apply` reopened both agents on their sessions, with the earlier conversation on screen,
and nodecode as `nodecode -p <profile>` in its directory. nodecode does not tell other programs
which session a tab holds, so it comes back as its shell, not as a particular conversation.

- Started from inside a Claude Code session, the nested compositor first passed that session's
  `CLAUDE_CODE_*` variables to its clients, and the test Claude turned transcript saving off. Niri
  gives the apps it spawns its own environment, so a real login or `restore --apply` is not
  affected; the test then used the outer Niri's environment.
- Inside the nested compositor parked on a hidden workspace, Ghostty windows sometimes appeared
  only after about 30 s, past the 25 s spawn timeout, and one run ended `reopened-partially`. On a
  real desktop they appear within about a second; the later runs used `--spawn-timeout 90`.

## The foreground job

On the real desktop a nodecode tab (`start.sh` runs nodecode, which forked `setsid -w nodecode
serve` into a group and session of its own) was recorded as that server, the innermost process. A
login would have opened a terminal running it headless. A tab without an agent session is now
recorded as the job in its terminal's foreground: the job's leader as it was started (`bash
start.sh`, `just dev`), unless that is the interactive shell, and then the job's innermost program
as before. Background jobs no longer become the command. Capture reads each process's group and
the terminal's foreground group from `/proc`; nothing new is stored, because the strict engine
checks the exact fields of the stored inventory. Without readable job control, or when a pid now
names another process, the earlier rule applies unchanged.

Evidence: handwritten scenario tests, four of which fail on the previous code while the fallback
case passes, and a kernel oracle (`os.getpgrp`) for the group reader. A read-only capture of the
real desktop changed exactly three of 56 recipes: two `python3 -m http.server` helpers became the
`just dev` that started them, and the nodecode server became `bash start.sh`. In a nested Niri the
same `start.sh` pattern was recorded as the script, reopened with its own nodecode home, and stayed
the same after a second reopen (Ghostty's bash integration adds `--posix` once, not again).

Full gate on the fix, in a clean clone with a `/usr` Python 3.14, a clean environment and a private
offline cache: 3,015 tests passed, the installed-wheel query case once its cache also held the
package index. Ruff, formatting, the wheel and sdist build, and the installed-wheel smoke passed.
The portable-source check flagged a fabricated home path in the new test; it passed once that was
renamed. Both machines now run this wheel, and a capture through the user service recorded the
nodecode tab as `bash start.sh`.
