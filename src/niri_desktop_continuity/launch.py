"""Per-window reopen recipes derived from same-user process metadata. Nothing here runs anything."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .launch_proc import TERMINAL_MARKERS as TERMINAL_MARKERS
from .launch_proc import children_index as children_index
from .launch_proc import descendants as descendants
from .launch_proc import read_cmdline as read_cmdline
from .launch_proc import read_cwd as read_cwd
from .launch_proc import read_exe as read_exe
from .launch_sessions import AGENT_NAMES as AGENT_NAMES
from .launch_sessions import claude_session as claude_session
from .launch_sessions import clear_declaration as clear_declaration
from .launch_sessions import declaration_root as declaration_root
from .launch_sessions import declare as declare
from .launch_sessions import declared_session as declared_session
from .launch_sessions import hook_declaration as hook_declaration
from .launch_sessions import pi_session as pi_session

RECIPE_SCHEMA = "desktop-continuity.launch-recipe.v1"
SHELLS = {"bash", "zsh", "fish", "sh", "dash", "nu", "xonsh"}
CLAUDE_TITLE_PREFIX = "✳ "
# Niri reports this X11 bridge, not the X11 application, as the owner of every X11 window.
XWAYLAND_BRIDGE = "xwayland-satellite"
# A type-2 AppImage runs its payload from a temporary FUSE mount named .mount_<name><random>.
APPIMAGE_MOUNT_PREFIX = ".mount_"


def _unescape_mount_field(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def mount_table(path: Path | None = None) -> list[tuple[str, str, str]]:
    """(mount point, filesystem type, source) rows of this process's mount namespace."""
    try:
        text = (path or Path("/proc/self/mountinfo")).read_text()
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        head, separator, tail = line.partition(" - ")
        fields, rest = head.split(), tail.split()
        if not separator or len(fields) < 5 or len(rest) < 2:
            continue
        rows.append((_unescape_mount_field(fields[4]), rest[0], _unescape_mount_field(rest[1])))
    return rows


def refusal(recipe: dict) -> str | None:
    """Why a saved recipe must not run, even if captured by older code that kept agent commands.

    A `command` recipe whose program is a coding agent would replay its opening prompt, and so
    would an `app` recipe of an agent in its own window (angelX 0.2.5 opens one).
    """
    if recipe.get("kind") == "unknown":
        return recipe.get("reason") or "no-launch-command"
    argv = recipe.get("argv") or []
    program = None
    if recipe.get("kind") == "command" and "-e" in argv[:-1]:
        program = Path(argv[argv.index("-e") + 1]).name.lower()
    elif recipe.get("kind") == "app" and argv:
        program = Path(argv[0]).name.lower()
    if program in AGENT_NAMES:
        return "claude-session-unregistered" if program == "claude" else "agent-session-unannounced"
    return None if argv else "no-launch-command"


def is_terminal(app_id: str, comm: str) -> bool:
    haystack = f"{app_id} {comm}".lower()
    return any(marker in haystack for marker in TERMINAL_MARKERS)


def job_control(pid: int, start_ticks: int | None) -> tuple[int, int] | None:
    """A process's group and its terminal's foreground group; None when unknown or reused."""
    if start_ticks is None:
        return None
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text()
        fields = raw[raw.rindex(")") + 2 :].split()
        if int(fields[19]) != start_ticks:
            return None  # the pid now names another process
        return int(fields[2]), int(fields[5])
    except (OSError, ValueError, IndexError):
        return None


def foreground_job(
    shell: int, tree: list[int], by_pid: dict
) -> tuple[int | None, list[int]] | None:
    """The leader (if it still runs) and processes of the job in a surface's foreground.

    A daemon a program forked into a group of its own (nodecode's `setsid ... serve`) or a
    background job is not what the tab shows. None when job control cannot be read.
    """
    groups = {p: job_control(p, by_pid.get(p, {}).get("start_ticks")) for p in tree}
    if groups[shell] is None or groups[shell][1] <= 0:
        return None
    foreground = groups[shell][1]
    job = [p for p in tree if groups[p] is not None and groups[p][0] == foreground]
    if not job:
        return None
    return (foreground if foreground in job else None), job


def interactive_shell(pid: int, comm: str) -> bool:
    """A shell waiting for input (`bash`, `-zsh`, `bash --posix`), not one running a script or -c."""
    if comm not in SHELLS:
        return False
    try:
        args = read_cmdline(pid)[1:]
    except OSError:
        return True
    return not any(arg == "-c" or not arg.startswith("-") for arg in args)


