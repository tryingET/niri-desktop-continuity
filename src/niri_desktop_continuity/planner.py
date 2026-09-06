"""Closed selective plans. Restart coverage is an admission predicate, never a guess."""

from __future__ import annotations

import hashlib
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .model import (
    PLAN_SCHEMA,
    digest,
    fingerprint,
    focus_pin,
    readiness,
    require_snapshot,
    topology,
)


def select(snapshot: dict, *, window_ids=(), pids=(), app_id=None, version=None) -> dict:
    processes = {item["pid"]: item for item in snapshot["processes"]}
    windows = snapshot["windows"]
    chosen = [
        item
        for item in windows
        if (not window_ids or item["id"] in window_ids)
        and (not pids or item.get("pid") in pids)
        and (not app_id or item.get("app_id") == app_id)
        and (not version or processes.get(item.get("pid"), {}).get("version") == version)
    ]
    return {
        "window_ids": sorted(item["id"] for item in chosen),
        "pids": sorted({item["pid"] for item in chosen if isinstance(item.get("pid"), int)}),
        "app_id": app_id,
        "version": version,
        "requested_window_ids": sorted(set(window_ids)),
        "requested_pids": sorted(set(pids)),
    }


def affected_scope(snapshot: dict, selection: dict) -> dict:
    inventory = {item["pid"]: item for item in snapshot.get("process_inventory", [])}
    inventory.update({item["pid"]: item for item in snapshot["processes"]})
    affected = set(selection["pids"])
    groups = {inventory[pid].get("cgroup") for pid in affected if pid in inventory}
    groups.discard(None)
    # A root or broad session slice is never considered an independently restartable service.
    precise_groups = {group for group in groups if group.endswith((".service", ".scope"))}
    changed = True
    while changed:
        before = len(affected)
        for item in inventory.values():
            group = item.get("cgroup") or ""
            if item.get("ppid") in affected or any(
                group == owner or group.startswith(owner + "/") for owner in precise_groups
            ):
                affected.add(item["pid"])
        changed = len(affected) != before
    window_ids = sorted(
        window["id"] for window in snapshot["windows"] if window.get("pid") in affected
    )
    return {
        "window_ids": window_ids,
        "pids": sorted(affected),
        "extra_window_ids": sorted(set(window_ids) - set(selection["window_ids"])),
        "process_pins": [
            {
                key: inventory[pid].get(key)
                for key in ("pid", "ppid", "start_ticks", "comm", "cgroup")
            }
            for pid in sorted(affected)
            if pid in inventory
        ],
        "ownership_unknown": any(
            pid not in inventory or not inventory[pid].get("cgroup") for pid in affected
        ),
    }


def pin_replacement(path: str) -> dict:
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError("replacement must be an existing executable regular file")
    before = resolved.stat()
    if before.st_size > 512 * 1024 * 1024:
        raise ValueError("replacement exceeds hash size bound")
    with resolved.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    after = resolved.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError("replacement changed during admission")
    return {
        "path": str(resolved),
        "sha256": checksum,
        "inode": after.st_ino,
        "device": after.st_dev,
        "size": after.st_size,
    }


def layout_actions(current: dict, desired: dict) -> tuple[list[dict], list[str]]:
    """Conservative same-instance single-output/single-tile-column placement backend."""
    blockers: list[str] = []
    actions: list[dict] = []
    before, after = topology(current), topology(desired)
    if current["identity"] != desired["identity"]:
        blockers.append("different-compositor-instance")
    for key in ("outputs", "workspaces", "processes", "layers"):
        if before[key] != after[key]:
            blockers.append(f"unsupported-{key}-change")
    actual = {item["id"]: item for item in current["windows"]}
    target = {item["id"]: item for item in desired["windows"]}
    if actual.keys() != target.keys():
        blockers.append("missing-or-extra-window-identities")
    if before == after:
        return [], blockers
    if len(focus_pin(current)["windows"]) != 1:
        blockers.append("original-focus-not-restorable")
    if len([item for item in desired["outputs"] if item.get("logical")]) != 1:
        blockers.append("multi-output-layout-apply-not-yet-admitted")
    for snapshot in (current, desired):
        seen: set[tuple] = set()
        for window in snapshot["windows"]:
            pos = window.get("layout", {}).get("pos_in_scrolling_layout")
            if window.get("is_floating"):
                continue
            if (
                not isinstance(pos, list)
                or len(pos) != 2
                or pos[1] != 1
                or any(type(value) is not int or value < 1 for value in pos)
            ):
                blockers.append("multi-tile-or-unknown-column-topology-not-admitted")
                continue
            key = (window.get("workspace_id"), pos[0])
            if key in seen:
                blockers.append("multi-tile-or-unknown-column-topology-not-admitted")
            seen.add(key)
        for workspace_id in {item[0] for item in seen}:
            indices = sorted(item[1] for item in seen if item[0] == workspace_id)
            if indices != list(range(1, len(indices) + 1)):
                blockers.append("noncontiguous-column-topology-not-admitted")
    if any(
        not item.get("start_ticks") or not item.get("exe_sha256") for item in current["processes"]
    ) or ({w.get("pid") for w in current["windows"]} - {p["pid"] for p in current["processes"]}):
        blockers.append("incomplete-executable-identity")
    for wid in actual.keys() & target.keys():
        left, right = actual[wid], target[wid]
        if (left.get("pid"), left.get("app_id")) != (right.get("pid"), right.get("app_id")):
            blockers.append("window-owner-changed")
        if left.get("workspace_id") != right.get("workspace_id"):
            blockers.append("cross-workspace-placement-not-effect-modelled")
        if left.get("is_floating") != right.get("is_floating"):
            blockers.append("floating-transition-not-admitted")
        if left.get("is_floating") and left.get("layout") != right.get("layout"):
            blockers.append("floating-geometry-change-not-admitted")
        for field in ("tile_size", "window_size"):
            if left.get("layout", {}).get(field) != right.get("layout", {}).get(field):
                blockers.append("geometry-resize-not-admitted")
    if blockers:
        return [], sorted(set(blockers))
    workspaces = {item["id"]: item for item in desired["workspaces"]}
    # Re-establish all affected column orders, not a fragile list of relative swaps.
    ordered = sorted(
        (item for item in target.values() if not item.get("is_floating")),
        key=lambda item: (
            workspaces[item["workspace_id"]]["idx"],
            item["layout"]["pos_in_scrolling_layout"][0],
        ),
    )
    for window in ordered:
        actions.append(
            {
                "kind": "place-column",
                "window_id": window["id"],
                "column_index": window["layout"]["pos_in_scrolling_layout"][0],
            }
        )
    return actions, []


