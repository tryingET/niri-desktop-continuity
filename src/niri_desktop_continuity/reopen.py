"""Reopen a saved desktop: launch each app once, adopt only its new windows, rebuild the layout.

This is the 0.1.2 restorer with its three defects fixed: one launch per saved app instance (never a
second launch after a wait), only new windows of the launched app are adopted (never an unrelated
window), and agents are never relaunched from their command line (see launch.py). Every app follows
the same rule; routes.py says where it is launched from. Windows open before restore are never moved.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections import Counter

from . import operation_lock as locks
from . import probe, routes
from .launch import refusal
from .model import now, readiness, require_snapshot

RESTORE_SCHEMA = "desktop-continuity.restore-receipt.v1"
SPAWN_TIMEOUT = 25.0
QUIET = 5.0  # an app that stops opening windows for this long has restored what it will
POLL_INTERVAL = 0.4
SESSION_KINDS = {"claude", "pi", "declared"}
TERMINAL_KINDS = {"shell", "command", *SESSION_KINDS}
# Earlier controlled restores started Ghostty without the user's configuration; drop that.
LOSSY_TERMINAL_FLAGS = {"--config-default-files=false"}
# niri spawns from its own working directory. An application captured with a relative path
# (`electron .`) starts in its saved one; `exec` keeps its command line exactly as recorded.
CHDIR_EXEC = 'cd -- "$1" && shift && exec "$@"'


def logind_locked() -> bool:
    """Whether logind says the user's active session is locked; unknown counts as unlocked.

    Niri ignores spawn requests while a screen locker runs, so nothing launched then would appear.
    """

    def ask(*args):
        result = subprocess.run(
            ["loginctl", *args], capture_output=True, text=True, timeout=3, check=False
        )
        return result.stdout if result.returncode == 0 else ""

    try:
        for line in ask("list-sessions", "--no-legend").splitlines():
            fields = line.split()
            if len(fields) < 2 or fields[1] != str(os.getuid()):
                continue
            values = ask("show-session", fields[0], "-p", "Active", "-p", "LockedHint")
            if "Active=yes" in values.split() and "LockedHint=yes" in values.split():
                return True
    except (OSError, subprocess.SubprocessError):
        return False
    return False


session_locked = logind_locked  # tests replace this, never the real logind


def terminal_argv(argv: list[str]) -> list[str]:
    """Each saved terminal window is its own Ghostty process, with the user's own configuration."""
    end = argv.index("-e") if "-e" in argv else len(argv)
    head = [a for a in argv[1:end] if a not in LOSSY_TERMINAL_FLAGS]
    if not any(a.startswith("--gtk-single-instance") for a in head):
        head.insert(0, "--gtk-single-instance=false")
    return [argv[0], *head, *argv[end:]]


def spawn_argv(group: dict) -> list[str]:
    argv, cwd = list(group["argv"]), group.get("cwd")
    if group["kind"] == "app" and isinstance(cwd, str) and os.path.isdir(cwd):
        return ["sh", "-c", CHDIR_EXEC, "sh", cwd, *argv]
    return argv


def layout_of(window: dict) -> tuple[int | None, int]:
    position = (window.get("layout") or {}).get("pos_in_scrolling_layout")
    return (position[0], position[1]) if position else (None, 1)


def saved_slots(snapshot: dict) -> list[dict]:
    """One slot per saved window, plus one per session found in its extra terminal tabs."""
    workspaces = {item["id"]: item for item in snapshot["workspaces"]}
    slots = []
    for window in sorted(snapshot["windows"], key=lambda item: item["id"]):
        recipe = window.get("reopen") or {"kind": "unknown", "argv": [], "reason": "no-recipe"}
        workspace = workspaces.get(window.get("workspace_id")) or {}
        column, tile = layout_of(window)
        slot = {
            "window_id": window["id"],
            "app_id": window.get("app_id"),
            "pid": window.get("pid"),
            "recipe": recipe,
            "saved_workspace_idx": workspace.get("idx"),
            "saved_workspace_name": workspace.get("name"),
            "column": column,
            "tile": tile,
            "width": (window.get("layout") or {}).get("tile_size", [None])[0],
            "floating": bool(window.get("is_floating")),
            "floating_position": (window.get("layout") or {}).get("tile_pos_in_workspace_view"),
        }
        slots.append(slot)
        for extra in recipe.get("extra") or []:
            slots.append(
                {**slot, "recipe": extra, "window_id": None, "extra_of": window["id"]}
                | {"column": None, "tile": 1, "width": None, "floating": False}
            )
    return slots


