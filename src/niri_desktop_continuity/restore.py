"""Reopen a saved desktop: spawn each recipe, place it, rebuild columns. Never touches live windows."""

from __future__ import annotations

import errno
import json
import math
import os
import subprocess
import time

from .model import now, readiness, require_snapshot
from .operation_lock import operation_lock
from .probe import compositor_identity
from .restore_execute import execute
from .restore_wire import remaining

RESTORE_SCHEMA = "desktop-continuity.restore-receipt.v1"
SPAWN_TIMEOUT = 25.0
POLL_INTERVAL = 0.4
# niri spawns from its own working directory. An application captured with a relative path
# (`electron .`) starts in its saved one; `exec` keeps its command line exactly as recorded.
CHDIR_EXEC = 'cd -- "$1" && shift && exec "$@"'


def spawn_argv(recipe: dict) -> list[str]:
    """Terminal recipes carry their directory in their own argv; applications need it applied."""
    argv, cwd = list(recipe["argv"]), recipe.get("cwd")
    if recipe.get("kind") == "app" and isinstance(cwd, str) and os.path.isdir(cwd):
        return ["sh", "-c", CHDIR_EXEC, "sh", cwd, *argv]
    return argv


class LiveDesktop:
    """Niri IPC transport for restoration. Every mutation is an explicit action."""

    def windows(self, *, deadline=None) -> list[dict]:
        return self._query("windows", deadline=deadline)

    def workspaces(self, *, deadline=None) -> list[dict]:
        return self._query("workspaces", deadline=deadline)

    def ready(self) -> bool:
        try:
            self._query("version")
            return True
        except (subprocess.SubprocessError, ValueError, OSError):
            return False

    def spawn(self, argv: list[str]) -> None:
        self.action("spawn", "--", *argv)

    def action(self, *args: str) -> None:
        command = ["niri", "msg", "action", *args]
        client = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        status = client.wait(timeout=10)  # no timeout kill or retry after ambiguous IPC
        if status:
            raise subprocess.CalledProcessError(status, command)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def monotonic(self) -> float:
        return time.monotonic()

    def _query(self, command: str, *, deadline=None):
        if command not in {"windows", "workspaces", "version", "outputs"}:
            raise ValueError("unsupported restore read query")
        argv = ["niri", "msg", "--json", command]
        if command == "outputs":
            # Required inventory retains its original single-dispatch transport and budget.
            if deadline is not None:
                remaining(deadline)
            client = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                close_fds=True,
            )
            stdout, _ = client.communicate(
                timeout=10 if deadline is None else min(10, remaining(deadline))
            )  # no automatic process termination
            if deadline is not None:
                remaining(deadline)
            if client.returncode:
                raise subprocess.CalledProcessError(client.returncode, argv)
            result = json.loads(stdout)
            if deadline is not None:
                remaining(deadline)
            return result

        start = self.monotonic()
        bound = start + 10.0
        last, traceback = None, None

        def budget(observed=None):
            checked = self.monotonic() if observed is None else observed
            left = bound - checked
            caller = None if deadline is None else deadline - checked
            invalid = caller is not None and (not math.isfinite(caller) or not 0 < caller <= 300)
            if invalid or not left > 0:
                if last is not None:
                    raise last.with_traceback(traceback)
                if invalid:
                    raise TimeoutError("bootstrap absolute deadline exceeded or invalid")
                raise subprocess.TimeoutExpired(argv, 10)
            return left if caller is None else min(left, caller)

        budget(start)
        for attempt in range(3):
            budget()
            try:
                client = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    close_fds=True,
                )
            except BlockingIOError as exc:
                if type(exc) is not BlockingIOError or exc.errno != errno.EAGAIN:
                    raise
                last, traceback = exc, exc.__traceback__
                if attempt == 2:
                    raise
                delay = (0.05, 0.10)[attempt]
                if budget() <= delay:
                    raise
                self.sleep(delay)
                continue
            # A created client is never retried, terminated, or implicitly cleaned up.
            stdout, _ = client.communicate(timeout=budget())
            budget()
            if client.returncode:
                raise subprocess.CalledProcessError(client.returncode, argv)
            result = json.loads(stdout)
            budget()
            return result


def column_of(window: dict) -> int | None:
    position = (window.get("layout") or {}).get("pos_in_scrolling_layout")
    return position[0] if position else None


def tile_of(window: dict) -> int:
    position = (window.get("layout") or {}).get("pos_in_scrolling_layout")
    return position[1] if position else 1


