"""Agent sessions a terminal tab can resume: Claude's registry, Pi's presence, nodecode's shell
records, Antigravity CLI (agy) presence locks and the declarations the SessionStart hook writes.
Nothing here launches anything."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
from pathlib import Path
from urllib.parse import quote

from .launch_proc import TERMINAL_MARKERS, read_cmdline, read_cwd

# Coding agents, by process name. Rerunning an agent's command line would replay its opening
# prompt, so an agent comes back only through a session it announced (`hook`) or a built-in
# reader (Claude registry, Pi presence, agy presence lock). Adding an agent is one line here,
# never a module.
# nodecode is not listed: its shell takes no prompt, so without a record it reopens as itself.
AGENT_NAMES = {
    "claude": "claude",
    "codex": "codex",
    "pi": "pi",
    "agy": "agy",
    "angel": "angelx",
    "angelx": "angelx",
    "aider": "aider",
    "gemini": "gemini",
    "opencode": "opencode",
    "goose": "goose",
    "crush": "crush",
    "qwen": "qwen",
    "grok": "grok",
    "cursor-agent": "cursor-agent",
}
# How `hook AGENT` turns an announced session ID into a resume command; others pass their own.
RESUME_TEMPLATES = {
    "claude": ["claude", "--resume", "{id}"],
    "codex": ["codex", "resume", "{id}"],
    "agy": ["agy", "--conversation", "{id}"],
    "angelx": ["angelx", "--resume", "{id}"],
}
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}")
AGY_SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# Explicit allowlist of session-scoped `agy` CLI flags preserved across resume.
# Prompt/one-shot/settings flags are skipped with their values so prompt text is never replayed.
AGY_BOOL_FLAGS = (
    "--dangerously-skip-permissions",
    "--sandbox",
    "--remote-agent",
    "--remote-control",
)
AGY_VALUE_FLAGS = ("--model", "--effort", "--mode", "--agent", "--project")
AGY_REPEAT_VALUE_FLAGS = ("--add-dir",)
AGY_SKIP_VALUE_FLAGS = frozenset(
    {
        "-i",
        "--prompt-interactive",
        "-p",
        "--print",
        "--prompt",
        "--conversation",
        "--log-file",
        "--settings",
        "--input-format",
        "--output-format",
        "--json-schema",
        "--print-timeout",
    }
)


def claude_registry_root() -> Path:
    return Path.home() / ".claude" / "sessions"


def pi_presence_root() -> Path:
    override = os.environ.get("PI_SESSION_PRESENCE_DIR")
    if override:
        return Path(override)
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "pi-session-presence"
    return Path.home() / ".local" / "state" / "pi-session-presence"


def nodecode_presence_root() -> Path | None:
    # nodecode writes these only where XDG_RUNTIME_DIR is absolute; there is no fallback.
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    return Path(runtime) / "nodecode" / "shells" if runtime.startswith("/") else None


def agy_presence_root() -> Path:
    return Path.home() / ".gemini" / "antigravity-cli" / "presence"


def agy_conversation_title(session_id: str) -> str | None:
    """Conversation title from agy's private summary DB, read-only with bounded timeout."""
    if not AGY_SESSION_ID.fullmatch(session_id):
        return None
    db_path = agy_presence_root().parent / "conversation_summaries.db"
    try:
        info = db_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            return None
        uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=0.2)
    except (OSError, sqlite3.Error):
        return None
    try:
        con.execute("PRAGMA query_only = ON")
        row = con.execute(
            "SELECT title FROM conversation_summaries WHERE conversation_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    if not row or not isinstance(row[0], str):
        return None
    title = row[0].strip()
    return title or None


def declaration_root() -> Path:
    # Per boot, like the processes it names: the runtime directory is emptied at reboot.
    return Path(f"/run/user/{os.getuid()}") / "niri-desktop-continuity-declared"


def _private_json(path: Path) -> dict | None:
    try:
        info = path.lstat()
        if info.st_uid != os.getuid() or info.st_size > 1024 * 1024:
            return None
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def claude_project_slug(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "-", cwd)


def claude_ai_title(session_id: str, cwd: str) -> str | None:
    """Last AI-assigned title from the private transcript, scanned as lines, never loaded whole."""
    if not re.fullmatch(r"[0-9a-f-]{36}", session_id):
        return None
    path = Path.home() / ".claude" / "projects" / claude_project_slug(cwd) / f"{session_id}.jsonl"
    title = None
    try:
        with path.open("rb") as stream:
            for line in stream:
                if b'"ai-title"' not in line and b'"customTitle"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") == "ai-title" and record.get("aiTitle"):
                    title = str(record["aiTitle"])
                elif record.get("customTitle"):
                    title = str(record["customTitle"])
    except OSError:
        return None
    return title


def claude_session(pid: int) -> dict | None:
    value = _private_json(claude_registry_root() / f"{pid}.json")
    if not value or value.get("pid") != pid:
        return None
    session_id, cwd = value.get("sessionId"), value.get("cwd")
    if not isinstance(session_id, str) or not isinstance(cwd, str):
        return None
    return {
        "kind": "claude",
        "argv": ["claude", "--resume", session_id],
        "cwd": cwd,
        "label": claude_ai_title(session_id, cwd),
    }


def pi_session(pid: int) -> dict | None:
    value = _private_json(pi_presence_root() / f"{pid}.json")
    if not value or value.get("pid") != pid:
        return None
    argv, cwd = value.get("resumeArgv"), value.get("cwd")
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        return None
    if not isinstance(cwd, str):
        return None
    labels = [
        str(value[key])
        for key in ("sessionIdentityToken", "sessionName", "sessionIdShort")
        if value.get(key)
    ]
    return {
        "kind": "pi",
        "argv": list(argv),
        "cwd": cwd,
        "label": labels[0] if labels else None,
        "labels": labels,
    }


def nodecode_session(pid: int, start_ticks: int | None) -> dict | None:
    """The session a nodecode shell says it is on (nodecode-shell record, version 1)."""
    root = nodecode_presence_root()
    if root is None or start_ticks is None:
        return None
    value = _private_json(root / f"{pid}.json")
    # The shell's start time pins its record: a stale record under a reused pid never matches.
    if (
        not value
        or value.get("version") != 1
        or value.get("kind") != "nodecode-shell"
        or value.get("pid") != pid
        or value.get("start_ticks") != start_ticks
    ):
        return None
    session_id, argv, cwd = value.get("session_id"), value.get("resume_argv"), value.get("cwd")
    if not (isinstance(session_id, str) and SESSION_ID.fullmatch(session_id)):
        return None
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv)):
        return None
    if session_id not in argv or not (isinstance(cwd, str) and cwd.startswith("/")):
        return None
    return {"kind": "nodecode", "argv": list(argv), "cwd": cwd, "label": None}