def live_session_argvs(current_windows: list[dict]) -> set[str]:
    found = set()
    for window in current_windows:
        recipe = window.get("reopen")
        for item in [recipe, *((recipe or {}).get("extra") or [])] if recipe else []:
            if isinstance(item, dict) and item.get("kind") in SESSION_KINDS:
                found.add(json.dumps(item.get("argv"), sort_keys=True))
    return found


def plan(snapshot: dict, current_windows: list[dict], *, entries=None, users=None) -> dict:
    """Pure: which groups launch, from where, and where each saved slot goes."""
    require_snapshot(snapshot)
    entries = routes.desktop_entries() if entries is None else entries
    users = routes.user_routes() if users is None else users
    slots = saved_slots(snapshot)
    known = sorted(
        {
            s["saved_workspace_idx"]
            for s in slots
            if s["recipe"].get("kind") != "unknown" and s["saved_workspace_idx"] is not None
        }
    )
    mapping = {idx: position for position, idx in enumerate(known, 1)}
    spare = len(known) + 1  # windows without a known saved place go to one new last workspace
    for slot in slots:
        slot["target_workspace_idx"] = mapping.get(slot["saved_workspace_idx"], spare)
        if slot["target_workspace_idx"] == spare:
            slot["column"] = None
    slots.sort(
        key=lambda s: (
            s["target_workspace_idx"],
            s["column"] is None,
            s["column"] or 0,
            s["tile"],
            s["window_id"] or 0,
        )
    )
    open_sessions = live_session_argvs(current_windows)
    running = {w.get("app_id") for w in current_windows if w.get("app_id")}
    instances = Counter(
        app_id
        for app_id, _ in {
            (s["app_id"], s["pid"]) for s in slots if s["recipe"].get("kind") == "app"
        }
    )
    groups, by_instance = [], {}
    for slot in slots:
        recipe, kind = slot["recipe"], slot["recipe"].get("kind")
        if (reason := refusal(recipe)) is not None:
            slot["status"] = "not-reopened"
            slot["reason"] = reason
        elif kind in SESSION_KINDS and json.dumps(recipe["argv"], sort_keys=True) in open_sessions:
            slot["status"] = "already-open"
        elif kind in TERMINAL_KINDS:
            groups.append(
                {
                    "kind": "terminal",
                    "app_id": slot["app_id"],
                    "route": "terminal",
                    "argv": terminal_argv(recipe["argv"]),
                    "cwd": None,
                    "slots": [slot],
                }
            )
        elif kind == "app":
            instance = (slot["app_id"], slot["pid"] or json.dumps(recipe["argv"]))
            if instance in by_instance:
                by_instance[instance]["slots"].append(slot)
                continue
            group = {"kind": "app", "app_id": slot["app_id"], "slots": [slot]}
            found = routes.route(
                slot["app_id"],
                recipe,
                single_instance=instances[slot["app_id"]] == 1,
                entries=entries,
                users=users,
            )
            group.update(found or {"skip": "no-route"})  # shown in the dry run even when skipped
            if slot["app_id"] in running:
                group["skip"] = "already-running"  # never a second instance, never its windows
            by_instance[instance] = group
            groups.append(group)
        else:
            slot["status"] = "not-reopened"
            slot["reason"] = f"unsupported-kind:{kind}"
    for number, group in enumerate(groups, 1):
        for slot in group["slots"]:
            slot["group"] = number
    names = {
        mapping[s["saved_workspace_idx"]]: s["saved_workspace_name"]
        for s in slots
        if s["saved_workspace_idx"] in mapping and s["saved_workspace_name"]
    }
    return {
        "slots": slots,
        "groups": groups,
        "workspace_names": names,
        "protected_window_ids": sorted(w["id"] for w in current_windows),
        "unknown_workspace_idx": spare
        if any(s["target_workspace_idx"] == spare for s in slots)
        else None,
    }


def collect(desktop, known: set[int], app_id, wanted: int, timeout: float) -> list[dict]:
    """New windows of exactly this app, until enough arrive, they stop arriving, or time runs out."""
    deadline = desktop.monotonic() + timeout
    found: dict[int, dict] = {}
    last = None
    while True:
        for window in desktop.windows():
            if window["id"] in known or window["id"] in found or app_id is None:
                continue
            if window.get("app_id") == app_id:
                found[window["id"]] = window
                last = desktop.monotonic()
        moment = desktop.monotonic()
        if len(found) >= wanted or moment >= deadline or (last and moment - last >= QUIET):
            return [found[key] for key in sorted(found)]
        desktop.sleep(POLL_INTERVAL)


