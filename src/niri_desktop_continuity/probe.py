"""Bounded read-only desktop observation. Never launches apps or reads browser/session content."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import subprocess
from pathlib import Path

from .model import normalized_snapshot, now, process_pin

READ_COMMANDS = {"outputs", "windows", "workspaces", "layers", "version"}


class Niri:
    def query(self, command: str):
        if command not in READ_COMMANDS:
            raise ValueError("not an admitted read-only Niri query")
        result = subprocess.run(
            ["niri", "msg", "--json", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        if len(result.stdout) > 8 * 1024 * 1024:
            raise ValueError("Niri response exceeds observation bound")
        return json.loads(result.stdout)


def compositor_identity() -> dict:
    path = os.environ.get("NIRI_SOCKET")
    if not path:
        raise ValueError("NIRI_SOCKET unavailable")
    info = os.stat(path)
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("Niri socket must belong to the current user")
    return {
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "niri_socket": path,
        "socket_inode": info.st_ino,
        "socket_device": info.st_dev,
    }


def proc_stat(pid: int) -> dict:
    root = Path("/proc") / str(pid)
    if root.stat().st_uid != os.getuid():
        raise ValueError("not a same-user process")
    raw = (root / "stat").read_text()
    end = raw.rindex(")")
    fields = raw[end + 2 :].split()
    return {
        "pid": pid,
        "ppid": int(fields[1]),
        "start_ticks": int(fields[19]),
        "comm": raw[raw.index("(") + 1 : end],
    }


def cgroup(pid: int) -> str | None:
    lines = (Path("/proc") / str(pid) / "cgroup").read_text().splitlines()
    return next((line[3:] for line in lines if line.startswith("0::")), None)


def process_inventory() -> tuple[list[dict], bool]:
    items = []
    complete = True
    for entry in os.scandir("/proc"):
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            pid = int(entry.name)
            item = proc_stat(pid)
            item["cgroup"] = cgroup(pid)
            if proc_stat(pid)["start_ticks"] != item["start_ticks"]:
                continue
            items.append(item)
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (OSError, ValueError, IndexError):
            complete = False
            continue
        if len(items) >= 20000:
            complete = False
            break
    return sorted(items, key=lambda item: item["pid"]), complete


def executable_info(pid: int, cache: dict) -> dict:
    handle = Path("/proc") / str(pid) / "exe"
    target = os.readlink(handle)
    info = handle.stat()
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if identity in cache:
        return dict(cache[identity])
    checksum = None
    if info.st_size <= 512 * 1024 * 1024:
        with handle.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    # Observation must never execute a discovered application binary. Its version is unknown.
    version = None
    value = {
        "exe": target,
        "exe_sha256": checksum,
        "version": version,
        "exe_inode": info.st_ino,
        "exe_device": info.st_dev,
    }
    cache[identity] = value
    return dict(value)


def window_processes(windows: list[dict]) -> tuple[list[dict], list[str]]:
    processes, warnings, cache = [], [], {}
    for pid in sorted({window["pid"] for window in windows if isinstance(window.get("pid"), int)}):
        try:
            before = proc_stat(pid)
            value = {**before, "cgroup": cgroup(pid), **executable_info(pid, cache)}
            if proc_stat(pid)["start_ticks"] != before["start_ticks"]:
                raise ValueError("process identity changed while probing")
            processes.append(value)
        except (OSError, ValueError, IndexError) as exc:
            warnings.append(f"process-{pid}-unavailable:{type(exc).__name__}")
    return processes, warnings


def spatial_sample(windows: list[dict], workspaces: list[dict], outputs: dict) -> dict:
    return {
        "windows": sorted(
            [
                {
                    key: item.get(key)
                    for key in (
                        "id",
                        "app_id",
                        "pid",
                        "workspace_id",
                        "is_floating",
                        "is_focused",
                        "layout",
                    )
                }
                for item in windows
            ],
            key=lambda item: item["id"],
        ),
        "workspaces": sorted(
            [
                {
                    key: item.get(key)
                    for key in ("id", "idx", "name", "output", "is_focused", "is_active")
                }
                for item in workspaces
            ],
            key=lambda item: item["id"],
        ),
        "outputs": outputs,
    }


def capture(*, include_titles: bool = False, transport=None) -> dict:
    ipc = transport or Niri()
    identity = compositor_identity()
    started = now()
    windows = ipc.query("windows")
    workspaces = ipc.query("workspaces")
    outputs = ipc.query("outputs")
    layers = ipc.query("layers")
    version = ipc.query("version")
    processes, warnings = window_processes(windows)
    inventory, inventory_complete = process_inventory()
    final_windows = ipc.query("windows")
    final_workspaces = ipc.query("workspaces")
    final_outputs = ipc.query("outputs")
    final_layers = ipc.query("layers")
    final_processes, final_warnings = window_processes(final_windows)
    warnings.extend(final_warnings)
    coherent = (
        spatial_sample(windows, workspaces, outputs)
        == spatial_sample(final_windows, final_workspaces, final_outputs)
        and identity == compositor_identity()
        and layers == final_layers
        and ([process_pin(p) for p in processes] == [process_pin(p) for p in final_processes])
        and not warnings
    )
    return normalized_snapshot(
        {
            "captured_at": started,
            "finished_at": now(),
            "identity": identity,
            "niri_version": version,
            "coherent": coherent,
            "outputs": [{**value, "name": name} for name, value in outputs.items()],
            "windows": windows,
            "workspaces": workspaces,
            "layers": layers,
            "processes": processes,
            "process_inventory": inventory,
            "inventory_complete": inventory_complete,
            "warnings": warnings,
        },
        include_titles=include_titles,
    )


def watch_events(max_events: int):
    """Read-only finite event stream. No automatic mutation/promotion on event receipt."""
    if not 1 <= max_events <= 10000:
        raise ValueError("event limit must be 1..10000")
    identity = compositor_identity()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(30)
        stream.connect(identity["niri_socket"])
        stream.sendall(b'"EventStream"\n')
        with stream.makefile("rb") as reader:
            for _ in range(max_events):
                line = reader.readline(8 * 1024 * 1024 + 1)
                if not line:
                    return
                if len(line) > 8 * 1024 * 1024:
                    raise ValueError("event exceeds observation bound")
                value = json.loads(line)
                # Event names/count only; raw events can contain private titles.
                yield {
                    "event": next(iter(value), "unknown") if isinstance(value, dict) else "unknown",
                    "received_at": now(),
                }
