"""Offline selection contracts with handwritten expected recipes and private fabricated state."""

import json
from contextlib import nullcontext, redirect_stderr
from copy import deepcopy
from io import StringIO
from types import SimpleNamespace

import pytest

from niri_desktop_continuity import cli, probe, reopen, restore
from niri_desktop_continuity.model import normalized_snapshot
from niri_desktop_continuity.store import Store


def snapshot(window_id, *, boot="saved-boot", unavailable=False):
    return normalized_snapshot(
        {
            "identity": {"boot_id": boot, "socket_inode": 11, "socket_device": 22},
            "coherent": True,
            "outputs": [] if unavailable else [{"name": "FAKE", "logical": {}, "current_mode": 0}],
            "workspaces": [{"id": 1, "idx": 1, "output": "FAKE", "is_focused": True}],
            "windows": [
                {
                    "id": window_id,
                    "workspace_id": 1,
                    "layout": {"pos_in_scrolling_layout": [1, 1]},
                    "reopen": {"kind": "app", "argv": ["fabricated-app"], "cwd": None},
                }
            ],
        }
    )


def contents(store):
    return {p.relative_to(store.root): p.read_bytes() for p in store.root.rglob("*.json")}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    store = Store(tmp_path / "private")
    state = SimpleNamespace(store=store, calls=[], clock=0.0, ready_after=0.0)
    state.current = snapshot(900, boot="current-boot")

    def forbidden(*args, **kwargs):
        pytest.fail("unexpected real IPC, process, lock or layout effect")

    class Desktop:
        def ready(self):
            state.calls.append("ready")
            return state.clock >= state.ready_after

        def monotonic(self):
            return state.clock

        def sleep(self, seconds):
            state.clock += seconds

        spawn = action = windows = workspaces = staticmethod(forbidden)

    def identity():
        state.calls.append("identity")
        return dict(state.current["identity"])

    def capture(**kwargs):
        state.calls.append("capture")
        return deepcopy(state.current)

    def lock(identity, *, effectful=True):
        assert effectful is False
        state.calls.append("lock")
        return nullcontext()

    real_reopen = reopen.reopen

    def hermetic_reopen(*args, **kwargs):
        # No real desktop entries or user routes.json: only this test's fabricated recipes.
        return real_reopen(*args, **kwargs, entries=[], users={})

    monkeypatch.setattr(restore, "LiveDesktop", Desktop)
    monkeypatch.setattr(probe, "compositor_identity", identity)
    monkeypatch.setattr(probe, "capture", capture)
    monkeypatch.setattr(reopen.locks, "operation_lock", lock)
    monkeypatch.setattr(reopen, "reopen", hermetic_reopen)
    monkeypatch.setattr(restore.subprocess, "Popen", forbidden)
    return state


def invoke(state, *, login=False, explicit=None, apply=False):
    args = cli.parser().parse_args(
        ["restore", *([explicit] if explicit is not None else [])]
        + (["--at-login"] if login else [])
        + (["--apply"] if apply else [])
    )
    diagnostic = StringIO()
    try:
        with redirect_stderr(diagnostic):
            result = cli.run_restore(args, state.store)
    finally:
        lines = diagnostic.getvalue().splitlines()
        assert len(lines) <= 1, "selection emits at most one diagnostic"
        state.diagnostic = json.loads(lines[0]) if lines else None
        if state.diagnostic is not None:
            assert set(state.diagnostic) == {"source_pointer", "snapshot_digest", "fallback_reason"}
    assert "snapshot_selection" not in result[0]
    return result


@pytest.mark.parametrize("login", [False, True], ids=["manual", "login"])
def test_no_output_latest_selects_preserved_valid_desktop(sandbox, login):
    good = sandbox.store.save_snapshot(snapshot(1))
    latest = sandbox.store.save_snapshot(snapshot(2, unavailable=True))
    before = contents(sandbox.store)
    sandbox.ready_after = 2.0
    result, status = invoke(sandbox, login=login)
    assert status == 0 and result["status"] == "dry-run"
    assert result["snapshot_digest"] == good
    assert sandbox.diagnostic == {
        "source_pointer": "last-display-valid",
        "snapshot_digest": good,
        "fallback_reason": "latest-display-unavailable",
    }
    assert [(w["window_id"], w["argv"]) for w in result["windows"]] == [(1, ["fabricated-app"])]
    assert result["effects"] == [] and result["protected_window_ids"] == [900]
    assert sandbox.store.pointer("latest-observed") == latest
    assert sandbox.store.pointer("last-display-valid") == good
    assert all(contents(sandbox.store)[p] == data for p, data in before.items())
    if login:
        assert sandbox.calls[:4] == ["ready", "ready", "ready", "identity"]
    else:
        assert "ready" not in sandbox.calls