def row(slot: dict, group: dict | None) -> dict:
    record = {k: v for k, v in slot.items() if k not in {"recipe", "pid"}}
    record["kind"] = slot["recipe"].get("kind")
    record["argv"] = group["argv"] if group and group.get("argv") else slot["recipe"].get("argv")
    if group:
        record["route"] = group.get("route")
    return record


def decoration(desktop, window_id: int) -> float:
    """Tile width minus window width (borders), as Niri reports it now; 0 when not reported."""
    layout = next((w.get("layout") or {} for w in desktop.windows() if w["id"] == window_id), {})
    tile, window = (layout.get("tile_size") or [None])[0], (layout.get("window_size") or [None])[0]
    numbers = all(isinstance(v, (int, float)) for v in (tile, window))
    return tile - window if numbers and tile >= window else 0.0


def arrange_workspace(desktop, idx: int, placed: list[dict], protected: set[int]) -> list[dict]:
    """Rebuild saved column order after existing (protected) columns on one workspace."""
    effects: list[dict] = []
    workspace_id = {w["idx"]: w["id"] for w in desktop.workspaces()}.get(idx)
    live = [w for w in desktop.windows() if w.get("workspace_id") == workspace_id]
    offset = len(
        {layout_of(w)[0] for w in live if w["id"] in protected and not w.get("is_floating")}
    )
    columns: dict[int, list[dict]] = {}
    for entry in placed:
        if not entry.get("floating") and entry.get("column") is not None:
            columns.setdefault(entry["column"], []).append(entry)
    for rank, column in enumerate(sorted(columns), 1):
        tiles = sorted(columns[column], key=lambda e: e["tile"])
        target, seed = offset + rank, tiles[0]["restored_window_id"]
        desktop.action("focus-window", "--id", str(seed))
        desktop.action("move-column-to-index", str(target))
        effects.append({"window_id": seed, "action": "move-column-to-index", "index": target})
        for extra in tiles[1:]:
            desktop.action("focus-window", "--id", str(extra["restored_window_id"]))
            desktop.action("move-column-to-index", str(target + 1))
            desktop.action("focus-window", "--id", str(seed))
            desktop.action("consume-window-into-column")
            effects.append(
                {"window_id": extra["restored_window_id"], "action": "consume-into-column"}
            )
        width = tiles[0].get("width")
        if isinstance(width, (int, float)) and width > 0:
            # After stacking, so every tile gets it. The saved width is the tile's; Niri's fixed
            # column width is the window's, so subtract the seed's measured border decoration.
            request = int(round(width - decoration(desktop, seed)))
            if request > 0:
                desktop.action("set-column-width", str(request))
                effects.append({"window_id": seed, "action": "set-column-width", "width": request})
    for entry in placed:
        if entry.get("floating") and entry.get("restored_window_id") is not None:
            wid = str(entry["restored_window_id"])
            desktop.action("move-window-to-floating", "--id", wid)
            position = entry.get("floating_position")
            if isinstance(position, list) and len(position) == 2:
                x, y = (str(int(round(value))) for value in position)
                desktop.action("move-floating-window", "--id", wid, "-x", x, "-y", y)
            effects.append({"window_id": entry["restored_window_id"], "action": "float"})
    return effects


def reopen(
    store,
    snapshot_key: str,
    desktop,
    *,
    apply: bool,
    observe=None,
    spawn_timeout: float = SPAWN_TIMEOUT,
    entries=None,
    users=None,
) -> dict:
    """observe() is a full capture of the current desktop (with recipes); desktop is Niri IPC."""
    snapshot = store.get("snapshots", snapshot_key)
    if not readiness(snapshot)["ready"]:
        raise ValueError("saved snapshot is not display-valid; refusing to reopen from it")
    observe = observe or probe.capture
    if apply and session_locked():
        raise ValueError(
            "the session is locked: Niri would not launch anything; unlock and run again"
        )
    if apply:
        from .restore_exited import historical_replay

        replay = historical_replay(snapshot, snapshot_key)  # exited-shell v3 sources
        if replay is not None:
            return replay
    identity = probe.compositor_identity()
    # An unresolved earlier attempt still blocks --apply; a dry run only serializes.
    with locks.operation_lock(identity, effectful=apply):
        replay = historical(identity, snapshot_key) if apply else None
        if replay is not None:
            return replay
        current = observe()
        the_plan = plan(snapshot, current["windows"], entries=entries, users=users)
        return _run(store, snapshot_key, desktop, current, the_plan, apply, spawn_timeout)