def terminal_sessions(pid: int, inventory: list[dict]) -> list[dict]:
    """Resumable sessions (or the foreground commands) running inside one terminal process."""
    by_pid = {item["pid"]: item for item in inventory}
    children = children_index(inventory)
    sessions: list[dict] = []
    claimed: set[int] = set()
    for shell in children.get(pid, []):
        # Each direct child of the terminal is one surface's shell (or the command itself).
        tree = [shell, *descendants(shell, children)]
        found = None
        for candidate in tree:
            found = (
                claude_session(candidate)
                or pi_session(candidate)
                or declared_session(candidate, by_pid.get(candidate, {}).get("start_ticks"))
            )
            if found:
                break
        agent = next(
            (
                AGENT_NAMES[name]
                for p in tree
                if (name := str(by_pid.get(p, {}).get("comm", "")).lower()) in AGENT_NAMES
            ),
            None,
        )
        if found is None and agent is not None:
            # No announced session means nothing to resume. Its command line (often the opening
            # prompt) or a child's would start new work, so this surface is not reopened.
            found = {
                "kind": "unknown",
                "argv": [],
                "cwd": None,
                "label": None,
                "reason": "claude-session-unregistered"
                if agent == "claude"
                else "agent-session-unannounced",
                **({} if agent == "claude" else {"agent": agent}),
            }
        if found is None:
            # The command is what the tab runs in its foreground: the job's leader, as it was
            # started (`bash start.sh`), unless that is the interactive shell itself; then the
            # job's innermost program. Without job control, the whole tree is the job.
            job = foreground_job(shell, tree, by_pid)
            leader, pool = (None, tree) if job is None else job
            comm = str(by_pid.get(leader, {}).get("comm", ""))
            if leader is not None and leader not in claimed and not interactive_shell(leader, comm):
                leaf = leader
            else:
                leaves = [
                    p
                    for p in pool
                    if not any(c in pool for c in children.get(p, [])) and p not in claimed
                ]
                leaf = next(
                    (p for p in leaves if by_pid.get(p, {}).get("comm") not in SHELLS), None
                )
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
    if session and session["kind"] == "unknown":
        return unknown_recipe(session["reason"])
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


def appimage_launcher(executable: str, inventory: list[dict]) -> str | None:
    """The AppImage file whose runtime serves the temporary mount `executable` runs from."""
    mount = next(
        (
            (point, fstype, source)
            for point, fstype, source in mount_table()
            if Path(point).name.startswith(APPIMAGE_MOUNT_PREFIX)
            and executable.startswith(point.rstrip("/") + "/")
        ),
        None,
    )
    if mount is None or not mount[1].startswith("fuse."):
        return None
    image_name = mount[2]
    for item in inventory:
        image = read_exe(item["pid"])
        if not image or Path(image).name != image_name:
            continue
        try:
            launched = read_cmdline(item["pid"])[0]
        except (OSError, IndexError):
            launched = ""
        # Prefer the path the operator launched (often a stable, version-free symlink).
        return launched if launched.startswith("/") else image
    return None


def process_title_argv(cmdline: list[str]) -> list[str] | None:
    """Chromium and Electron overwrite /proc/PID/cmdline with one space-joined process title.

    Split such a title only where a leading part names a real program (whose path may itself
    contain spaces); arguments that contained spaces cannot be recovered. None: no program found.
    """
    if len(cmdline) != 1 or " " not in cmdline[0] or os.path.exists(cmdline[0]):
        return cmdline
    words = cmdline[0].split(" ")
    for end in range(1, len(words)):
        head = " ".join(words[:end])
        if (os.path.isfile(head) and os.access(head, os.X_OK)) or (
            os.sep not in head and shutil.which(head)
        ):
            return [head, *(word for word in words[end:] if word)]
    return None


def app_window_recipe(
    cmdline: list[str], comm: str, cwd: str | None, inventory: list[dict]
) -> dict:
    if comm.startswith(XWAYLAND_BRIDGE[:15]) or Path(cmdline[0]).name == XWAYLAND_BRIDGE:
        return unknown_recipe("xwayland-client")
    argv = process_title_argv(cmdline)
    if argv is None:
        return unknown_recipe("process-title-unresolved")
    split_title = argv is not cmdline  # process_title_argv returns an intact argv unchanged
    if f"/{APPIMAGE_MOUNT_PREFIX}" in argv[0]:
        launcher = appimage_launcher(argv[0], inventory)
        if launcher is None:
            return unknown_recipe("appimage-mount-unresolved")
        argv = [launcher, *argv[1:]]
    recipe = app_recipe(argv, cwd)
    if split_title:
        recipe["argv_from_process_title"] = True
    return recipe


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
            recipe = app_window_recipe(cmdline, process.get("comm", ""), read_cwd(pid), inventory)
            for window in group:
                recipes[window["id"]] = dict(recipe)
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
