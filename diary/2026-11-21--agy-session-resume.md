---
summary: "Native Antigravity CLI (agy) session resume, session-flag allowlist, multi-window Ghostty matching, and env-wrapper refusal."
read_when:
  - "You change agent session readers, Ghostty title matching, or refusal rules."
type: "diary"
---

# 2026-11-21 — Native `agy` session resume

## Why

Live Antigravity CLI (`agy`) tabs in Ghostty were previously recorded as generic `command` recipes
with their raw launch `argv` (often `env ... agy --model ... -i "<opening prompt>"`). Reopening
after a reboot would have started fresh sessions and replayed every opening prompt instead of
resuming the existing conversations.

## What

- Added `"agy"` to `AGENT_NAMES`, `RESUME_TEMPLATES` (`agy --conversation {id}`), `SESSION_KINDS`,
  and `REOPENS_AS`.
- Added `agy_session(pid, start_ticks)` in `launch_sessions.py`: verifies `comm == "agy"` and
  `start_ticks` from `/proc/<pid>/stat`, finds a single regular same-UID
  `~/.gemini/antigravity-cli/presence/<uuid>.lock` in `/proc/<pid>/fd/*`, verifies an exclusive
  `FLOCK ADVISORY WRITE` lock owned by `pid` on the matching inode in `/proc/<pid>/fdinfo/<fd>`,
  and preserves an explicit allowlist of session-scoped CLI flags (`--model`, `--effort`, `--mode`,
  `--agent`, `--project`, `--add-dir`, `--sandbox`, `--dangerously-skip-permissions`,
  `--remote-agent`, `--remote-control`) while skipping prompt/print/settings flags and their values.
  Missing, stale, deleted, symlinked, unlocked, or ambiguous locks fail closed to
  `agent-session-unannounced`.
- Added read-only `agy_conversation_title(session_id)` against `conversation_summaries.db`
  (`mode=ro`, `PRAGMA query_only = ON`, 200 ms timeout) and 2-pass `window_recipes()` matching
  (explicit session labels first, then path-boundary `cwd`/`~/` title matching).
- Hardened `refusal()` with `_unwrapped_program()` so legacy `command`/`app` recipes behind
  `env [OPT]... [NAME=VALUE]...` are refused rather than replayed.

## Verified

- Unit & oracle suite (`tests/test_reopen_agy.py`), including a real Linux kernel
  `fcntl.flock` -> `/proc/self/fdinfo/<fd>` oracle; `just check` and `just ci` passed.
- End-to-end nested Niri test: launched Ghostty running `agy --model ... -i "..."`, captured
  `kind: "agy"` with `--conversation <uuid> --model ...` (no `-i`), closed the window, ran
  `restore --apply --no-open` (`status: "reopened"`, `placed`), and verified the reopened `agy`
  matched `already-open` on a follow-up dry-run.
