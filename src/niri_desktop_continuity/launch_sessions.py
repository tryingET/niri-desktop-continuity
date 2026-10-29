"""Agent sessions a terminal tab can resume: Claude's registry, Pi's presence and the
declarations the SessionStart hook writes. Nothing here launches anything."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from .launch_proc import TERMINAL_MARKERS, read_cwd

# Coding agents, by process name. Rerunning an agent's command line would replay its opening
# prompt, so an agent comes back only through a session it announced (`hook`) or a built-in
# reader (Claude registry, Pi presence). Adding an agent is one line here, never a module.
AGENT_NAMES = {
    "claude": "claude",
    "codex": "codex",
    "pi": "pi",
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
    "angelx": ["angelx", "--resume", "{id}"],
}
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}")


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
