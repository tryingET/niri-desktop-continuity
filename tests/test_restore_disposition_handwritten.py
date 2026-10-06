"""Handwritten pre-fix producer transcript. No executor/planner/predictor constructs this oracle."""

import hashlib
import json
import os
from copy import deepcopy
from types import SimpleNamespace

import pytest

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_disposition_evidence as e
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity.store import Store


def sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def state(order, focused, widths):
    return {
        "outputs": [{"name": "DP-1", "scale": 1.0}],
        "windows": [
            {
                "id": wid,
                "pid": 2000 if wid == 12000 else wid + 100,
                "workspace_id": 1,
                "is_floating": False,
                "is_focused": wid == focused,
                "layout": {
                    "pos_in_scrolling_layout": [order.index(wid) + 1, 1],
                    "tile_size": [widths[wid], 1000.0],
                    "window_size": [widths[wid] - 12.0, 988.0],
                    "tile_pos_in_workspace_view": None,
                },
            }
            for wid in sorted(order)
        ],
        "workspaces": [
            {
                "id": 1,
                "idx": 1,
                "output": "DP-1",
                "name": None,
                "is_focused": True,
                "is_active": True,
                "active_window_id": focused,
            },
            {
                "id": 2,
                "idx": 2,
                "output": "DP-1",
                "name": None,
                "is_focused": False,
                "is_active": False,
                "active_window_id": None,
            },
        ],
    }


