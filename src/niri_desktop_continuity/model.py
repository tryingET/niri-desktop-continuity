"""Pure desktop state and proof predicates. No IPC, process control or title guessing."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

SNAPSHOT_SCHEMA = "desktop-continuity.snapshot.v1"
PLAN_SCHEMA = "desktop-continuity.plan.v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def require_snapshot(snapshot: dict) -> None:
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError("unsupported snapshot schema")
    for key in ("windows", "workspaces", "outputs", "layers", "processes"):
        if not isinstance(snapshot.get(key), list):
            raise ValueError(f"snapshot {key} must be a list")
    for key in ("windows", "workspaces"):
        ids = [entry.get("id") for entry in snapshot[key]]
        if any(type(item) is not int or item < 0 for item in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"invalid or duplicate {key} identities")
    for window in snapshot["windows"]:
        position = (window.get("layout") or {}).get("pos_in_scrolling_layout")
        if position is not None and (
            not isinstance(position, list)
            or len(position) != 2
            or any(type(value) is not int or value < 1 for value in position)
        ):
            raise ValueError("invalid column/tile position")
        for key in ("tile_size", "window_size"):
            dimensions = (window.get("layout") or {}).get(key)
            if dimensions is not None and (
                not isinstance(dimensions, list)
                or len(dimensions) != 2
                or any(
                    type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                    for value in dimensions
                )
            ):
                raise ValueError("invalid window dimensions")
    if not isinstance(snapshot.get("identity"), dict) or not snapshot["identity"]:
        raise ValueError("missing compositor identity")


def readiness(snapshot: dict) -> dict:
    reasons = []
    active_outputs = {
        item.get("name")
        for item in snapshot["outputs"]
        if isinstance(item.get("logical"), dict) and item.get("current_mode") is not None
    }
    if not active_outputs:
        reasons.append("no-usable-output")
    workspace_by_id = {item["id"]: item for item in snapshot["workspaces"]}
    if not any(item.get("is_active") or item.get("is_focused") for item in snapshot["workspaces"]):
        reasons.append("no-active-workspace")
    for window in snapshot["windows"]:
        workspace = workspace_by_id.get(window.get("workspace_id"))
        if workspace is None or workspace.get("output") not in active_outputs:
            reasons.append("window-on-unavailable-workspace")
    if snapshot.get("coherent") is not True:
        reasons.append("incoherent-observation")
    return {"ready": not reasons, "reasons": sorted(set(reasons))}


def process_pin(process: dict) -> dict:
    return {
        key: process.get(key)
        for key in ("pid", "start_ticks", "exe", "exe_sha256", "exe_inode", "exe_device", "cgroup")
    }


def focus_pin(snapshot: dict) -> dict:
    return {
        "windows": sorted(item["id"] for item in snapshot["windows"] if item.get("is_focused")),
        "workspaces": sorted(
            item["id"] for item in snapshot["workspaces"] if item.get("is_focused")
        ),
    }


def topology(snapshot: dict) -> dict:
    """Only durable-for-this-compositor placement; never titles or capture time."""
    return {
        "identity": snapshot["identity"],
        "outputs": sorted(
            [
                {key: item.get(key) for key in ("name", "logical", "current_mode")}
                for item in snapshot["outputs"]
            ],
            key=lambda item: item["name"],
        ),
        "workspaces": sorted(
            [
                {key: item.get(key) for key in ("id", "idx", "name", "output")}
                for item in snapshot["workspaces"]
            ],
            key=lambda item: item["id"],
        ),
        "windows": sorted(
            [
                {
                    **{
                        key: item.get(key)
                        for key in ("id", "pid", "app_id", "workspace_id", "is_floating")
                    },
                    "layout": {
                        key: item.get("layout", {}).get(key)
                        for key in (
                            "pos_in_scrolling_layout",
                            "tile_size",
                            "window_size",
                            # Tiled viewport coordinates change with scrolling/focus, not topology.
                        )
                    },
                    "floating_position": item.get("layout", {}).get("tile_pos_in_workspace_view")
                    if item.get("is_floating")
                    else None,
                }
                for item in snapshot["windows"]
            ],
            key=lambda item: item["id"],
        ),
        "processes": sorted(
            [process_pin(item) for item in snapshot["processes"]], key=lambda item: item["pid"]
        ),
        "layers": sorted(
            snapshot["layers"],
            key=lambda item: (
                str(item.get("namespace")),
                str(item.get("output")),
                str(item.get("layer")),
            ),
        ),
    }


def fingerprint(snapshot: dict) -> str:
    require_snapshot(snapshot)
    return digest(topology(snapshot))


def capability(app_id: str) -> dict:
    owner = "application-specific adapter required"
    if "ghostty" in app_id.lower():
        owner = (
            "Ghostty exact window/tab/split export required; terminal history is not process memory"
        )
    elif app_id in {"brave-browser", "chromium"}:
        owner = "browser-native profile/session state; not inspected"
    return {
        "layout": "same-instance",
        "native_state": "unverified",
        "restart": "blocked",
        "reason": owner,
    }


def normalized_snapshot(raw: dict, *, include_titles: bool = False) -> dict:
    snapshot = deepcopy(raw)
    snapshot["schema"] = SNAPSHOT_SCHEMA
    snapshot.setdefault("captured_at", now())
    snapshot.setdefault("processes", [])
    snapshot.setdefault("layers", [])
    snapshot.setdefault("warnings", [])
    snapshot["privacy"] = {"titles_included": include_titles}
    for window in snapshot["windows"]:
        app = str(window.get("app_id") or "unknown")
        window["app_id"] = app
        window["title"] = (
            str(window.get("title") or "") if include_titles else f"{app} · {window['id']}"
        )
        window["layout"] = window.get("layout") or {}
        window["capabilities"] = capability(app)
    require_snapshot(snapshot)
    snapshot["display"] = readiness(snapshot)
    return snapshot


def verify(desired: dict, actual: dict) -> dict:
    """A compositor proof only. Native tabs, drafts and process memory remain unverified."""
    require_snapshot(desired)
    require_snapshot(actual)
    issues: list[dict] = []
    if not readiness(desired)["ready"]:
        return {
            "status": "blocked",
            "issues": ["desired-checkpoint-not-display-valid"],
            "layout_verified": False,
            "native_state": "unverified",
        }
    if not readiness(actual)["ready"]:
        return {
            "status": "waiting-for-output",
            "issues": readiness(actual)["reasons"],
            "layout_verified": False,
            "native_state": "unverified",
        }
    if desired["identity"] != actual["identity"]:
        return {
            "status": "blocked",
            "issues": ["different-compositor-instance"],
            "layout_verified": False,
            "native_state": "unverified",
        }
    expected = topology(desired)
    observed = topology(actual)
    desired_windows = {item["id"]: item for item in expected["windows"]}
    actual_windows = {item["id"]: item for item in observed["windows"]}
    for wid in sorted(desired_windows.keys() | actual_windows.keys()):
        before, after = desired_windows.get(wid), actual_windows.get(wid)
        if before is None or after is None:
            issues.append(
                {"window_id": wid, "kind": "extra-window" if before is None else "missing-window"}
            )
        elif before != after:
            issues.append(
                {
                    "window_id": wid,
                    "kind": "window-mismatch",
                    "fields": [key for key in before if before[key] != after.get(key)],
                }
            )
    for key in ("outputs", "workspaces", "processes", "layers"):
        if expected[key] != observed[key]:
            issues.append({"kind": f"{key}-mismatch"})
    return {
        "status": "layout-verified" if not issues else "partial",
        "issues": issues,
        "focus_verified": focus_pin(desired) == focus_pin(actual),
        "layout_verified": not issues,
        "native_state": "unverified",
        "matched_windows": len(desired_windows.keys() & actual_windows.keys()),
        "expected_windows": len(desired_windows),
        "actual_windows": len(actual_windows),
    }
