"""Same-user /proc readers shared by the launch-recipe modules. Nothing here runs anything."""

from __future__ import annotations

import os
from pathlib import Path

# Ghostty only: recipes use its --working-directory and -e. Other terminals take other flags,
# so they reopen as plain applications (their own command line), never with Ghostty's.
TERMINAL_MARKERS = ("ghostty",)


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


def read_exe(pid: int) -> str | None:
    try:
        return os.readlink(Path("/proc") / str(pid) / "exe")
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
