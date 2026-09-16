"""Reopen a saved desktop: spawn each recipe, place it, rebuild columns. Never touches live windows."""

from __future__ import annotations

import json
import subprocess
import time
from copy import deepcopy

from .model import now, readiness, require_snapshot
from .operation_lock import operation_lock
from .probe import compositor_identity

RESTORE_SCHEMA = "desktop-continuity.restore-receipt.v1"
SPAWN_TIMEOUT = 25.0
POLL_INTERVAL = 0.4


class LiveDesktop:
    """Niri IPC transport for restoration. Every mutation is an explicit action."""

    def windows(self) -> list[dict]:
        return self._query("windows")

    def workspaces(self) -> list[dict]:
        return self._query("workspaces")

    def ready(self) -> bool:
        try:
            self._query("version")
            return True
        except (subprocess.SubprocessError, ValueError, OSError):
            return False

    def spawn(self, argv: list[str]) -> None:
        self.action("spawn", "--", *argv)

    def action(self, *args: str) -> None:
        subprocess.run(
            ["niri", "msg", "action", *args], capture_output=True, text=True, timeout=10, check=True
        )

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def monotonic(self) -> float:
        return time.monotonic()

    @staticmethod
    def _query(command: str):
        result = subprocess.run(
            ["niri", "msg", "--json", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return json.loads(result.stdout)


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
            "width": (window.get("layout") or {}).get("tile_size", [None])[0],
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
        "workspace_names": names,
        "protected_window_ids": sorted(item["id"] for item in current_windows),
        "unknown_workspace_idx": unknown_target
        if any(e["target_workspace_idx"] == unknown_target for e in entries)
        else None,
    }


def wait_for_window(desktop, known: set[int], app_id: str | None, timeout: float) -> dict | None:
    deadline = desktop.monotonic() + timeout
    fallback = None
    while desktop.monotonic() < deadline:
        for window in desktop.windows():
            if window["id"] in known:
                continue
            if app_id is None or window.get("app_id") == app_id:
                return window
            fallback = fallback or window
        desktop.sleep(POLL_INTERVAL)
    return fallback


def arrange_workspace(desktop, idx: int, placed: list[dict], protected: set[int]) -> list[dict]:
    """Rebuild saved column order after existing (protected) columns on one workspace."""
    effects: list[dict] = []
    workspace_ids = {w["idx"]: w["id"] for w in desktop.workspaces()}
    workspace_id = workspace_ids.get(idx)
    live = [w for w in desktop.windows() if w.get("workspace_id") == workspace_id]
    offset = len({column_of(w) for w in live if w["id"] in protected and not w.get("is_floating")})
    columns: dict[int, list[dict]] = {}
    for entry in placed:
        if entry.get("floating") or entry.get("column") is None:
            continue
        columns.setdefault(entry["column"], []).append(entry)
    for rank, column in enumerate(sorted(columns), 1):
        tiles = sorted(columns[column], key=lambda e: e["tile"])
        target = offset + rank
        seed = tiles[0]["restored_window_id"]
        desktop.action("focus-window", "--id", str(seed))
        desktop.action("move-column-to-index", str(target))
        effects.append({"window_id": seed, "action": "move-column-to-index", "index": target})
        width = tiles[0].get("width")
        if isinstance(width, (int, float)) and width > 0:
            desktop.action("set-column-width", str(int(round(width))))
            effects.append(
                {"window_id": seed, "action": "set-column-width", "width": int(round(width))}
            )
        for extra in tiles[1:]:
            desktop.action("focus-window", "--id", str(extra["restored_window_id"]))
            desktop.action("move-column-to-index", str(target + 1))
            desktop.action("focus-window", "--id", str(seed))
            desktop.action("consume-window-into-column")
            effects.append(
                {
                    "window_id": extra["restored_window_id"],
                    "action": "consume-into-column",
                    "index": target,
                }
            )
    for entry in placed:
        if entry.get("floating") and entry.get("restored_window_id") is not None:
            wid = str(entry["restored_window_id"])
            desktop.action("move-window-to-floating", "--id", wid)
            position = entry.get("floating_position")
            if isinstance(position, list) and len(position) == 2:
                desktop.action(
                    "move-floating-window",
                    "--id",
                    wid,
                    "-x",
                    str(int(round(position[0]))),
                    "-y",
                    str(int(round(position[1]))),
                )
            effects.append({"window_id": wid, "action": "float"})
    return effects


def restore(
    store,
    snapshot_key: str,
    desktop,
    *,
    apply: bool,
    observe=None,
    spawn_timeout: float = SPAWN_TIMEOUT,
) -> dict:
    """observe() is a full capture of the current desktop (with reopen recipes); desktop is IPC."""
    snapshot = store.get("snapshots", snapshot_key)
    if not readiness(snapshot)["ready"]:
        raise ValueError("saved snapshot is not display-valid; refusing to reopen from it")
    if observe is None:
        from .probe import capture

        observe = capture
    identity = compositor_identity()
    with operation_lock(identity):
        return _restore_locked(
            store, snapshot_key, snapshot, desktop, observe, apply, spawn_timeout
        )


def _restore_locked(store, snapshot_key, snapshot, desktop, observe, apply, spawn_timeout):
    current = observe()
    current_windows = current["windows"]
    plan = plan_restore(snapshot, current_windows, current["workspaces"])
    receipt = {
        "schema": RESTORE_SCHEMA,
        "snapshot_digest": snapshot_key,
        "started_at": now(),
        "apply": apply,
        "protected_window_ids": plan["protected_window_ids"],
        "unknown_workspace_idx": plan["unknown_workspace_idx"],
        "windows": [],
        "effects": [],
        "status": "dry-run",
    }
    if not apply:
        receipt["windows"] = [
            {k: v for k, v in entry.items() if k != "recipe"}
            | {"kind": entry["recipe"].get("kind"), "argv": entry["recipe"].get("argv")}
            for entry in plan["entries"]
        ]
        receipt["finished_at"] = now()
        return {"receipt_digest": store.put("receipts", receipt), **receipt}
    protected = set(plan["protected_window_ids"])
    original_focus = next((w["id"] for w in current_windows if w.get("is_focused")), None)
    known = {w["id"] for w in current_windows}
    placed_by_workspace: dict[int, list[dict]] = {}
    failures = 0
    try:
        for entry in plan["entries"]:
            record = deepcopy(entry)
            record["kind"] = entry["recipe"].get("kind")
            record["argv"] = entry["recipe"].get("argv")
            del record["recipe"]
            if entry.get("status") == "already-open":
                receipt["windows"].append(record)
                continue
            if not entry["recipe"].get("argv"):
                record["status"] = "no-launch-command"
                failures += 1
                receipt["windows"].append(record)
                continue
            target = entry["target_workspace_idx"]
            desktop.spawn(entry["recipe"]["argv"])
            receipt["effects"].append({"action": "spawn", "kind": record["kind"], "at": now()})
            window = wait_for_window(desktop, known, entry.get("app_id"), spawn_timeout)
            if window is None:
                record["status"] = "spawned-window-not-detected"
                failures += 1
                receipt["windows"].append(record)
                continue
            known.add(window["id"])
            record["restored_window_id"] = window["id"]
            desktop.action(
                "move-window-to-workspace",
                "--window-id",
                str(window["id"]),
                "--focus",
                "false",
                str(target),
            )
            receipt["effects"].append(
                {"action": "move-window-to-workspace", "window_id": window["id"], "index": target}
            )
            record["status"] = "placed"
            receipt["windows"].append(record)
            placed_by_workspace.setdefault(target, []).append(record)
        for idx in sorted(placed_by_workspace):
            receipt["effects"].extend(
                arrange_workspace(desktop, idx, placed_by_workspace[idx], protected)
            )
        for idx, name in sorted(plan["workspace_names"].items()):
            if idx in placed_by_workspace:
                desktop.action("set-workspace-name", "--workspace", str(idx), name)
                receipt["effects"].append({"action": "set-workspace-name", "index": idx})
        if original_focus is not None and any(w["id"] == original_focus for w in desktop.windows()):
            desktop.action("focus-window", "--id", str(original_focus))
        else:
            desktop.action("focus-workspace", "1")
        receipt["status"] = "reopened" if not failures else "reopened-partially"
    except Exception as exc:  # noqa: BLE001 - the receipt must record any interruption
        receipt["status"] = "interrupted"
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)
    receipt["failures"] = failures
    receipt["finished_at"] = now()
    key = store.put("receipts", receipt)
    if receipt["status"].startswith("reopened"):
        store.pointer("last-reopened", snapshot_key)
    return {"receipt_digest": key, **receipt}
