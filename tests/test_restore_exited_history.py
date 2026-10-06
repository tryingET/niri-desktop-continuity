"""Handwritten ten-record legacy oracle; no v3 or transition constructor supplies it."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.store import Store

FAMILY = "associated-shell-protected-dimensions-interrupted"


def sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def scene(phase):
    locations = {70: (1, 1), 80: (2, 1)}
    if phase:
        locations[12000] = (2, 2) if phase == 1 else (1, 2)
    focus = 12000 if phase in (1, 3) else 80
    return {
        "windows": [
            {
                "id": wid,
                "pid": 2000 if wid == 12000 else wid + 1000000,
                "workspace_id": ws,
                "is_floating": False,
                "is_focused": wid == focus,
                "layout": {
                    "pos_in_scrolling_layout": [column, 1],
                    "tile_size": [800.0 if wid == 12000 else 640.0, 1000.0],
                    "window_size": [788.0 if wid == 12000 else 628.0, 988.0],
                    "tile_pos_in_workspace_view": None,
                },
            }
            for wid, (ws, column) in sorted(locations.items())
        ],
        "workspaces": [
            {
                "id": ws,
                "idx": ws,
                "output": "FIXTURE-1",
                "name": None,
                "is_active": ws == (1 if phase == 3 else 2),
                "is_focused": ws == (1 if phase == 3 else 2),
                "active_window_id": (12000 if phase == 3 else 70)
                if ws == 1
                else (12000 if phase == 1 else 80),
            }
            for ws in (1, 2)
        ],
        "outputs": [{"name": "FIXTURE-1", "scale": 1.0}],
    }


def fabricate(tmp_path, monkeypatch, *, identity=None, process=None, peer=None):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    identity = identity or {
        "boot_id": "fabricated-boot",
        "socket_device": 11,
        "socket_inode": 22,
        "niri_socket": "/fabricated/niri.sock",
    }
    process = process or {"boot_id": identity["boot_id"], "pid": 2000, "start_ticks": 1}
    peer = peer or {"pid": 3000, "start_ticks": 2, "ppid": 1, "comm": "fixture", "cgroup": None}
    store = Store(tmp_path / "store")
    recipe = {"kind": "shell", "argv": ["/fabricated/ghostty"], "cwd": "/fabricated/cwd"}
    controlled = {
        **recipe,
        "argv": [
            "/fabricated/ghostty",
            "--config-default-files=false",
            "--gtk-single-instance=false",
            "--initial-window=true",
            "--working-directory=/fabricated/cwd",
        ],
    }
    base, arrived, moved, focused = [scene(i) for i in range(4)]
    for state in (arrived, moved, focused):
        next(w for w in state["windows"] if w["id"] == 12000)["pid"] = process["pid"]
    snapshot = {
        "schema": "desktop-continuity.snapshot.v1",
        "identity": identity,
        "coherent": True,
        "outputs": [{"name": "FIXTURE-1", "logical": {"scale": 1.0}, "current_mode": 0}],
        "workspaces": deepcopy(base["workspaces"]),
        "layers": [],
        "processes": [],
        "inventory_complete": True,
        "process_inventory": [peer],
        "niri_version": {"compositor": "fixture-version", "cli": "fixture-client"},
        "windows": [
            {
                "id": 1,
                "pid": 101,
                "app_id": "ghostty",
                "workspace_id": 1,
                "is_floating": False,
                "layout": {"pos_in_scrolling_layout": [1, 1], "tile_size": [800.0, 1000.0]},
                "reopen": recipe,
            }
        ],
    }
    source_entry = {
        "window_id": 1,
        "app_id": "ghostty",
        "recipe": recipe,
        "saved_workspace_idx": 1,
        "saved_workspace_name": None,
        "column": 1,
        "tile": 1,
        "width": 800.0,
        "floating": False,
        "floating_position": None,
        "target_workspace_idx": 1,
    }
    entry = {**source_entry, "recipe": controlled}
    source_plan = {
        "entries": [source_entry],
        "workspace_names": {},
        "protected_window_ids": [70, 80],
        "unknown_workspace_idx": None,
    }
    plan = {
        **source_plan,
        "entries": [entry],
        "source_plan": source_plan,
        "mode": "restore",
        "baseline": base,
        "baseline_recipes": [{"id": 70, "recipe": None}, {"id": 80, "recipe": None}],
        "initial_accounting": [{"entry": entry, "window_id": 1, "status": "unprocessed"}],
    }
    source = store.put("snapshots", snapshot)
    bootstrap = {
        "action": "bootstrap",
        "details": {
            "entry": 0,
            "nonce": "a" * 64,
            "spec": {"argv": controlled["argv"], "cwd": controlled["cwd"]},
            "image": {"device": 1, "inode": 2, "sha256": "b" * 64},
            "directory": {"device": 1, "inode": 3},
        },
    }
    execute = {"action": "exec", "details": {"entry": 0, "process": process, "binding": "c" * 64}}
    evidence = {
        "phase": "process-observed",
        "ownership": "process-only",
        "process": process,
        "binding": "c" * 64,
        "window_ownership": "not-proved",
        "placement": "not-attempted",
        "native_session": "not-proved",
        "settlement": "unresolved",
    }
    process_key = store.put("receipts", evidence)
    actions = [
        ["move-window-to-workspace", "--window-id", "12000", "--focus", "false", "1"],
        ["focus-window", "--id", "12000"],
    ]
    move = {
        "action": "layout",
        "details": {
            "argv": actions[0],
            "before": arrived,
            "expected": moved,
            "measured_float": None,
            "target": {"workspace_id": 1, "output": "FIXTURE-1", "index": 1},
        },
    }
    focus = {
        "action": "layout",
        "details": {
            "argv": actions[1],
            "before": moved,
            "expected": focused,
            "measured_float": None,
            "target": None,
        },
    }
    transcript = [
        ("prepared", {"identity": identity, "snapshot_digest": source, "plan": plan}),
        ("intent", bootstrap),
        (
            "observed",
            {"intent": sha(bootstrap), "evidence": {"bootstrap": process, "binding": "c" * 64}},
        ),
        ("intent", execute),
        ("observed", {"intent": sha(execute), "evidence": evidence}),
        ("association", {"entry": 0, "before": base, "after": arrived}),
        ("intent", move),
        ("observed", {"intent": sha(move), "evidence": {"layout": moved}}),
        ("intent", focus),
        ("observed", {"intent": sha(focus), "evidence": {"layout": focused}}),
    ]
    attempt, previous = "d" * 64, None
    origin = {
        "root": str(store.root),
        "pin": {"device": store.root.stat().st_dev, "inode": store.root.stat().st_ino},
    }
    with operation_lock.operation_lock(identity, effectful=False):
        directory = history.fence_path(identity)
        directory.mkdir(mode=0o700)
        for seq, (kind, payload) in enumerate(transcript):
            key = store.put("receipts", payload)
            assert key == sha(payload)
            record = {
                "schema": "desktop-continuity.restore-history.v3",
                "seq": seq,
                "previous": previous,
                "type": kind,
                "attempt": attempt,
                "receipt": key,
                "origin": origin,
            }
            path = directory / f"{seq:08d}.json"
            path.write_text(json.dumps(record) + "\n")
            path.chmod(0o600)
            previous = sha(record)
    receipt = {
        "status": "interrupted",
        "windows": [
            {
                "entry": entry,
                "window_id": 1,
                "status": "owned-not-placed",
                "geometry_coverage": {"width": "requested-observed", "position": "not-recorded"},
                "process_receipt": process_key,
                "restored_window_id": 12000,
                "observed_initial_width": 800.0,
                "target_workspace_id": 1,
            }
        ],
        "effects": actions,
        "final_observation": {"unavailable": True},
        "native_session": "not-proved",
        "error_type": "ValueError",
        "error": "protected dimensions changed",
    }
    interrupted = store.put("receipts", receipt)
    result, exit_file = store.root / "original-result.json", store.root / "original-exit.txt"
    result.write_text(
        json.dumps({"snapshot_digest": source, "receipt_digest": interrupted, **receipt})
    )
    exit_file.write_text("2\n")
    result.chmod(0o600)
    exit_file.chmod(0o600)
    return SimpleNamespace(
        **{
            k: v
            for k, v in locals().items()
            if k
            in (
                "store",
                "identity",
                "attempt",
                "source",
                "snapshot",
                "interrupted",
                "result",
                "exit_file",
                "directory",
                "transcript",
                "receipt",
                "actions",
                "process",
                "peer",
            )
        }
    )


@pytest.fixture
def legacy_ten(tmp_path, monkeypatch):
    return fabricate(tmp_path, monkeypatch)


def test_given_ten_legacy_records_when_inspected_then_historical_only(legacy_ten, monkeypatch):
    s = legacy_ten
    with operation_lock.operation_lock(s.identity, effectful=False):
        assert history.load(s.identity)[2] == 10  # Actual ordinary semantics, not hashes alone.
    monkeypatch.setattr("os.fsync", lambda *_: pytest.fail("inspection must not fsync"))
    result = disposition.inspect(
        s.store, None, s.attempt, s.interrupted, s.result, s.exit_file, family=FAMILY
    )
    assert result["eligible_family"] is True
    assert result["current_proof"] == "not-performed"
    assert result["admission"] == "not-granted"
