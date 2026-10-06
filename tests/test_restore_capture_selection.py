"""Given fabricated whole-desktop reads, select saved windows through the actual CLI."""

import json
import subprocess
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_reopen import IDENTITY, recipe, window

from niri_desktop_continuity import cli, launch, operation_lock, probe, restore, restore_host
from niri_desktop_continuity.model import digest, readiness, require_snapshot
from niri_desktop_continuity.store import Store


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    # Deliberately non-ID order: neither normalization nor selection may reorder windows.
    source = [
        window(30, 5, 2, reopen=recipe("shell", "ghostty")),
        window(0, 1, 1, reopen=recipe("app", "fabricated-browser")),
        window(10, 2, 3, reopen=recipe("unknown")),
    ]
    source[2]["reopen"] = {"kind": "unknown", "argv": [], "reason": "no-recipe"}
    workspaces = [
        {"id": 1, "idx": 1, "output": "DP-1", "is_focused": True},
        {"id": 2, "idx": 2, "output": "DP-1"},
        {"id": 5, "idx": 4, "output": "DP-1", "name": "lab"},
        {"id": 9, "idx": 5, "output": "DP-1", "name": "empty"},
    ]
    processes = [{"pid": 130, "start_ticks": 1}, {"pid": 100, "start_ticks": 2}]
    data = {
        "windows": source,
        "workspaces": workspaces,
        "outputs": {"DP-1": {"logical": {"w": 1000}, "current_mode": 0}},
        "layers": [{"namespace": "fabricated-panel", "output": "DP-1", "layer": "top"}],
        "version": "fabricated",
    }
    calls = {"queries": [], "processes": [], "inventory": 0, "recipes": [], "effects": 0}
    observations = []

    class IPC:
        def query(self, command):
            calls["queries"].append(command)
            return deepcopy(data[command])

    def window_processes(windows):
        calls["processes"].append([w["id"] for w in windows])
        return deepcopy(processes), []

    def inventory():
        calls["inventory"] += 1
        return [*deepcopy(processes), {"pid": 999, "ppid": 130}], True

    def recipes(windows, *_args):
        calls["recipes"].append([w["id"] for w in windows])
        return {w["id"]: deepcopy(w["reopen"]) for w in source}

    def forbidden(*_args, **_kwargs):
        calls["effects"] += 1
        pytest.fail("capture/dry-run attempted an external process or desktop action")

    real_capture = probe.capture

    def observe(**kwargs):
        value = real_capture(**kwargs)
        observations.append((value, deepcopy(value)))
        return value

    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    monkeypatch.setattr(probe, "Niri", IPC)
    monkeypatch.setattr(probe, "compositor_identity", lambda: dict(IDENTITY))
    monkeypatch.setattr(restore, "compositor_identity", lambda: dict(IDENTITY))
    monkeypatch.setattr(probe, "now", lambda: "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(probe, "window_processes", window_processes)
    monkeypatch.setattr(probe, "process_inventory", inventory)
    # Capture lazily imports the owner; patch that real function without restoring a
    # removed probe export or defeating the independent import-scope contract.
    monkeypatch.setattr(launch, "window_recipes", recipes)
    monkeypatch.setattr(probe, "capture", observe)
    monkeypatch.setattr(cli, "capture", observe)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(restore.LiveDesktop, "action", forbidden)
    monkeypatch.setattr(restore.LiveDesktop, "spawn", forbidden)
    yield SimpleNamespace(
        root=tmp_path / "state", source=source, calls=calls, observations=observations
    )
    assert calls["effects"] == 0
    assert all(value == before for value, before in observations)


def invoke(desktop, capsys, *arguments):
    status = cli.main(["--state-root", str(desktop.root), *arguments])
    output = capsys.readouterr()
    assert not output.err
    assert status == 0
    return json.loads(output.out)


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_given_no_selector_when_capture_then_original_bytes_and_result(desktop, capsys):
    result = invoke(desktop, capsys, "capture")
    original = desktop.observations[0][1]
    assert [w["id"] for w in original["windows"]] == [30, 0, 10]
    assert result == {
        "snapshot_digest": digest(original),
        "display": {"ready": True, "reasons": []},
        "windows": 3,
        "warnings": [],
    }
    store = Store(desktop.root)
    assert (
        store.path("snapshots", result["snapshot_digest"]).read_bytes()
        == (json.dumps(original, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    )
    assert store.pointer("latest-observed") == result["snapshot_digest"]
    assert "capture_selection" not in original


@pytest.mark.parametrize("ids,expected", [([30], [30]), ([0], [0]), ([0, 30], [30, 0])])
@pytest.mark.parametrize("titles", [False, True])
def test_given_ids_when_capture_then_exact_scope_and_full_support(
    desktop, capsys, ids, expected, titles
):
    args = ["capture", *(["--include-titles"] if titles else [])]
    for wid in ids:
        args.extend(["--window-id", str(wid)])
    result = invoke(desktop, capsys, *args)
    store = Store(desktop.root)
    selected = store.get("snapshots", result["snapshot_digest"])
    original = desktop.observations[0][1]
    assert [w["id"] for w in selected["windows"]] == expected
    assert selected["windows"] == [w for w in original["windows"] if w["id"] in ids]
    provenance = {"kind": "window-ids", "window_ids": sorted(ids), "observed_window_count": 3}
    assert selected["capture_selection"] == result["capture_selection"] == provenance
    assert result["windows"] == len(expected)
    assert selected["display"] == result["display"] == {"ready": True, "reasons": []}
    assert {k: v for k, v in selected.items() if k not in {"windows", "capture_selection"}} == {
        k: v for k, v in original.items() if k != "windows"
    }
    require_snapshot(selected)
    assert result["snapshot_digest"] != digest(original)
    assert (
        store.pointer("latest-observed") == store.pointer("last-display-valid") == digest(selected)
    )
    assert len(list((desktop.root / "snapshots").glob("*.json"))) == 1
    # Handwritten whole-desktop read oracle: this is NOT selective probing.
    assert desktop.calls == {
        "queries": [
            "windows",
            "workspaces",
            "outputs",
            "layers",
            "version",
            "windows",
            "workspaces",
            "outputs",
            "layers",
        ],
        "processes": [[30, 0, 10], [30, 0, 10]],
        "inventory": 1,
        "recipes": [[30, 0, 10]],
        "effects": 0,
    }


@pytest.mark.parametrize("seed", [False, True])
@pytest.mark.parametrize(
    "selectors,diagnostic",
    [
        (["--window-id", "30", "--window-id", "30"], "duplicate"),
        (["--window-id", "30", "--window-id", "999"], "absent"),
        (["--window-id", "-1"], "nonnegative"),
        (["--window-id", "1.5"], "invalid int"),
        (["--window-id", "no"], "invalid int"),
        (["--window-id"], "expected one argument"),
    ],
)
def test_given_bad_selector_when_capture_then_no_artifact_or_promotion(
    desktop, capsys, seed, selectors, diagnostic
):
    if seed:
        invoke(desktop, capsys, "capture")
    before = files(desktop.root)
    try:
        status = cli.main(["--state-root", str(desktop.root), "capture", *selectors])
    except SystemExit as exc:
        status = exc.code
    output = capsys.readouterr()
    assert status == 2
    assert not output.out
    assert diagnostic in output.err
    assert files(desktop.root) == before


def test_given_reordered_selectors_when_capture_then_same_digest(desktop, capsys):
    full = invoke(desktop, capsys, "capture")
    first = invoke(desktop, capsys, "capture", "--window-id", "0", "--window-id", "30")
    second = invoke(desktop, capsys, "capture", "--window-id", "30", "--window-id", "0")
    assert first == second
    assert first["snapshot_digest"] != full["snapshot_digest"]
    store = Store(desktop.root)
    assert [w["id"] for w in store.get("snapshots", full["snapshot_digest"])["windows"]] == [
        30,
        0,
        10,
    ]


@pytest.mark.parametrize("selected,ready", [(30, True), (10, False)])
def test_given_unavailable_unselected_window_when_capture_then_readiness_matches(
    desktop, capsys, selected, ready
):
    desktop.source[2]["workspace_id"] = 999
    result = invoke(desktop, capsys, "capture", "--window-id", str(selected))
    store = Store(desktop.root)
    value = store.get("snapshots", result["snapshot_digest"])
    assert value["display"] == result["display"] == readiness(value)
    assert value["display"] == {
        "ready": ready,
        "reasons": [] if ready else ["window-on-unavailable-workspace"],
    }
    assert store.pointer("last-display-valid") == (result["snapshot_digest"] if ready else None)


def test_given_extra_recipe_when_selected_then_dry_run_keeps_both_entries(desktop, capsys):
    desktop.source[0]["reopen"]["extra"] = [recipe("command", "ghostty", "-e", "fabricated")]
    result = invoke(desktop, capsys, "capture", "--window-id", "30")
    store = Store(desktop.root)
    key = result["snapshot_digest"]
    original_bytes = store.path("snapshots", key).read_bytes()
    selected = store.get("snapshots", key)
    assert selected["windows"][0]["reopen"]["extra"] == [
        {
            "schema": "desktop-continuity.launch-recipe.v1",
            "kind": "command",
            "argv": ["ghostty", "-e", "fabricated"],
            "cwd": None,
            "label": None,
        }
    ]
    result = invoke(desktop, capsys, "restore", key)
    assert result["status"] == "dry-run"
    assert result["snapshot_digest"] == key
    assert result["apply"] is False and result["effects"] == []
    assert len(result["windows"]) == 2  # One selected window is NOT one launch.
    assert [
        (w["window_id"], w["kind"], w["saved_workspace_idx"], w["target_workspace_idx"])
        for w in result["windows"]
    ] == [(30, "shell", 4, 1), (None, "command", 4, 1)]
    assert result["windows"][1]["extra_of"] == 30
    assert result["protected_window_ids"] == [0, 10, 30]
    receipt = store.get("receipts", result["receipt_digest"])
    assert receipt == {k: v for k, v in result.items() if k != "receipt_digest"}
    assert store.path("snapshots", key).read_bytes() == original_bytes
    assert store.pointer("last-reopened") is None


def test_given_unsupported_recipes_when_selected_then_plan_does_not_hide_them(desktop, capsys):
    result = invoke(desktop, capsys, "capture", "--window-id", "10", "--window-id", "0")
    value = Store(desktop.root).get("snapshots", result["snapshot_digest"])
    plan = restore.plan_restore(value, [], value["workspaces"])
    assert [
        (e["window_id"], e["recipe"]["kind"], e["target_workspace_idx"]) for e in plan["entries"]
    ] == [(0, "app", 1), (10, "unknown", 2)]
    assert plan["unknown_workspace_idx"] == 2
    assert plan["entries"][1]["recipe"]["reason"] == "no-recipe"
    assert [e["saved_workspace_idx"] for e in plan["entries"]] == [1, 2]
    for entry in plan["entries"]:
        with pytest.raises(ValueError, match="unsupported launch kind"):
            restore_host.admit(entry["recipe"])
    dry_run = invoke(desktop, capsys, "restore", result["snapshot_digest"])
    assert [(w["window_id"], w["kind"]) for w in dry_run["windows"]] == [
        (0, "app"),
        (10, "unknown"),
    ]
    assert dry_run["effects"] == []


def test_given_single_selection_when_dry_run_then_one_entry_and_saved_workspace(desktop, capsys):
    result = invoke(desktop, capsys, "capture", "--window-id", "30")
    selected = Store(desktop.root).get("snapshots", result["snapshot_digest"])
    assert not selected["windows"][0]["reopen"].get("extra")
    plan = restore.plan_restore(selected, [], selected["workspaces"])
    assert plan["workspace_names"] == {"1": "lab"}
    dry_run = invoke(desktop, capsys, "restore", result["snapshot_digest"])
    assert len(dry_run["windows"]) == 1
    entry = dry_run["windows"][0]
    assert (
        entry["window_id"],
        entry["saved_workspace_idx"],
        entry["target_workspace_idx"],
        entry["saved_workspace_name"],
        entry["column"],
    ) == (30, 4, 1, "lab", 2)
    assert "extra_of" not in entry
    assert dry_run["effects"] == []


def test_given_all_ids_explicit_when_capture_then_selection_still_has_provenance(desktop, capsys):
    full = invoke(desktop, capsys, "capture")
    selected = invoke(
        desktop, capsys, "capture", "--window-id", "10", "--window-id", "30", "--window-id", "0"
    )
    assert selected["capture_selection"] == {
        "kind": "window-ids",
        "window_ids": [0, 10, 30],
        "observed_window_count": 3,
    }
    store = Store(desktop.root)
    assert (
        store.get("snapshots", full["snapshot_digest"])["windows"]
        == store.get("snapshots", selected["snapshot_digest"])["windows"]
    )
    assert selected["snapshot_digest"] != full["snapshot_digest"]