def _read_link(path: Path) -> str | None:
    try:
        return os.readlink(path)
    except OSError:
        return None


def _read_proc_cmdline(pid: int, proc_root: Path | None) -> list[str]:
    if proc_root is None:
        try:
            return read_cmdline(pid)
        except OSError:
            return []
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return []
    parts = raw.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    return [part.decode("utf-8", "surrogateescape") for part in parts]


def _agy_resume_flags(cmdline: list[str]) -> list[str]:
    """Extract allowlisted session-scoped flags from an `agy` cmdline in canonical order."""
    args = cmdline[1:]
    bools: set[str] = set()
    values: dict[str, str] = {}
    repeated: dict[str, list[str]] = {flag: [] for flag in AGY_REPEAT_VALUE_FLAGS}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            break
        if arg in AGY_SKIP_VALUE_FLAGS:
            index += 2
            continue
        if "=" in arg and arg.split("=", 1)[0] in AGY_SKIP_VALUE_FLAGS:
            index += 1
            continue
        if arg in AGY_BOOL_FLAGS:
            bools.add(arg)
            index += 1
            continue
        matched = False
        for flag in AGY_VALUE_FLAGS:
            if arg == flag and index + 1 < len(args):
                val = args[index + 1]
                if val:
                    values[flag] = val
                index += 2
                matched = True
                break
            if arg.startswith(flag + "="):
                val = arg.split("=", 1)[1]
                if val:
                    values[flag] = val
                index += 1
                matched = True
                break
        if matched:
            continue
        for flag in AGY_REPEAT_VALUE_FLAGS:
            if arg == flag and index + 1 < len(args):
                val = args[index + 1]
                if val and val not in repeated[flag]:
                    repeated[flag].append(val)
                index += 2
                matched = True
                break
            if arg.startswith(flag + "="):
                val = arg.split("=", 1)[1]
                if val and val not in repeated[flag]:
                    repeated[flag].append(val)
                index += 1
                matched = True
                break
        if matched:
            continue
        index += 1
    result: list[str] = []
    for flag in AGY_VALUE_FLAGS:
        if flag in values:
            result.extend([flag, values[flag]])
    for flag in AGY_REPEAT_VALUE_FLAGS:
        for val in repeated[flag]:
            result.extend([flag, val])
    for flag in AGY_BOOL_FLAGS:
        if flag in bools:
            result.append(flag)
    return result


