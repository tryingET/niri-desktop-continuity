"""Given/When/Then CLI contracts using fabricated state and no live desktop boundaries."""

from __future__ import annotations

import json
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest

from niri_desktop_continuity import cli, probe, reopen, restore
from niri_desktop_continuity.model import normalized_snapshot
from niri_desktop_continuity.store import Store

IDENTITY = {
    "boot_id": "fabricated-boot",
    "niri_socket": "/fabricated/compositor.sock",
    "socket_inode": 11,
    "socket_device": 22,
}


def snapshot(window_id):
    return normalized_snapshot(
        {
            "captured_at": "2025-01-01T00:00:00+00:00",
            "identity": dict(IDENTITY),
            "coherent": True,
            "outputs": [{"name": "FAKE-1", "logical": {}, "current_mode": 0}],
            "workspaces": [{"id": 1, "idx": 1, "output": "FAKE-1", "is_focused": True}],
            "windows": [
                {
                    "id": window_id,
                    "app_id": "fabricated-app",
                    "workspace_id": 1,
                    "layout": {"pos_in_scrolling_layout": [1, 1]},
                    "reopen": {"kind": "app", "argv": ["fabricated-app"], "cwd": None},
                }
            ],
        }
    )


def stored_bytes(store):
    """Compare only this test's private Store, including pointers and receipts."""
    return {p.relative_to(store.root): p.read_bytes() for p in store.root.rglob("*.json")}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    store = Store(tmp_path / "private")
    state = SimpleNamespace(store=store, calls=[], clock=0.0, ready_after=0.0)
    current = snapshot(900)
    state.identity = dict(IDENTITY)

    def forbidden(*args, **kwargs):
        pytest.fail("unexpected process, IPC, spawn, or layout effect")

    class Desktop:
        def ready(self):
            state.calls.append("ready")
            return state.clock >= state.ready_after

        def monotonic(self):
            return state.clock

        def sleep(self, seconds):
            state.clock += seconds

        spawn = staticmethod(forbidden)
        action = staticmethod(forbidden)
        windows = staticmethod(forbidden)
        workspaces = staticmethod(forbidden)

    def isolated_store(root):
        assert root == store.root  # Never permit implicit operator state.
        return store

    def identity():
        state.calls.append("identity")
        return dict(state.identity)

    def capture(**kwargs):
        state.calls.append("capture")
        return deepcopy(current)

    def lock(identity, *, effectful=True):
        assert effectful is False, "dry-run must request serialized read-only admission"
        state.calls.append("lock")
        return nullcontext()  # Never enter a real per-compositor lock directory.

    real_reopen = reopen.reopen

    def dry_restore(*args, **kwargs):
        state.calls.append("restore")
        assert kwargs["apply"] is False, "login skip must not reach the apply executor"
        # No real desktop entries or user routes.json: only this test's fabricated recipes.
        return real_reopen(*args, **kwargs, entries=[], users={})

    monkeypatch.setattr(cli, "Store", isolated_store)
    monkeypatch.setattr(cli, "capture", capture)
    monkeypatch.setattr(probe, "capture", capture)
    monkeypatch.setattr(probe, "compositor_identity", identity)
    monkeypatch.setattr(reopen.locks, "operation_lock", lock)
    monkeypatch.setattr(restore, "LiveDesktop", Desktop)
    monkeypatch.setattr(reopen, "reopen", dry_restore)
    monkeypatch.setattr(restore.subprocess, "run", forbidden)
    state.argv = ["--state-root", str(store.root), "restore"]
    return state


@pytest.mark.parametrize("explicit", [False, True], ids=["latest-pointer", "explicit-digest"])
def test_given_multiple_captures_when_restore_then_selected_snapshot_is_planned(
    sandbox, capsys, explicit
):
    # Given an older capture, a latest capture, and a stored but uncaptured distractor.
    store = sandbox.store
    older = store.save_snapshot(snapshot(1))
    latest = store.save_snapshot(snapshot(2))
    store.put("snapshots", snapshot(3))
    store.pointer("last-display-valid", older)
    store.pointer("last-reopened", older)
    # When the CLI requests the default snapshot or explicitly overrides it.
    assert cli.main(sandbox.argv + ([older] if explicit else [])) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    # Then the independent expected window/argv oracle proves actual dry-run planning.
    assert output.err == ""
    assert result["snapshot_digest"] == (older if explicit else latest)
    assert result["status"] == "dry-run" and result["apply"] is False
    assert [(w["window_id"], w["argv"]) for w in result["windows"]] == [
        (1 if explicit else 2, ["fabricated-app"])
    ]
    assert result["effects"] == [] and result["protected_window_ids"] == [900]
    assert store.get("receipts", result["receipt_digest"])["status"] == "dry-run"
    assert store.pointer("latest-observed") == latest
    assert store.pointer("last-reopened") == older


def test_given_latest_headless_in_current_instance_when_restore_then_fallback_is_reported_and_skipped(
    sandbox, capsys
):
    # Given a good older capture and a newer headless capture.
    store = sandbox.store
    good = store.save_snapshot(snapshot(1))
    headless = snapshot(2)
    headless["outputs"] = []
    latest = store.save_snapshot(headless)
    before = stored_bytes(store)
    # When default restoration is requested without effects.
    assert cli.main(sandbox.argv) == 0
    output = capsys.readouterr()
    # Selection is explicit in diagnostics, but current-instance fallback grants no effects.
    assert json.loads(output.out) == {
        "status": "same-compositor-instance",
        "snapshot_digest": good,
        "skipped": True,
    }
    assert json.loads(output.err) == {
        "source_pointer": "last-display-valid",
        "snapshot_digest": good,
        "fallback_reason": "latest-display-unavailable",
    }
    assert sandbox.calls == ["identity"]
    assert store.pointer("latest-observed") == latest
    assert store.pointer("last-display-valid") == good
    assert stored_bytes(store) == before