@pytest.fixture
def handwritten(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    identity = {
        "boot_id": "fabricated-boot",
        "socket_device": 11,
        "socket_inode": 22,
        "niri_socket": "/fabricated/niri.sock",
    }
    store = Store(tmp_path / "store")
    source_recipe = {"kind": "shell", "argv": ["/fabricated/ghostty"], "cwd": "/fabricated/cwd"}
    controlled = {
        "kind": "shell",
        "cwd": "/fabricated/cwd",
        "argv": [
            "/fabricated/ghostty",
            "--config-default-files=false",
            "--gtk-single-instance=false",
            "--initial-window=true",
            "--working-directory=/fabricated/cwd",
        ],
    }
    base = state([70, 80], 70, {70: 640.0, 80: 720.0})
    arrived = state([70, 12000, 80], 12000, {70: 640.0, 80: 720.0, 12000: 800.0})
    moved = state([70, 80, 12000], 12000, {70: 640.0, 80: 720.0, 12000: 800.0})
    predicted = state([70, 80, 12000], 12000, {70: 640.0, 80: 720.0, 12000: 900.0})
    snapshot = {
        "schema": "desktop-continuity.snapshot.v1",
        "identity": {**identity, "boot_id": "old"},
        "coherent": True,
        "outputs": [{"name": "DP-1", "logical": {"w": 1920}, "current_mode": 0}],
        "workspaces": deepcopy(base["workspaces"]),
        "layers": [],
        "processes": [],
        "windows": [
            {
                "id": 1,
                "pid": 101,
                "app_id": "ghostty",
                "workspace_id": 1,
                "is_floating": False,
                "layout": {"pos_in_scrolling_layout": [1, 1], "tile_size": [900.0, 1000.0]},
                "reopen": source_recipe,
            }
        ],
    }
    source_entry = {
        "window_id": 1,
        "app_id": "ghostty",
        "recipe": source_recipe,
        "saved_workspace_idx": 1,
        "saved_workspace_name": None,
        "column": 1,
        "tile": 1,
        "width": 900.0,
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
    source_key = store.put("snapshots", snapshot)
    process = {"boot_id": identity["boot_id"], "pid": 2000, "start_ticks": 1}
    image = {"device": 1, "inode": 2, "sha256": "b" * 64}
    process_evidence = {
        "phase": "process-observed",
        "ownership": "process-only",
        "process": process,
        "binding": "c" * 64,
        "window_ownership": "not-proved",
        "placement": "not-attempted",
        "native_session": "not-proved",
        "settlement": "unresolved",
    }
    process_key = store.put("receipts", process_evidence)
    prepared = {"identity": identity, "snapshot_digest": source_key, "plan": plan}
    bootstrap = {
        "action": "bootstrap",
        "details": {
            "entry": 0,
            "nonce": "a" * 64,
            "spec": {"argv": controlled["argv"], "cwd": controlled["cwd"]},
            "image": image,
            "directory": {"device": 1, "inode": 3},
        },
    }
    execute = {"action": "exec", "details": {"entry": 0, "process": process, "binding": "c" * 64}}
    move = {
        "action": "layout",
        "details": {
            "argv": ["move-column-to-index", "3"],
            "before": arrived,
            "expected": moved,
            "measured_float": None,
            "target": None,
        },
    }
    width = {
        "action": "layout",
        "details": {
            "argv": ["set-column-width", "888.0"],
            "before": moved,
            "expected": predicted,
            "measured_float": None,
            "target": None,
        },
    }
    # EXACT handwritten record sequence; observations are supplied, not predicted by runtime code.
    transcript = [
        ("prepared", prepared),
        ("intent", bootstrap),
        (
            "observed",
            {"intent": sha(bootstrap), "evidence": {"bootstrap": process, "binding": "c" * 64}},
        ),
        ("intent", execute),
        ("observed", {"intent": sha(execute), "evidence": process_evidence}),
        ("association", {"entry": 0, "before": base, "after": arrived}),
        ("intent", move),
        ("observed", {"intent": sha(move), "evidence": {"layout": moved}}),
        ("intent", width),
    ]
    attempt, previous = "d" * 64, None
    origin = {
        "root": str(store.root),
        "pin": {"device": store.root.stat().st_dev, "inode": store.root.stat().st_ino},
    }
    with operation_lock.operation_lock(identity, effectful=False):
        directory = (
            runtime
            / "niri-desktop-continuity-locks"
            / (
                sha({k: identity[k] for k in ("boot_id", "socket_device", "socket_inode")})
                + ".restore"
            )
        )
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
            path.write_text(json.dumps(record, sort_keys=True) + "\n")
            path.chmod(0o600)
            previous = sha(record)
    receipt = {
        "status": "interrupted",
        "windows": [
            {
                "entry": entry,
                "window_id": 1,
                "status": "owned-not-placed",
                "geometry_coverage": {"width": "requested-pending"},
                "process_receipt": process_key,
                "restored_window_id": 12000,
                "observed_initial_width": 800.0,
                "target_workspace_id": 1,
            }
        ],
        "effects": [["move-column-to-index", "3"]],
        "final_observation": moved,
        "native_session": "not-proved",
        "error_type": "CalledProcessError",
        "error": "Command '['niri', 'msg', 'action', 'set-column-width', '888.0']' returned non-zero exit status 2.",
    }
    interrupted = store.put("receipts", receipt)
    result, exit_file = store.root / "original-result.json", store.root / "original-exit.txt"
    result.write_text(
        json.dumps({"snapshot_digest": source_key, "receipt_digest": interrupted, **receipt})
    )
    exit_file.write_text("2\n")
    result.chmod(0o600)
    exit_file.chmod(0o600)

    class Process:
        def __init__(self, pid):
            self.pin = {**process, "pid": pid}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def live(self):
            pass

        def validate(self, expected):
            assert expected == image

        def argv(self):
            return controlled["argv"]

    class Image(Process):
        def __init__(self, path):
            assert path == controlled["argv"][0]
            self.pin = image

    class Directory(Process):
        def __init__(self, path, pin, process):
            assert pin == {"device": 1, "inode": 3}
            self.value = {"path": path, "directory": pin, "process_directory": pin}

        def validate(self):
            return self.value

    monkeypatch.setattr(host, "Process", Process)
    monkeypatch.setattr(host, "Image", Image)
    monkeypatch.setattr(e, "Directory", Directory)
    monkeypatch.setattr(e, "controller_pids", lambda: {9999})
    monkeypatch.setattr(os, "kill", lambda *_: pytest.fail("no effects"))
    current = state([70, 80, 12000], 70, {70: 660.0, 80: 720.0, 12000: 812.0})
    return SimpleNamespace(
        store=store,
        identity=identity,
        attempt=attempt,
        interrupted=interrupted,
        result=result,
        exit_file=exit_file,
        directory=directory,
        observe=lambda: {"identity": identity, "coherent": True, "state": deepcopy(current)},
    )


def test_handwritten_prefixed_decimal_disposition_flow(handwritten):
    s = handwritten
    originals = {p: p.read_bytes() for p in s.directory.iterdir()}
    with operation_lock.operation_lock(s.identity, effectful=False):
        assert history.load(s.identity)[2] == 9
    with pytest.raises(ValueError):
        with operation_lock.operation_lock(s.identity):
            pytest.fail("decimal data cannot admit a writer")
    key = d.propose(
        s.store, s.identity, s.attempt, s.interrupted, s.result, s.exit_file, observer=s.observe
    )["plan_digest"]
    approved = d.approve(
        s.store,
        key,
        confirmation=key,
        acceptance="operator-accepted-partial",
        attest_client_returned=True,
        observer=s.observe,
    )["approval_digest"]
    result = d.apply(s.store, approved, observer=s.observe)
    assert result["status"] == "operator-accepted-partial" and result["effects"] == []
    assert result["historical_completion"] == "unproved" and not result["retry_authorized"]
    assert {p: p.read_bytes() for p in originals} == originals
    assert s.store.pointer("last-reopened") is None
    with operation_lock.operation_lock(s.identity):
        pass