def _fdinfo_holds_flock(text: str, pid: int, inode: int) -> bool:
    """Whether a /proc/<pid>/fdinfo/<fd> file shows an exclusive FLOCK lock held by pid on inode."""
    pid_text = str(pid)
    inode_suffix = f":{inode}"
    for line in text.splitlines():
        if not line.startswith("lock:"):
            continue
        parts = line.split()
        if (
            len(parts) >= 7
            and parts[2] == "FLOCK"
            and parts[4] == "WRITE"
            and parts[5] == pid_text
            and parts[6].endswith(inode_suffix)
        ):
            return True
    return False


def agy_session(pid: int, start_ticks: int | None, *, proc_root: Path | None = None) -> dict | None:
    """The conversation an Antigravity CLI (agy) process holds an exclusive presence lock for."""
    if start_ticks is None:
        return None
    proc_dir = (proc_root or Path("/proc")) / str(pid)
    try:
        raw = (proc_dir / "stat").read_text()
        open_paren = raw.index("(")
        close_paren = raw.rindex(")")
        comm = raw[open_paren + 1 : close_paren]
        fields = raw[close_paren + 2 :].split()
        if comm.lower() != "agy" or int(fields[19]) != start_ticks:
            return None
    except (OSError, ValueError, IndexError):
        return None
    uid = os.getuid()
    root = agy_presence_root()
    try:
        root_info = root.stat()
        if root_info.st_uid != uid or not stat.S_ISDIR(root_info.st_mode):
            return None
        root_resolved = root.resolve()
        fd_entries = list((proc_dir / "fd").iterdir())
    except OSError:
        return None
    matches: set[str] = set()
    for fd_entry in fd_entries:
        target = _read_link(fd_entry)
        if not target or target.endswith(" (deleted)"):
            continue
        target_path = Path(target)
        if target_path.parent != root_resolved or not target_path.name.endswith(".lock"):
            continue
        session_id = target_path.name[:-5]
        if not AGY_SESSION_ID.fullmatch(session_id):
            continue
        try:
            info = target_path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != uid:
                continue
            fdinfo = (proc_dir / "fdinfo" / fd_entry.name).read_text()
        except OSError:
            continue
        if _fdinfo_holds_flock(fdinfo, pid, info.st_ino):
            matches.add(session_id)
    if len(matches) != 1:
        return None
    cwd = read_cwd(pid) if proc_root is None else _read_link(proc_dir / "cwd")
    if not (isinstance(cwd, str) and cwd.startswith("/")):
        return None
    session_id = next(iter(matches))
    flags = _agy_resume_flags(_read_proc_cmdline(pid, proc_root))
    title = agy_conversation_title(session_id)
    labels = [value for value in (title, session_id, session_id[:8]) if value]
    return {
        "kind": "agy",
        "argv": ["agy", "--conversation", session_id, *flags],
        "cwd": cwd,
        "label": title,
        "labels": labels,
    }