@pytest.mark.parametrize("login", [False, True])
def test_cli_emits_selection_without_changing_receipt_schema(sandbox, capsys, login):
    good = sandbox.store.save_snapshot(snapshot(1))
    sandbox.store.save_snapshot(snapshot(2, unavailable=True))
    argv = ["--state-root", str(sandbox.store.root), "restore"]
    assert cli.main(argv + (["--at-login"] if login else [])) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["snapshot_digest"] == good and "snapshot_selection" not in result
    assert len(output.err.splitlines()) == 1
    assert json.loads(output.err) == {
        "source_pointer": "last-display-valid",
        "snapshot_digest": good,
        "fallback_reason": "latest-display-unavailable",
    }
    receipt = sandbox.store.get("receipts", result["receipt_digest"])
    assert receipt == {k: v for k, v in result.items() if k != "receipt_digest"}
    assert receipt["effects"] == []


def test_cli_explicit_refusal_keeps_stdout_empty_and_errors_line_oriented(sandbox, capsys):
    key = sandbox.store.save_snapshot(snapshot(1, unavailable=True))
    assert cli.main(["--state-root", str(sandbox.store.root), "restore", key]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    lines = output.err.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "status": "error",
        "error": "saved snapshot is not display-valid; refusing to reopen from it",
    }