@pytest.mark.parametrize("bad_pointer", [False, True], ids=["absent", "malformed-json"])
def test_given_unusable_latest_pointer_when_login_then_no_restore(sandbox, capsys, bad_pointer):
    # Given either no capture or a corrupted pointer in this test's private Store.
    if bad_pointer:
        sandbox.store.save_snapshot(snapshot(1))
        (sandbox.store.root / "latest-observed.json").write_text("{")
    before = stored_bytes(sandbox.store)
    # When the login command is parsed, its apply boundary remains guarded.
    assert cli.main([*sandbox.argv, "--at-login", "--apply"]) == 2
    output = capsys.readouterr()
    # Then a structured error occurs before readiness, capture, locking, or restoration.
    assert output.out == "" and json.loads(output.err)["status"] == "error"
    if not bad_pointer:
        assert json.loads(output.err)["error"] == "no saved desktop to reopen"
    assert sandbox.calls == []
    assert stored_bytes(sandbox.store) == before


@pytest.mark.parametrize("ready_after", [0.0, 2.0], ids=["ready", "becomes-ready"])
@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply-guarded"])
def test_given_same_compositor_when_login_then_skip_without_restore_effects(
    sandbox, capsys, ready_after, apply
):
    # Given a saved desktop from this compositor and an independently older pointer.
    older = snapshot(1)
    older["identity"]["boot_id"] = "fabricated-previous-boot"
    sandbox.store.save_snapshot(older)
    latest = sandbox.store.save_snapshot(snapshot(2))
    sandbox.ready_after = ready_after
    before = stored_bytes(sandbox.store)
    # When login runs, even --apply must stop before the guarded executor.
    args = [*sandbox.argv, "--at-login", *(["--apply"] if apply else [])]
    assert cli.main(args) == 0
    output = capsys.readouterr()
    # Then no capture, lock, executor, receipt, pointer change, spawn, or layout action occurs.
    assert output.err == ""
    assert json.loads(output.out) == {
        "status": "same-compositor-instance",
        "snapshot_digest": latest,
        "skipped": True,
    }
    assert sandbox.calls == ["ready"] * (int(ready_after) + 1) + ["identity"]
    assert sandbox.clock == ready_after
    assert stored_bytes(sandbox.store) == before


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("boot_id", "fabricated-next-boot"),
        ("niri_socket", "/fabricated/other.sock"),
        ("socket_inode", 33),
        ("socket_device", 44),
    ],
)
def test_given_changed_compositor_when_login_then_dry_run_not_same_instance_skip(
    sandbox, capsys, field, replacement
):
    # Given one changed compositor identity component.
    latest = sandbox.store.save_snapshot(snapshot(1))
    sandbox.identity[field] = replacement
    # When login is requested WITHOUT --apply (the real effect executor remains forbidden).
    assert cli.main([*sandbox.argv, "--at-login"]) == 0
    output = capsys.readouterr()
    # Then the login guard dispatches to the real dry-run planner, not the skip branch.
    result = json.loads(output.out)
    assert output.err == ""
    assert result["status"] == "dry-run" and result["snapshot_digest"] == latest
    assert result["effects"] == []
    assert sandbox.calls == ["ready", "identity", "restore", "identity", "lock", "capture"]


def test_given_niri_never_ready_when_login_then_bounded_error_without_restore(sandbox, capsys):
    # Given a saved desktop but no readiness during the entire login budget.
    sandbox.store.save_snapshot(snapshot(1))
    sandbox.ready_after = float("inf")
    before = stored_bytes(sandbox.store)
    # When login waits on a fabricated clock, no real sleeping or IPC is performed.
    assert cli.main([*sandbox.argv, "--at-login", "--apply"]) == 2
    output = capsys.readouterr()
    # Then it stops at the 60-second budget with no restore effects or artifacts.
    assert output.out == ""
    assert json.loads(output.err) == {
        "status": "error",
        "error": "Niri did not become ready; nothing reopened",
    }
    assert sandbox.clock == 60.0 and sandbox.calls == ["ready"] * 61
    assert stored_bytes(sandbox.store) == before


def test_given_identity_probe_interrupted_when_login_then_no_restore(sandbox, monkeypatch, capsys):
    # Given readiness succeeds but the compositor identity cannot be read.
    sandbox.store.save_snapshot(snapshot(1))
    before = stored_bytes(sandbox.store)

    def interrupted():
        raise OSError("fabricated identity read interruption")

    monkeypatch.setattr(probe, "compositor_identity", interrupted)
    # When login encounters this interruption before its skip decision.
    assert cli.main([*sandbox.argv, "--at-login", "--apply"]) == 2
    output = capsys.readouterr()
    # Then it reports an error without entering restoration or modifying saved state.
    assert output.out == ""
    assert json.loads(output.err) == {
        "status": "error",
        "error": "fabricated identity read interruption",
    }
    assert sandbox.calls == ["ready"]
    assert stored_bytes(sandbox.store) == before
