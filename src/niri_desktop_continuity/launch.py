"""Per-window reopen recipes derived from same-user process metadata. Nothing here runs anything."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

RECIPE_SCHEMA = "desktop-continuity.launch-recipe.v1"
SHELLS = {"bash", "zsh", "fish", "sh", "dash", "nu", "xonsh"}
TERMINAL_MARKERS = ("ghostty", "foot", "alacritty", "kitty", "wezterm")
CLAUDE_TITLE_PREFIX = "✳ "


def read_cmdline(pid: int) -> list[str]:
    raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    parts = raw.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    return [part.decode("utf-8", "surrogateescape") for part in parts]


def read_cwd(pid: int) -> str | None:
    try:
        return os.readlink(Path("/proc") / str(pid) / "cwd")
    except OSError:
        return None


def children_index(inventory: list[dict]) -> dict[int, list[int]]:
    index: dict[int, list[int]] = {}
    for item in inventory:
        index.setdefault(item["ppid"], []).append(item["pid"])
    return index


def descendants(pid: int, children: dict[int, list[int]]) -> list[int]:
    """Breadth-first same-user descendants; bounded so a fork bomb cannot stall capture."""
    result, queue, seen = [], list(children.get(pid, [])), {pid}
    while queue and len(result) < 4096:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        result.append(current)
        queue.extend(children.get(current, []))
    return result


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


def is_terminal(app_id: str, comm: str) -> bool:
    haystack = f"{app_id} {comm}".lower()
    return any(marker in haystack for marker in TERMINAL_MARKERS)


def terminal_sessions(pid: int, inventory: list[dict]) -> list[dict]:
    """Resumable sessions (or plain leaf commands) running inside one terminal process."""
    by_pid = {item["pid"]: item for item in inventory}
    children = children_index(inventory)
    sessions: list[dict] = []
    claimed: set[int] = set()
    for shell in children.get(pid, []):
        # Each direct child of the terminal is one surface's shell (or the command itself).
        tree = [shell, *descendants(shell, children)]
        found = None
        for candidate in tree:
            found = claude_session(candidate) or pi_session(candidate)
            if found:
                break
        if found is None:
            leaves = [p for p in tree if not children.get(p) and p not in claimed]
            leaf = next((p for p in leaves if by_pid.get(p, {}).get("comm") not in SHELLS), None)
            cwd = read_cwd(leaf if leaf is not None else shell)
            if leaf is None:
                found = {"kind": "shell", "argv": [], "cwd": cwd, "label": None}
            else:
                try:
                    argv = read_cmdline(leaf)
                except OSError:
                    argv = []
                found = {"kind": "command", "argv": argv, "cwd": cwd, "label": None}
        claimed.update(tree)
        sessions.append(found)
    return sessions


def terminal_base_argv(cmdline: list[str]) -> list[str]:
    """Terminal argv without a previous command or working directory."""
    base: list[str] = []
    for arg in cmdline:
        if arg == "-e":
            break
        if arg.startswith("--working-directory"):
            continue
        base.append(arg)
    return base


def matches_title(session: dict, title: str) -> bool:
    labels = session.get("labels") or ([session["label"]] if session.get("label") else [])
    if session["kind"] == "claude" and session.get("label"):
        return title == CLAUDE_TITLE_PREFIX + session["label"] or title == session["label"]
    return any(label and label in title for label in labels)


def terminal_recipe(cmdline: list[str], session: dict | None) -> dict:
    argv = terminal_base_argv(cmdline)
    cwd = session.get("cwd") if session else None
    if cwd:
        argv.append(f"--working-directory={cwd}")
    if session and session.get("argv"):
        argv += ["-e", *session["argv"]]
    return {
        "schema": RECIPE_SCHEMA,
        "kind": session["kind"] if session else "shell",
        "argv": argv,
        "cwd": cwd,
        "label": (session or {}).get("label"),
    }


def app_recipe(cmdline: list[str], cwd: str | None) -> dict:
    return {
        "schema": RECIPE_SCHEMA,
        "kind": "app",
        "argv": list(cmdline),
        "cwd": cwd,
        "label": None,
    }


def unknown_recipe(reason: str) -> dict:
    return {
        "schema": RECIPE_SCHEMA,
        "kind": "unknown",
        "argv": [],
        "cwd": None,
        "label": None,
        "reason": reason,
    }


def window_recipes(
    windows: list[dict], processes: list[dict], inventory: list[dict], titles: dict[int, str]
) -> dict[int, dict]:
    """One recipe per window id. Titles are matched here and never stored."""
    by_pid = {item["pid"]: item for item in processes}
    recipes: dict[int, dict] = {}
    windows_by_pid: dict[int, list[dict]] = {}
    for window in windows:
        pid = window.get("pid")
        if isinstance(pid, int) and pid in by_pid:
            windows_by_pid.setdefault(pid, []).append(window)
        else:
            recipes[window["id"]] = unknown_recipe("process-unavailable")
    for pid, group in windows_by_pid.items():
        process = by_pid[pid]
        try:
            cmdline = read_cmdline(pid)
        except OSError:
            cmdline = []
        if not cmdline:
            for window in group:
                recipes[window["id"]] = unknown_recipe("cmdline-unavailable")
            continue
        group = sorted(group, key=lambda item: item["id"])
        if not is_terminal(group[0]["app_id"], process.get("comm", "")):
            cwd = read_cwd(pid)
            for window in group:
                recipes[window["id"]] = app_recipe(cmdline, cwd)
            continue
        sessions = terminal_sessions(pid, inventory)
        assigned: dict[int, dict] = {}
        remaining = list(sessions)
        if len(group) > 1 or len(sessions) > 1:
            for window in group:
                title = titles.get(window["id"], "")
                match = next((s for s in remaining if matches_title(s, title)), None)
                if match is not None:
                    assigned[window["id"]] = match
                    remaining.remove(match)
        for window in group:
            if window["id"] not in assigned and remaining:
                assigned[window["id"]] = remaining.pop(0)
        for window in group:
            recipe = terminal_recipe(cmdline, assigned.get(window["id"]))
            recipes[window["id"]] = recipe
        if remaining:
            # Sessions in tabs/splits of an already-assigned window reopen as extra windows.
            first = recipes[group[0]["id"]]
            first["extra"] = [terminal_recipe(cmdline, session) for session in remaining]
    return recipes