def plan_restore(
    snapshot: dict, current_windows: list[dict], current_workspaces: list[dict]
) -> dict:
    """Pure placement plan. Saved workspaces compact to consecutive indices; unknown recipes go last."""
    require_snapshot(snapshot)
    saved_workspaces = {item["id"]: item for item in snapshot["workspaces"]}
    live_sessions = {
        json.dumps(item.get("reopen", {}).get("argv"), sort_keys=True)
        for item in current_windows
        if isinstance(item.get("reopen"), dict) and item["reopen"].get("kind") in {"claude", "pi"}
    }
    entries = []
    for window in sorted(snapshot["windows"], key=lambda item: item["id"]):
        recipe = window.get("reopen") or {"kind": "unknown", "argv": [], "reason": "no-recipe"}
        workspace = saved_workspaces.get(window.get("workspace_id"))
        entry = {
            "window_id": window["id"],
            "app_id": window.get("app_id"),
            "recipe": recipe,
            "saved_workspace_idx": workspace.get("idx") if workspace else None,
            "saved_workspace_name": workspace.get("name") if workspace else None,
            "column": column_of(window),
            "tile": tile_of(window),
            "width": ((window.get("layout") or {}).get("tile_size") or [None])[0],
            "floating": bool(window.get("is_floating")),
            "floating_position": (window.get("layout") or {}).get("tile_pos_in_workspace_view"),
        }
        if recipe.get("kind") in {"claude", "pi"} and (
            json.dumps(recipe.get("argv"), sort_keys=True) in live_sessions
        ):
            entry["status"] = "already-open"
        entries.append(entry)
        for extra in recipe.get("extra") or []:
            entries.append(
                {
                    **entry,
                    "recipe": extra,
                    "window_id": None,
                    "column": None,
                    "tile": 1,
                    "width": None,
                    "extra_of": window["id"],
                    "status": "already-open"
                    if json.dumps(extra.get("argv"), sort_keys=True) in live_sessions
                    else None,
                }
            )
    known = sorted(
        {
            e["saved_workspace_idx"]
            for e in entries
            if e["recipe"].get("kind") != "unknown" and e["saved_workspace_idx"] is not None
        }
    )
    mapping = {idx: position for position, idx in enumerate(known, 1)}
    unknown_target = len(known) + 1
    for entry in entries:
        if entry["recipe"].get("kind") == "unknown" or entry["saved_workspace_idx"] is None:
            entry["target_workspace_idx"] = unknown_target
            entry["column"] = None
        else:
            entry["target_workspace_idx"] = mapping[entry["saved_workspace_idx"]]
    names = {
        mapping[e["saved_workspace_idx"]]: e["saved_workspace_name"]
        for e in entries
        if e["saved_workspace_idx"] in mapping and e["saved_workspace_name"]
    }
    entries.sort(
        key=lambda e: (
            e["target_workspace_idx"],
            e["column"] is None,
            e["column"] or 0,
            e["tile"],
            e["window_id"] or 0,
        )
    )
    return {
        "entries": entries,
        "workspace_names": {str(k): v for k, v in names.items()},
        "protected_window_ids": sorted(item["id"] for item in current_windows),
        "unknown_workspace_idx": unknown_target
        if any(e["target_workspace_idx"] == unknown_target for e in entries)
        else None,
    }


def restore(store, snapshot_key, desktop, *, apply, observe=None, spawn_timeout=SPAWN_TIMEOUT):
    """Dry runs observe only; effectful restore uses one explicit attempt through final commit."""
    snapshot = store.get("snapshots", snapshot_key)
    if not readiness(snapshot)["ready"]:
        raise ValueError("saved snapshot is not display-valid; refusing to reopen from it")
    if apply:
        from .restore_exited import historical_replay

        replay = historical_replay(snapshot, snapshot_key)
        if replay is not None:
            return replay
    if observe is None:
        from .probe import capture

        observe = capture
    identity = compositor_identity()
    if apply:
        return execute(
            store, snapshot_key, identity, desktop, observe, snapshot, plan_restore, spawn_timeout
        )
    with operation_lock(identity, effectful=False):
        current = observe()
        plan = plan_restore(snapshot, current["windows"], current["workspaces"])
        receipt = {
            "schema": RESTORE_SCHEMA,
            "snapshot_digest": snapshot_key,
            "apply": False,
            "status": "dry-run",
            "started_at": now(),
            "finished_at": now(),
            "protected_window_ids": plan["protected_window_ids"],
            "unknown_workspace_idx": plan["unknown_workspace_idx"],
            "effects": [],
            "windows": [
                {k: v for k, v in e.items() if k != "recipe"}
                | {"kind": e["recipe"].get("kind"), "argv": e["recipe"].get("argv")}
                for e in plan["entries"]
            ],
        }
        return {"receipt_digest": store.put("receipts", receipt), **receipt}