def test_cli_selection_failure_emits_no_provenance(sandbox, capsys):
    sandbox.store.save_snapshot(snapshot(1))
    (sandbox.store.root / "latest-observed.json").write_text("{")
    assert cli.main(["--state-root", str(sandbox.store.root), "restore"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and len(output.err.splitlines()) == 1
    assert set(json.loads(output.err)) == {"status", "error"}


@pytest.mark.parametrize("login", [False, True])
def test_ready_latest_preferred_even_with_corrupt_unused_fallback(sandbox, login):
    sandbox.store.save_snapshot(snapshot(1))
    latest = sandbox.store.save_snapshot(snapshot(2))
    (sandbox.store.root / "last-display-valid.json").write_text("{")
    result, status = invoke(sandbox, login=login)
    assert status == 0 and result["snapshot_digest"] == latest
    assert sandbox.diagnostic is None
    assert [w["window_id"] for w in result["windows"]] == [2]


@pytest.mark.parametrize("login", [False, True])
def test_explicit_unavailable_never_falls_back(sandbox, login):
    sandbox.store.save_snapshot(snapshot(1))
    invalid = sandbox.store.save_snapshot(snapshot(2, unavailable=True))
    before = contents(sandbox.store)
    with pytest.raises(ValueError, match="display-valid"):
        invoke(sandbox, login=login, explicit=invalid, apply=True)
    assert "capture" not in sandbox.calls and "lock" not in sandbox.calls
    assert contents(sandbox.store) == before


def test_explicit_valid_ignores_corrupt_pointers(sandbox):
    explicit = sandbox.store.put("snapshots", snapshot(1))
    (sandbox.store.root / "latest-observed.json").write_text("{")
    result, status = invoke(sandbox, explicit=explicit)
    assert status == 0 and result["snapshot_digest"] == explicit
    assert sandbox.diagnostic is None


@pytest.mark.parametrize("login", [False, True])
@pytest.mark.parametrize(
    "fault", ["json", "digest", "missing-artifact", "symlink", "private", "schema", "address"]
)
def test_latest_errors_do_not_select_good_fallback(sandbox, login, fault):
    sandbox.store.save_snapshot(snapshot(1))
    latest = sandbox.store.save_snapshot(snapshot(2, unavailable=True))
    pointer = sandbox.store.root / "latest-observed.json"
    artifact = sandbox.store.path("snapshots", latest)
    if fault == "json":
        pointer.write_text("{")
    elif fault == "digest":
        artifact.write_text("{}")
    elif fault == "missing-artifact":
        artifact.unlink()
    elif fault == "symlink":
        pointer.unlink()
        pointer.symlink_to("absent-fabricated-target")
    elif fault == "schema":
        invalid = snapshot(3, unavailable=True)
        invalid["schema"] = "unsupported"
        sandbox.store.pointer("latest-observed", sandbox.store.put("snapshots", invalid))
    elif fault == "address":
        pointer.write_text('{"snapshot_digest": "../not-an-address"}')
    else:
        pointer.chmod(0o644)
    before = contents(sandbox.store) if fault != "symlink" else None
    with pytest.raises((ValueError, OSError)):
        invoke(sandbox, login=login, apply=True)
    assert sandbox.calls == []
    if before is not None:
        assert contents(sandbox.store) == before


@pytest.mark.parametrize("login", [False, True])
@pytest.mark.parametrize(
    "fault", ["missing-pointer", "json", "missing-artifact", "digest", "unavailable", "schema"]
)
def test_invalid_fallback_refuses(sandbox, login, fault):
    good = sandbox.store.save_snapshot(snapshot(1))
    sandbox.store.save_snapshot(snapshot(2, unavailable=True))
    pointer = sandbox.store.root / "last-display-valid.json"
    if fault == "missing-pointer":
        pointer.unlink()
    elif fault == "json":
        pointer.write_text("{")
    elif fault == "missing-artifact":
        sandbox.store.path("snapshots", good).unlink()
    elif fault == "digest":
        sandbox.store.path("snapshots", good).write_text("{}")
    else:
        invalid = snapshot(3, unavailable=fault == "unavailable")
        if fault == "schema":
            invalid["schema"] = "unsupported"
        sandbox.store.pointer("last-display-valid", sandbox.store.put("snapshots", invalid))
    before = contents(sandbox.store)
    with pytest.raises((ValueError, OSError)):
        invoke(sandbox, login=login, apply=True)
    assert sandbox.calls == [] and contents(sandbox.store) == before


@pytest.mark.parametrize("login", [False, True])
def test_missing_latest_pointer_can_select_valid_fallback(sandbox, login):
    good = sandbox.store.save_snapshot(snapshot(1))
    (sandbox.store.root / "latest-observed.json").unlink()
    result, status = invoke(sandbox, login=login)
    assert status == 0 and result["snapshot_digest"] == good
    assert sandbox.diagnostic["fallback_reason"] == "latest-pointer-missing"
    assert not (sandbox.store.root / "latest-observed.json").exists()


@pytest.mark.parametrize("login", [False, True])
def test_no_pointers_refuses(sandbox, login):
    with pytest.raises(ValueError, match="no saved desktop"):
        invoke(sandbox, login=login, apply=True)
    assert sandbox.calls == []


@pytest.mark.parametrize("login", [False, True])
@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("same", ["latest", "fallback"])
def test_default_fallback_skips_current_instance(sandbox, login, apply, same):
    good = sandbox.store.save_snapshot(
        snapshot(1, boot="current-boot" if same == "fallback" else "saved-boot")
    )
    sandbox.store.save_snapshot(
        snapshot(2, boot="current-boot" if same == "latest" else "saved-boot", unavailable=True)
    )
    before = contents(sandbox.store)
    result, status = invoke(sandbox, login=login, apply=apply)
    assert status == 0 and result["status"] == "same-compositor-instance"
    assert result == {
        "status": "same-compositor-instance",
        "snapshot_digest": good,
        "skipped": True,
    }
    assert sandbox.diagnostic["source_pointer"] == "last-display-valid"
    assert "capture" not in sandbox.calls and "lock" not in sandbox.calls
    assert contents(sandbox.store) == before


@pytest.mark.parametrize("explicit", [False, True])
def test_login_valid_same_instance_still_skips(sandbox, explicit):
    key = sandbox.store.save_snapshot(snapshot(1, boot="current-boot"))
    before = contents(sandbox.store)
    result, status = invoke(sandbox, login=True, explicit=key if explicit else None, apply=True)
    assert status == 0 and result == {
        "status": "same-compositor-instance",
        "snapshot_digest": key,
        "skipped": True,
    }
    assert sandbox.calls == ["ready", "identity"]
    assert contents(sandbox.store) == before


def test_explicit_display_invalid_same_instance_login_preserves_skip(sandbox):
    key = sandbox.store.save_snapshot(snapshot(1, boot="current-boot", unavailable=True))
    before = contents(sandbox.store)
    result, status = invoke(sandbox, login=True, explicit=key, apply=True)
    assert status == 0 and result == {
        "status": "same-compositor-instance",
        "snapshot_digest": key,
        "skipped": True,
    }
    assert sandbox.diagnostic is None
    assert sandbox.calls == ["ready", "identity"] and contents(sandbox.store) == before


@pytest.mark.parametrize("reference", [999, True, 1.0, None, "1"])
def test_invalid_latest_workspace_reference_refuses_fallback(sandbox, reference):
    sandbox.store.save_snapshot(snapshot(1))
    invalid = snapshot(2, unavailable=True)
    invalid["windows"][0]["workspace_id"] = reference
    sandbox.store.save_snapshot(invalid)
    before = contents(sandbox.store)
    with pytest.raises(ValueError, match="workspace reference"):
        invoke(sandbox, apply=True)
    assert sandbox.calls == [] and contents(sandbox.store) == before


def test_active_display_with_missing_workspace_is_not_display_fallback(sandbox):
    sandbox.store.save_snapshot(snapshot(1))
    invalid = snapshot(2)
    invalid["windows"][0]["workspace_id"] = 999
    sandbox.store.save_snapshot(invalid)
    before = contents(sandbox.store)
    with pytest.raises(ValueError, match="workspace reference"):
        invoke(sandbox, apply=True)
    assert sandbox.calls == [] and contents(sandbox.store) == before


def test_incoherent_latest_is_not_display_fallback(sandbox):
    sandbox.store.save_snapshot(snapshot(1))
    incoherent = snapshot(2, unavailable=True)
    incoherent["coherent"] = False
    sandbox.store.save_snapshot(incoherent)
    with pytest.raises(ValueError, match="display-valid"):
        invoke(sandbox)
    assert sandbox.calls == []


@pytest.mark.parametrize("fault", ["missing", "corrupt", "address"])
def test_explicit_artifact_errors_never_fall_back(sandbox, fault):
    sandbox.store.save_snapshot(snapshot(1))
    key = sandbox.store.put("snapshots", snapshot(2))
    if fault == "missing":
        sandbox.store.path("snapshots", key).unlink()
    elif fault == "corrupt":
        sandbox.store.path("snapshots", key).write_text("{}")
    else:
        key = "../not-an-address"
    with pytest.raises((ValueError, OSError)):
        invoke(sandbox, explicit=key, apply=True)
    assert sandbox.calls == []


@pytest.mark.parametrize("explicit", [False, True])
def test_manual_valid_same_instance_is_not_newly_blocked(sandbox, explicit):
    key = sandbox.store.save_snapshot(snapshot(1, boot="current-boot"))
    result, status = invoke(sandbox, explicit=key if explicit else None)
    assert status == 0 and result["status"] == "dry-run"
    assert result["snapshot_digest"] == key and result["effects"] == []


def test_readiness_recomputed_not_cached_display_label(sandbox):
    good = sandbox.store.save_snapshot(snapshot(1))
    latest = snapshot(2, unavailable=True)
    latest["display"] = {"ready": True, "reasons": []}
    sandbox.store.save_snapshot(latest)
    result, status = invoke(sandbox)
    assert status == 0 and result["snapshot_digest"] == good


def test_login_fallback_readiness_timeout_preserved(sandbox):
    sandbox.store.save_snapshot(snapshot(1))
    sandbox.store.save_snapshot(snapshot(2, unavailable=True))
    sandbox.ready_after = float("inf")
    before = contents(sandbox.store)
    with pytest.raises(ValueError, match="Niri did not become ready"):
        invoke(sandbox, login=True, apply=True)
    assert sandbox.clock == 60.0 and sandbox.calls == ["ready"] * 61
    assert contents(sandbox.store) == before


@pytest.mark.parametrize("login", [False, True])
def test_fallback_identity_error_cannot_authorize_restore(sandbox, monkeypatch, login):
    sandbox.store.save_snapshot(snapshot(1))
    sandbox.store.save_snapshot(snapshot(2, unavailable=True))
    before = contents(sandbox.store)

    def interrupted():
        raise OSError("fabricated identity refusal")

    monkeypatch.setattr(probe, "compositor_identity", interrupted)
    with pytest.raises(OSError, match="identity refusal"):
        invoke(sandbox, login=login, apply=True)
    assert "capture" not in sandbox.calls and "lock" not in sandbox.calls
    assert contents(sandbox.store) == before


@pytest.mark.parametrize("login", [False, True])
def test_selected_fallback_still_meets_the_unresolved_attempt_fence(sandbox, monkeypatch, login):
    good = sandbox.store.save_snapshot(snapshot(1))
    sandbox.store.save_snapshot(snapshot(2, unavailable=True))
    before = contents(sandbox.store)

    def fenced(identity, *, effectful=True):
        # Effect admission (operation_lock -> require_clear) refuses an unresolved attempt.
        assert effectful is True
        sandbox.calls.append("fenced")
        raise ValueError("fabricated unresolved history refusal")

    monkeypatch.setattr(reopen.locks, "operation_lock", fenced)
    with pytest.raises(ValueError, match="unresolved history"):
        invoke(sandbox, login=login, apply=True)
    assert sandbox.diagnostic["snapshot_digest"] == good
    assert "fenced" in sandbox.calls and "capture" not in sandbox.calls
    assert contents(sandbox.store) == before