def declared_session(pid: int, start_ticks: int | None) -> dict | None:
    """An operator-declared launch for a process that cannot be resumed natively."""
    if start_ticks is None:
        return None
    value = _private_json(declaration_root() / f"{pid}.json")
    # The start time pins the declaration to one process: a reused pid never matches.
    if not value or value.get("pid") != pid or value.get("start_ticks") != start_ticks:
        return None
    argv, cwd, label = value.get("argv"), value.get("cwd"), value.get("label")
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        return None
    if not (isinstance(cwd, str) and cwd.startswith("/")):
        return None
    return {
        "kind": "declared",
        "argv": list(argv),
        "cwd": cwd,
        "label": label if isinstance(label, str) else None,
    }


def declare(pid: int, argv: list[str], *, cwd: str | None = None, label: str | None = None) -> dict:
    """Record how to reopen one live process's surface, e.g. a fresh session from a handoff."""
    from .probe import proc_stat
    from .store import private_directory

    if not argv or not all(isinstance(a, str) and a for a in argv):
        raise ValueError("a non-empty launch command is required")
    process = proc_stat(pid)  # same-user processes only
    cwd = cwd or read_cwd(pid)
    if not cwd or not cwd.startswith("/"):
        raise ValueError("working directory must be absolute")
    value = {
        "pid": pid,
        "start_ticks": process["start_ticks"],
        "argv": list(argv),
        "cwd": cwd,
        "label": label,
    }
    root = declaration_root()
    private_directory(root)
    temporary = root / f".{pid}.{os.getpid()}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
    os.replace(temporary, root / f"{pid}.json")
    return value


def inside_terminal(pid: int, depth: int = 16) -> bool:
    """Whether a process runs inside a terminal window, which is what capture can reopen."""
    from .probe import proc_stat

    for _ in range(depth):
        pid = proc_stat(pid)["ppid"]
        if pid <= 1:
            return False
        comm = (Path("/proc") / str(pid) / "comm").read_text().strip().lower()
        if any(marker in comm for marker in TERMINAL_MARKERS):
            return True
    return False


def agent_ancestor(agent: str, pid: int, depth: int = 8) -> int:
    """The nearest ancestor of a hook process that is the agent itself (hooks run via a shell)."""
    from .probe import proc_stat

    names = {comm for comm, name in AGENT_NAMES.items() if name == agent} or {agent}
    for _ in range(depth):
        if pid <= 1:
            break
        if (Path("/proc") / str(pid) / "comm").read_text().strip().lower() in names:
            return pid
        pid = proc_stat(pid)["ppid"]
    raise ValueError(f"no {agent} process among this hook's ancestors")


def hook_declaration(
    agent: str, payload: dict, template: list[str] | None, pid: int
) -> dict | None:
    """Declare the resume command for the session an agent's SessionStart hook announced.

    A new session or thread switch fires the hook again and replaces the record, so the
    declaration always names the current session. It is pinned to the agent's process start.
    None when the agent runs outside a terminal (for example Codex's shared app-server daemon):
    no terminal tab could be matched to it, so nothing is declared.
    """
    session_id, cwd = payload.get("session_id"), payload.get("cwd")
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        raise ValueError("hook input needs a plain session_id")
    template = template or RESUME_TEMPLATES.get(agent)
    if not template or not any("{id}" in arg for arg in template):
        raise ValueError(f"no resume template for {agent}; pass -- COMMAND ... {{id}}")
    argv = [arg.replace("{id}", session_id) for arg in template]
    argv[0] = shutil.which(argv[0]) or argv[0]  # niri's PATH can differ from the agent's
    cwd = cwd if isinstance(cwd, str) and cwd.startswith("/") else None
    owner = agent_ancestor(agent, pid)
    if not inside_terminal(owner):
        return None
    return declare(owner, argv, cwd=cwd)


def clear_declaration(pid: int) -> bool:
    try:
        (declaration_root() / f"{pid}.json").unlink()
    except FileNotFoundError:
        return False
    return True