def build_plan(
    snapshot: dict,
    *,
    intent="inspect",
    desired=None,
    window_ids=(),
    pids=(),
    app_id=None,
    version=None,
    replacement=None,
    ttl_seconds=300,
) -> dict:
    require_snapshot(snapshot)
    if intent not in {"inspect", "reconcile", "restart", "migrate"}:
        raise ValueError("unsupported intent")
    if not 1 <= ttl_seconds <= 900:
        raise ValueError("approval lifetime must be between 1 and 900 seconds")
    if intent == "reconcile" and any((window_ids, pids, app_id, version)):
        raise ValueError(
            "layout reconciliation is an exact whole-map operation; selectors are restart-only"
        )
    desired = deepcopy(desired or snapshot)
    require_snapshot(desired)
    chosen = select(snapshot, window_ids=window_ids, pids=pids, app_id=app_id, version=version)
    affected = affected_scope(snapshot, chosen)
    blockers, warnings, actions = [], [], []
    if not readiness(snapshot)["ready"]:
        blockers.extend(readiness(snapshot)["reasons"])
    if not readiness(desired)["ready"]:
        blockers.append("desired-checkpoint-not-display-valid")
    if not chosen["window_ids"] and not chosen["pids"]:
        blockers.append("selector-matched-nothing")
    if set(pids) - set(chosen["pids"]):
        blockers.append("some-selected-pids-unmatched-or-filtered")
    if set(window_ids) - set(chosen["window_ids"]):
        blockers.append("some-selected-windows-unmatched")
    pinned = pin_replacement(replacement) if replacement else None
    if intent in {"restart", "migrate"}:
        blockers.append("exact-application-checkpoint-and-restart-adapter-unavailable")
        if affected["extra_window_ids"]:
            blockers.append("shared-process-expands-beyond-selected-windows")
        if affected["ownership_unknown"] or not snapshot.get("inventory_complete"):
            blockers.append("incomplete-process-ownership")
        known_processes = {item["pid"]: item for item in snapshot["processes"]}
        if any(
            not known_processes.get(pid, {}).get("exe_sha256")
            or not known_processes.get(pid, {}).get("start_ticks")
            for pid in chosen["pids"]
        ):
            blockers.append("incomplete-executable-identity")
        warnings.append("running-jobs-and-unsaved-drafts-are-not-proven-recoverable")
    if intent == "migrate" and not pinned:
        blockers.append("exact-replacement-build-required")
    if pinned and all(
        item.get("exe_sha256") == pinned["sha256"]
        for item in snapshot["processes"]
        if item["pid"] in chosen["pids"]
    ):
        warnings.append("selected-hosts-already-use-replacement-build")
    if intent == "reconcile":
        actions, layout_blockers = layout_actions(snapshot, desired)
        blockers.extend(layout_blockers)
        warnings.append("focus-dependent-column-actions; operator-movement-invalidates-approval")
        warnings.append("non-atomic-focus-move; concurrent-input-race-cannot-be-prevented")
    created = datetime.now(timezone.utc)
    return {
        "schema": PLAN_SCHEMA,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(seconds=ttl_seconds)).isoformat(),
        "intent": intent,
        "snapshot_digest": digest(snapshot),
        "source_identity": snapshot["identity"],
        "state_fingerprint": fingerprint(snapshot),
        "focus_pin": focus_pin(snapshot),
        "desired": desired,
        "selection": chosen,
        "affected": affected,
        "replacement": pinned,
        "admission": {
            "status": "review-only"
            if intent == "inspect"
            else ("blocked" if blockers else "awaiting-approval"),
            "blockers": sorted(set(blockers)),
            "warnings": warnings,
        },
        "actions": actions,
        "fidelity": {
            "layout": "same-instance",
            "native_state": "unverified",
            "process_memory": "unsupported",
        },
    }
