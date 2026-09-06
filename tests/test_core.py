"""Admission/observation oracles. No test sends live compositor actions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from niri_desktop_continuity import cli, operation_lock, probe  # noqa: E402
from niri_desktop_continuity.approval import approve  # noqa: E402
from niri_desktop_continuity.model import (  # noqa: E402
    fingerprint,
    normalized_snapshot,
    readiness,
    verify,
)
from niri_desktop_continuity.planner import build_plan, layout_actions  # noqa: E402
from niri_desktop_continuity.reconcile import expected_after, reconcile  # noqa: E402
from niri_desktop_continuity.store import Store  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_runtime_lock(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)


def snapshot(count=3):
    return normalized_snapshot(
        {
            "identity": {
                "boot_id": "fixture",
                "niri_socket": "/fixture",
                "socket_inode": 1,
                "socket_device": 1,
            },
            "coherent": True,
            "outputs": [
                {"name": "DP-1", "logical": {"width": 1920, "height": 1200}, "current_mode": 0}
            ],
            "workspaces": [{"id": 1, "idx": 1, "output": "DP-1", "is_focused": True}],
            "windows": [
                {
                    "id": i,
                    "pid": 101,
                    "app_id": "com.mitchellh.ghostty",
                    "title": "same title",
                    "workspace_id": 1,
                    "is_floating": False,
                    "is_focused": i == 1,
                    "layout": {
                        "pos_in_scrolling_layout": [i, 1],
                        "tile_size": [800, 1084],
                        "window_size": [800, 1084],
                    },
                }
                for i in range(1, count + 1)
            ],
            "processes": [
                {
                    "pid": 101,
                    "ppid": 1,
                    "start_ticks": 42,
                    "exe": "/ghostty",
                    "exe_sha256": "f" * 64,
                    "exe_inode": 7,
                    "exe_device": 1,
                    "cgroup": "/ghostty.service",
                    "version": "1.4.0",
                }
            ],
            "process_inventory": [
                {"pid": 102, "ppid": 101, "start_ticks": 43, "cgroup": "/agent.scope"}
            ],
            "inventory_complete": True,
        }
    )


def desired_swap(source):
    target = deepcopy(source)
    target["windows"][0]["layout"]["pos_in_scrolling_layout"] = [2, 1]
    target["windows"][1]["layout"]["pos_in_scrolling_layout"] = [1, 1]
    return target


class FakeTransport:
    def __init__(self, state, *, failure=None):
        self.state = deepcopy(state)
        self.actions = []
        self.failure = failure

    def observe(self):
        return deepcopy(self.state)

    def apply(self, action):
        self.actions.append(action)
        if self.failure == "timeout":
            raise subprocess.TimeoutExpired("fixture", 1)
        if self.failure == "no-effect":
            return
        if action["kind"] == "focus-window":
            for window in self.state["windows"]:
                window["is_focused"] = window["id"] == action["window_id"]
        else:
            self.state = expected_after(self.state, action)


def admitted(tmp_path, source=None, target=None):
    store = Store(tmp_path / "private")
    source = source or snapshot()
    target = target or desired_swap(source)
    store.save_snapshot(source)
    plan = build_plan(source, intent="reconcile", desired=target)
    assert plan["admission"]["status"] == "awaiting-approval"
    key = store.put("plans", plan)
    approval = approve(store, key, source, confirmation=key)
    return store, source, target, key, approval


def test_33_windows_five_workspaces_two_missing():
    source = snapshot(33)
    source["workspaces"] = [
        {"id": i, "idx": i, "output": "DP-1", "is_focused": i == 1} for i in range(1, 6)
    ]
    for index, window in enumerate(source["windows"]):
        window["workspace_id"] = index % 5 + 1
        window["layout"]["pos_in_scrolling_layout"] = [index // 5 + 1, 1]
    actual = deepcopy(source)
    actual["windows"] = actual["windows"][:-2]
    report = verify(source, actual)
    assert report["matched_windows"] == 31
    assert report["status"] == "partial" and not report["layout_verified"]
    assert len(report["issues"]) == 2


def test_titles_not_identity_focus_separate_and_pid_reuse():
    source = snapshot()
    actual = deepcopy(source)
    actual["windows"][0]["title"] = "changed label"
    assert fingerprint(source) == fingerprint(actual)
    actual["windows"][0]["is_focused"] = False
    assert verify(source, actual)["layout_verified"]
    assert not verify(source, actual)["focus_verified"]
    actual["processes"][0]["start_ticks"] += 1
    assert not verify(source, actual)["layout_verified"]
    actual = deepcopy(source)
    actual["processes"][0]["exe_inode"] += 1
    assert fingerprint(source) != fingerprint(actual)


def test_headless_cannot_replace_good_pointers(tmp_path):
    store = Store(tmp_path / "private")
    good = snapshot()
    first = store.save_snapshot(good)
    store.save_verification(good, good)
    bad = deepcopy(good)
    bad["outputs"] = []
    latest = store.save_snapshot(bad)
    assert store.pointer("latest-observed") == latest
    assert store.pointer("last-display-valid") == first
    assert store.pointer("last-layout-verified") == first
    assert not readiness(bad)["ready"]
    assert verify(good, bad)["status"] == "waiting-for-output"
    assert not verify(bad, good)["layout_verified"]


def test_shared_process_scope_and_version_intersection():
    source = snapshot()
    plan = build_plan(source, intent="restart", window_ids=[1])
    assert plan["affected"]["window_ids"] == [1, 2, 3]
    assert plan["affected"]["pids"] == [101, 102]
    assert "shared-process-expands-beyond-selected-windows" in plan["admission"]["blockers"]
    plan = build_plan(source, intent="restart", pids=[101], version="1.3.1")
    assert plan["selection"]["pids"] == []
    assert "some-selected-pids-unmatched-or-filtered" in plan["admission"]["blockers"]
    assert "selector-matched-nothing" in plan["admission"]["blockers"]


@pytest.mark.parametrize("intent", ["inspect", "restart", "migrate"])
def test_never_approve_restart_or_inspection(tmp_path, intent):
    store = Store(tmp_path / "private")
    source = snapshot()
    store.save_snapshot(source)
    key = store.put("plans", build_plan(source, intent=intent))
    with pytest.raises(ValueError, match="restart is blocked"):
        approve(store, key, source, confirmation=key)


@pytest.mark.parametrize("position", [[0, 1], [True, 1], [1, 2], [9, 1], [1.5, 1]])
def test_bad_column_topology_blocked(position):
    source = snapshot()
    target = desired_swap(source)
    target["windows"][0]["layout"]["pos_in_scrolling_layout"] = position
    assert layout_actions(source, target)[1]


def test_unsupported_layout_shapes_and_missing_identity():
    source = snapshot()
    target = desired_swap(source)
    target["windows"][0]["workspace_id"] = 2
    assert "cross-workspace-placement-not-effect-modelled" in layout_actions(source, target)[1]
    target = desired_swap(source)
    target["windows"][0]["layout"]["tile_size"] = [600, 1084]
    assert "geometry-resize-not-admitted" in layout_actions(source, target)[1]
    source["processes"] = []
    target = desired_swap(source)
    assert "incomplete-executable-identity" in layout_actions(source, target)[1]


@pytest.mark.parametrize("change", ["focus", "pid", "output", "compositor"])
def test_stale_approval_no_effect(tmp_path, change):
    store, source, _, key, approval = admitted(tmp_path)
    current = deepcopy(source)
    if change == "focus":
        current["windows"][0]["is_focused"] = False
    elif change == "pid":
        current["processes"][0]["start_ticks"] += 1
    elif change == "output":
        current["outputs"] = []
    else:
        current["identity"]["socket_inode"] += 1
    with pytest.raises(ValueError):
        approve(store, key, current, confirmation=key)
    fake = FakeTransport(current)
    with pytest.raises(ValueError):
        reconcile(store, approval, fake)
    assert fake.actions == []


def test_confirmation_expiry_and_tampered_actions(tmp_path):
    store, source, _, key, approval = admitted(tmp_path)
    with pytest.raises(ValueError, match="confirmation"):
        approve(store, key, source, confirmation="yes")
    with pytest.raises(ValueError, match="expired"):
        reconcile(
            store,
            approval,
            FakeTransport(source),
            clock=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    plan = store.get("plans", key)
    plan["actions"] = [{"kind": "restart", "pid": 101}]
    tampered = store.put("plans", plan)
    with pytest.raises(ValueError, match="actions"):
        approve(store, tampered, source, confirmation=tampered)


def test_converges_verifies_and_noop_repeat_with_new_plan(tmp_path):
    store, source, target, _, approval = admitted(tmp_path)
    fake = FakeTransport(source)
    result = reconcile(store, approval, fake)
    assert result["layout_verified"] and result["original_focus_verified"]
    assert verify(target, fake.state)["layout_verified"]
    count = len(fake.actions)
    with pytest.raises((ValueError, FileExistsError)):
        reconcile(store, approval, fake)
    assert len(fake.actions) == count
    store.save_snapshot(fake.state)
    key = store.put("plans", build_plan(fake.state, intent="reconcile"))
    token = approve(store, key, fake.state, confirmation=key)
    assert reconcile(store, token, fake)["layout_verified"]
    assert len(fake.actions) == count


@pytest.mark.parametrize("failure", ["timeout", "no-effect"])
def test_ack_is_not_proof_and_failure_is_not_replayed(tmp_path, failure):
    store, source, _, key, approval = admitted(tmp_path)
    fake = FakeTransport(source, failure=failure)
    report = reconcile(store, approval, fake)
    assert not report["layout_verified"]
    assert report["status"] == "effect-indeterminate"
    assert len(fake.actions) == 1
    assert approve(store, key, source, confirmation=key) == approval
    with pytest.raises(FileExistsError):
        reconcile(store, approval, fake)
    assert len(fake.actions) == 1


def test_store_privacy_immutability_corruption_and_symlink(tmp_path):
    store = Store(tmp_path / "private")
    key = store.save_snapshot(snapshot())
    path = store.path("snapshots", key)
    assert path.stat().st_mode & 0o777 == 0o600
    assert store.root.stat().st_mode & 0o777 == 0o700
    assert store.put("snapshots", snapshot()) != key  # new captured_at, immutable distinct snapshot
    path.write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        store.get("snapshots", key)
    link = tmp_path / "link"
    link.symlink_to(store.root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        Store(link)
    path.unlink()
    path.symlink_to(link / "latest-observed.json")
    with pytest.raises(ValueError, match="private regular"):
        store.get("snapshots", key)
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="0700"):
        Store(public)


def test_store_oversize_refused_before_create(tmp_path):
    store = Store(tmp_path / "private")
    with pytest.raises(ValueError, match="16 MiB"):
        store.put("receipts", {"data": "a" * (16 * 1024 * 1024)})
    assert list((store.root / "receipts").iterdir()) == []


def test_cli_observation_failure_and_apply_optin(tmp_path, monkeypatch, capsys):
    def fail(**kwargs):
        raise subprocess.TimeoutExpired("niri", 10)

    monkeypatch.setattr(cli, "capture", fail)
    root = ["--state-root", str(tmp_path / "private")]
    assert cli.main([*root, "capture"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "error"
    assert cli.main([*root, "reconcile", "a" * 64]) == 2
    assert "requires --apply" in capsys.readouterr().err


def test_proc_stat_parser_handles_spaces_and_parentheses(monkeypatch):
    pid = os.getpid()
    value = probe.proc_stat(pid)
    assert value["pid"] == pid and value["start_ticks"] > 0


def test_probe_rechecks_layers_and_process_identity(monkeypatch):
    source = snapshot()
    monkeypatch.setattr(probe, "compositor_identity", lambda: source["identity"])
    monkeypatch.setattr(probe, "window_processes", lambda windows: (source["processes"], []))
    monkeypatch.setattr(probe, "process_inventory", lambda: ([], True))

    class ReadOnly:
        layer_reads = 0

        def query(self, command):
            if command == "outputs":
                return {"DP-1": source["outputs"][0]}
            if command == "version":
                return "fixture"
            if command == "layers":
                self.layer_reads += 1
                return [{"namespace": str(self.layer_reads)}]
            return source[command]

    actual = probe.capture(transport=ReadOnly())
    assert not actual["coherent"] and not readiness(actual)["ready"]
    assert actual["privacy"]["titles_included"] is False


def test_operator_change_after_focus_stops_before_move(tmp_path):
    store, source, _, _, approval = admitted(tmp_path)

    class Drift(FakeTransport):
        def apply(self, action):
            super().apply(action)
            self.state["windows"][2]["pid"] = 999

    fake = Drift(source)
    report = reconcile(store, approval, fake)
    assert report["status"] == "effect-indeterminate"
    assert len(fake.actions) == 1 and fake.actions[0]["kind"] == "focus-window"


def test_effect_intent_is_durable_before_dispatch(tmp_path):
    store, source, _, _, approval = admitted(tmp_path)

    class CheckIntent(FakeTransport):
        def apply(self, action):
            records = [
                store.get("receipts", p.stem) for p in (store.root / "receipts").glob("*.json")
            ]
            assert any(
                r.get("action") == action and r.get("status") == "effect-indeterminate"
                for r in records
            )
            super().apply(action)

    assert reconcile(store, approval, CheckIntent(source))["layout_verified"]


def test_budget_refusal_no_effect_or_consumption(tmp_path):
    store, source, _, _, approval = admitted(tmp_path)
    fake = FakeTransport(source)
    with pytest.raises(ValueError, match="budget"):
        reconcile(store, approval, fake, budget=1)
    assert not store.path("used", approval).exists()
    assert fake.actions == []


def test_live_transport_exact_allowlist_without_running_niri(monkeypatch):
    from niri_desktop_continuity.reconcile import LiveTransport

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kwargs: calls.append(argv))
    transport = LiveTransport()
    transport.apply({"kind": "focus-window", "window_id": 42})
    transport.apply({"kind": "place-column", "column_index": 2})
    assert calls == [
        ["niri", "msg", "action", "focus-window", "--id", "42"],
        ["niri", "msg", "action", "move-column-to-index", "2"],
    ]
    with pytest.raises(ValueError):
        transport.apply({"kind": "restart", "pid": 101})
    assert len(calls) == 2


def test_writer_lock_spans_distinct_store_roots_and_releases(tmp_path):
    store, source, _, _, token = admitted(tmp_path / "first")
    other, _, _, _, second_token = admitted(tmp_path / "second", source=source)
    fake = FakeTransport(source)
    with operation_lock.operation_lock(source["identity"]):
        with pytest.raises(ValueError, match="another continuity writer"):
            reconcile(other, second_token, fake)
    assert fake.actions == [] and not other.path("used", second_token).exists()
    assert reconcile(store, token, fake)["layout_verified"]
    with pytest.raises(ValueError, match="stale plan"):
        reconcile(other, second_token, fake)


def test_focus_only_transition_invalidates_capture(monkeypatch):
    source = snapshot()
    monkeypatch.setattr(probe, "compositor_identity", lambda: source["identity"])
    monkeypatch.setattr(probe, "window_processes", lambda windows: (source["processes"], []))
    monkeypatch.setattr(probe, "process_inventory", lambda: ([], True))

    class FocusChange:
        calls = 0

        def query(self, command):
            if command == "windows":
                self.calls += 1
                windows = deepcopy(source["windows"])
                if self.calls > 1:
                    windows[0]["is_focused"] = False
                    windows[1]["is_focused"] = True
                return windows
            if command == "outputs":
                return {"DP-1": source["outputs"][0]}
            if command == "version":
                return "fixture"
            return source[command]

    assert not probe.capture(transport=FocusChange())["coherent"]


def test_hand_written_reorder_oracle(tmp_path):
    store, source, _, _, token = admitted(tmp_path)

    class Independent(FakeTransport):
        def apply(self, action):
            self.actions.append(action)
            if action["kind"] == "focus-window":
                for window in self.state["windows"]:
                    window["is_focused"] = window["id"] == action["window_id"]
                return
            assert action == {"kind": "place-column", "window_id": 2, "column_index": 1}
            # Independent expected Niri order, not the implementation's expected_after helper.
            self.state["windows"][0]["layout"]["pos_in_scrolling_layout"] = [2, 1]
            self.state["windows"][1]["layout"]["pos_in_scrolling_layout"] = [1, 1]
            self.state["windows"][2]["layout"]["pos_in_scrolling_layout"] = [3, 1]

    fake = Independent(source)
    assert reconcile(store, token, fake)["layout_verified"]
    assert [a["kind"] for a in fake.actions] == ["focus-window", "place-column", "focus-window"]


def test_expiry_after_first_effect_prevents_next_action(tmp_path, monkeypatch):
    import importlib

    engine = importlib.import_module("niri_desktop_continuity.reconcile")
    store, source, _, key, token = admitted(tmp_path)
    instant = [datetime.now(timezone.utc)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant[0]

    class Expiring(FakeTransport):
        def apply(self, action):
            super().apply(action)
            instant[0] = datetime.fromisoformat(store.get("plans", key)["expires_at"]) + timedelta(
                seconds=1
            )

    monkeypatch.setattr(engine, "datetime", Clock)
    fake = Expiring(source)
    report = reconcile(store, token, fake)
    assert report["status"] == "effect-indeterminate" and len(fake.actions) == 1
    assert "expired" in report["error"]


def test_final_focus_ack_without_effect_is_failure(tmp_path):
    store, source, _, _, token = admitted(tmp_path)

    class NoFinalFocus(FakeTransport):
        def apply(self, action):
            if len(self.actions) == 2 and action["kind"] == "focus-window":
                self.actions.append(action)
            else:
                super().apply(action)

    report = reconcile(store, token, NoFinalFocus(source))
    assert not report["layout_verified"] and report["status"] == "effect-indeterminate"
