---
summary: "nodecode tabs resume their session from the record nodecode's shell writes, pinned to the shell's start time."
read_when:
  - "Changing how terminal tabs find a resumable session, or the nodecode reader."
type: "diary"
---

# nodecode tabs resume from the shell's own record

nodecode now records, per running shell, which session that shell is on:
`$XDG_RUNTIME_DIR/nodecode/shells/<pid>.json` (version 1, kind `nodecode-shell`), written by the
shell itself because only the shell knows its own subscription; a preview follow is never named.
Until then a nodecode tab could only come back as `nodecode [-p profile]`, a fresh shell.

`launch_sessions.nodecode_session(pid, start_ticks)` reads that record next to the Claude and Pi
readers. It is used only when every field agrees with the live process: version and kind, the pid,
the start time (so a record a killed shell left under a reused pid never matches), a plain session
ID, a non-empty `resume_argv` of strings that names that session, and an absolute `cwd`. The
argv is kept as recorded (`nodecode -p NAME resume ID`, or `env NODECODE_HOME=... nodecode ...`).
Records are read only where `XDG_RUNTIME_DIR` is absolute, as nodecode writes them only there.

nodecode is deliberately not in the agent table: its shell takes no opening prompt, so a tab
without a usable record keeps its previous recipe (its shell, in its profile) instead of being
refused. The new recipe kind `nodecode` is a session kind in the reopen plan, so a session that is
already open on the desktop is not launched a second time. The strict engine's own kind list was
left alone; it has no production caller and is due for removal.

Tests fabricate the record and the tab's process tree; the handwritten oracles are the resumed
session and Ghostty argv, the unchanged foreground recipe for every malformed, foreign, stale or
unreadable record and for a missing or relative runtime directory, and the fake-desktop engine's
spawn and `already-open` results. Without the change the four positive tests fail.
