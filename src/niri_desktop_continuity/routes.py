"""Where an app is relaunched from: a user route, its desktop entry, or its own command line.

One rule for every application. A desktop entry is how the user starts the app (wrappers, AppImages
and Flatpaks included). A captured command line can carry a sign-in URL or a deep link that would
repeat an action, so it is only the fallback, without URL operands. Nothing here runs anything.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

ROUTES_SCHEMA = "desktop-continuity.routes.v1"
MAX_ENTRY_BYTES = 256 * 1024
# Desktop Entry Specification field codes; continuity never passes files, URLs or icons.
FIELD_CODES = set("fFuUdDnNickvm")
ESCAPES = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}


@dataclass(frozen=True)
class Entry:
    id: str
    path: str
    argv: tuple[str, ...]
    wm_class: str | None
    cwd: str | None


def unescape(value: str) -> str:
    """The spec's string escapes (\\s \\n \\t \\r \\\\), applied before quoting rules."""
    out, i = [], 0
    while i < len(value):
        if value[i] == "\\" and value[i + 1 : i + 2] in ESCAPES:
            out.append(ESCAPES[value[i + 1]])
            i += 2
            continue
        out.append(value[i])  # other escapes (\" inside quotes) are for the quoting rules
        i += 1
    return "".join(out)


def exec_argv(value: str) -> list[str] | None:
    """Split an Exec value by the spec's quoting rules and drop field codes; None if malformed."""
    text = unescape(value)
    args, current, quoted, started, i = [], [], False, False, 0
    while i < len(text):
        char = text[i]
        if quoted:
            if char == "\\" and i + 1 < len(text) and text[i + 1] in '"`$\\':
                current.append(text[i + 1])
                i += 2
                continue
            if char == '"':
                quoted = False
            else:
                current.append(char)
        elif char == '"':
            quoted = started = True
        elif char in " \t\n":
            if current or started:
                args.append("".join(current))
            current, started = [], False
        elif char in "'\\":
            return None  # reserved outside double quotes
        else:
            current.append(char)
        i += 1
    if quoted:
        return None
    if current or started:
        args.append("".join(current))
    result = []
    for arg in args:
        if len(arg) == 2 and arg[0] == "%" and arg[1] in FIELD_CODES:
            continue
        kept, j = [], 0
        while j < len(arg):
            if arg[j] != "%":
                kept.append(arg[j])
                j += 1
                continue
            code = arg[j + 1 : j + 2]
            if code == "%":
                kept.append("%")
            elif code not in FIELD_CODES or not code:
                return None
            j += 2
        result.append("".join(kept))
    return result or None


def entry_keys(path: Path) -> dict[str, str] | None:
    try:
        if path.stat().st_size > MAX_ENTRY_BYTES:
            return None
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    keys, inside = {}, False
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            if inside:
                break
            inside = line == "[Desktop Entry]"
        elif inside and "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            if "[" not in key:  # localized keys never change what runs
                keys.setdefault(key.strip(), value.strip())
    return keys or None


def application_dirs() -> list[Path]:
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(base) / "applications" for base in [home, *dirs.split(":")] if base]


def desktop_entries(dirs: list[Path] | None = None) -> list[Entry]:
    """Launchable entries in XDG precedence order; an earlier directory hides the same ID later."""
    seen, entries = set(), []
    for root in application_dirs() if dirs is None else dirs:
        for path in sorted(root.rglob("*.desktop")) if root.is_dir() else []:
            entry_id = str(path.relative_to(root)).replace("/", "-")
            if entry_id in seen:
                continue
            seen.add(entry_id)
            keys = entry_keys(path)
            if not keys or keys.get("Type") != "Application" or keys.get("Hidden") == "true":
                continue
            if keys.get("Terminal") == "true":
                continue
            if keys.get("TryExec") and shutil.which(keys["TryExec"]) is None:
                continue
            argv = exec_argv(keys.get("Exec", ""))
            if argv is None:
                continue
            entries.append(
                Entry(
                    entry_id, str(path), tuple(argv), keys.get("StartupWMClass"), keys.get("Path")
                )
            )
    return entries


def resolved(program: str) -> str | None:
    found = program if program.startswith("/") else shutil.which(program)
    return os.path.realpath(found) if found else None


def entry_for(app_id: str | None, executable: str | None, entries: list[Entry]) -> Entry | None:
    """Same ID, then same StartupWMClass (case-insensitive), then the same program file."""
    key = (app_id or "").lower()
    if key:
        for entry in entries:
            if entry.id.lower().removesuffix(".desktop") == key:
                return entry
        for entry in entries:
            if (entry.wm_class or "").lower() == key:
                return entry
    program = resolved(executable) if executable else None
    if program:
        for entry in entries:
            if resolved(entry.argv[0]) == program:
                return entry
    return None


def user_routes(path: Path | None = None) -> dict[str, dict]:
    """Optional `routes.json`: one line per app that the automatic rules get wrong."""
    if path is None:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        path = Path(base) / "niri-desktop-continuity" / "routes.json"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {}
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError(f"{path}: must be your own regular file, not writable by others")
    value = json.loads(path.read_text(encoding="utf-8"))
    routes = value.get("routes") if isinstance(value, dict) else None
    if not isinstance(routes, dict):
        raise ValueError(f'{path}: expected {{"routes": {{APP_ID: ROUTE}}}}')
    for app_id, route in routes.items():
        desktop, argv = (
            (route.get("desktop"), route.get("argv")) if isinstance(route, dict) else (0, 0)
        )
        valid = (
            isinstance(route, dict)
            and set(route) <= {"desktop", "argv", "cwd"}
            and (isinstance(desktop, str) ^ isinstance(argv, list))
            and (argv is None or (argv and all(isinstance(a, str) and a for a in argv)))
            and (route.get("cwd") is None or str(route["cwd"]).startswith("/"))
        )
        if not valid:
            raise ValueError(f'{path}: route for {app_id!r} needs "desktop" or a nonempty "argv"')
    return routes


def without_urls(argv: list[str]) -> list[str]:
    """Drop URL/deep-link operands: a sign-in link or `app://action` must not run again."""
    return [argv[0], *(arg for arg in argv[1:] if "://" not in arg)] if argv else []


def route(
    app_id: str | None,
    recipe: dict,
    *,
    single_instance: bool,
    entries: list[Entry],
    users: dict[str, dict],
) -> dict | None:
    """How one saved app instance is launched, or None when there is no way to launch it."""
    argv = recipe.get("argv") or []
    user = users.get(app_id or "")
    if user and user.get("argv"):
        return {"route": "user", "argv": list(user["argv"]), "cwd": user.get("cwd")}
    if user:
        named = next((e for e in entries if e.id == user["desktop"]), None)
        if named is None:
            raise ValueError(f"routes.json: desktop entry {user['desktop']!r} not found")
        return {"route": f"desktop:{named.id}", "argv": list(named.argv), "cwd": named.cwd}
    # One menu entry cannot tell two instances (e.g. browser profiles) apart; each keeps its own.
    entry = entry_for(app_id, argv[0] if argv else None, entries) if single_instance else None
    if entry is not None:
        return {"route": f"desktop:{entry.id}", "argv": list(entry.argv), "cwd": entry.cwd}
    if argv:
        return {"route": "argv", "argv": without_urls(argv), "cwd": recipe.get("cwd")}
    return None