def historical(identity: dict, key: str) -> dict | None:
    """A source the earlier strict engine already attempted gets its recorded answer, no effects."""
    from . import restore_history as history

    completed = history.admit(identity)[0]
    found = next((h for h in completed if h["snapshot_digest"] == key), None)
    if found is None:
        return None
    accepted = found["result"]["status"] == "operator-accepted-partial"
    return {
        "snapshot_digest": key,
        "receipt_digest": found["receipt_digest"],
        **found["result"],
        "historical": True,
        "fresh_native_verification": False,
        **({"effects": [], "retry_authorized": False} if accepted else {}),
    }


def _run(store, snapshot_key, desktop, current, the_plan, apply, spawn_timeout) -> dict:
    receipt = {
        "schema": RESTORE_SCHEMA,
        "snapshot_digest": snapshot_key,
        "started_at": now(),
        "apply": apply,
        "protected_window_ids": the_plan["protected_window_ids"],
        "unknown_workspace_idx": the_plan["unknown_workspace_idx"],
        "groups": len(the_plan["groups"]),
        "windows": [],
        "effects": [],
        "status": "dry-run",
    }
    groups = {id(s): g for g in the_plan["groups"] for s in g["slots"]}
    failures = 0
    if not apply:
        for slot in the_plan["slots"]:
            group = groups.get(id(slot))
            record = row(slot, group)
            record.setdefault("status", (group or {}).get("skip") or "planned")
            receipt["windows"].append(record)
        return finish(store, receipt, snapshot_key, 0)
    protected = set(the_plan["protected_window_ids"])
    known = set(protected)
    focus = next((w["id"] for w in current["windows"] if w.get("is_focused")), None)
    placed: dict[int, list[dict]] = {}
    records = {id(s): row(s, groups.get(id(s))) for s in the_plan["slots"]}
    failures = sum(1 for s in the_plan["slots"] if s.get("status") == "not-reopened")
    try:
        for number, group in enumerate(the_plan["groups"], 1):
            if group.get("skip"):
                for slot in group["slots"]:
                    records[id(slot)]["status"] = group["skip"]
                failures += len(group["slots"]) if group["skip"] == "no-route" else 0
                continue
            desktop.spawn(spawn_argv(group))  # exactly once per group, never again
            receipt["effects"].append(
                {"action": "spawn", "group": number, "route": group["route"], "at": now()}
            )
            arrived = collect(desktop, known, group["app_id"], len(group["slots"]), spawn_timeout)
            known.update(w["id"] for w in arrived)
            for slot, window in zip(group["slots"], arrived):
                record = records[id(slot)]
                record["restored_window_id"] = window["id"]
                target = str(slot["target_workspace_idx"])
                desktop.action(
                    "move-window-to-workspace",
                    "--window-id",
                    str(window["id"]),
                    "--focus",
                    "false",
                    target,
                )
                receipt["effects"].append(
                    {
                        "action": "move-window-to-workspace",
                        "window_id": window["id"],
                        "index": target,
                    }
                )
                record["status"] = "placed"
                placed.setdefault(slot["target_workspace_idx"], []).append(record)
            for slot in group["slots"][len(arrived) :]:
                records[id(slot)]["status"] = "not-detected"
                failures += 1
        for idx in sorted(placed):
            receipt["effects"].extend(arrange_workspace(desktop, idx, placed[idx], protected))
        for idx, name in sorted(the_plan["workspace_names"].items()):
            if idx in placed:
                desktop.action("set-workspace-name", "--workspace", str(idx), name)
                receipt["effects"].append({"action": "set-workspace-name", "index": idx})
        if focus is not None and any(w["id"] == focus for w in desktop.windows()):
            desktop.action("focus-window", "--id", str(focus))
        receipt["status"] = "reopened" if not failures else "reopened-partially"
    except Exception as exc:  # noqa: BLE001 - the receipt must record any interruption
        receipt["status"] = "interrupted"
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)
    receipt["windows"] = [records[id(s)] for s in the_plan["slots"]]
    return finish(store, receipt, snapshot_key, failures)


def finish(store, receipt: dict, snapshot_key: str, failures: int) -> dict:
    for record in receipt["windows"]:
        record.setdefault("status", "planned" if not receipt["apply"] else "not-attempted")
    receipt["failures"] = failures
    receipt["finished_at"] = now()
    key = store.put("receipts", receipt)
    if receipt["status"].startswith("reopened"):
        store.pointer("last-reopened", snapshot_key)
    return {"receipt_digest": key, **receipt}
