"""Synthetic process/IPC workflows. All profile, compositor and lock boundaries are replaced."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_recovery_backend import provision

from niri_desktop_continuity import cli, operation_lock, recovery, recovery_profile
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.recovery_protocol import CONTRACT, coverage, decode, observation, proof
from niri_desktop_continuity.store import Store


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    def make(**kwargs):
        value = provision(tmp_path / "fake", **kwargs)
        root = value["root"]
        monkeypatch.setattr(operation_lock, "runtime_root", lambda: root / "runtime")
        monkeypatch.setattr(recovery_profile, "profile_path", lambda: root / "profile.json")
        monkeypatch.setattr(cli, "capture", lambda **_: deepcopy(value["snapshot"]))
        return value

    return make


def command(fixture, *args):
    return cli.run(cli.parser().parse_args(["--state-root", str(fixture["root"] / "state"), *args]))


def plan(fixture, *extra):
    return command(
        fixture,
        "plan",
        fixture["snapshot_digest"],
        "--intent",
        "reconstruct",
        "--adapter-config",
        str(fixture["root"] / "config.json"),
        *extra,
    )[0]["plan_digest"]


def approve(fixture, key, *extra):
    return command(fixture, "approve", key, "--confirm", key, "--accept-losses", CONTRACT, *extra)[
        0
    ]["approval_digest"]


def execute(fixture, key):
    return command(fixture, "reconstruct", key, "--apply", "--acknowledge-non-atomic-focus")


def test_full_workflow_and_no_replay(fixture):
    data = fixture()
    key = plan(data)
    preview, _ = command(data, "preview", key, "--kind", "plans")
    assert preview["runtime_effects"] == "none"
    approval = approve(data, key)
    assert approval == approve(data, key)
    assert not (data["root"] / "effects.jsonl").exists()
    result, status = execute(data, approval)
    assert status == 0 and result["status"] == "verified"
    assert result["overall_native_coverage_complete"] is True
    assert [
        json.loads(line) for line in (data["root"] / "effects.jsonl").read_text().splitlines()
    ] == ["shutdown", "launch", "layout"]
    verified, status = command(data, "verify", approval, "--kind", "reconstruction")
    assert status == 0 and verified["fresh_verification"] is True
    inspected, _ = command(data, "inspect", approval, "--kind", "reconstruction")
    assert inspected["fresh_native_verification"] is False
    assert inspected["status"] == "verified"
    with pytest.raises(ValueError):
        execute(data, approval)
    with pytest.raises(ValueError):
        approve(data, key)
    # A different CLI store with the exact plan and approval cannot reuse canonical authority.
    other = Store(data["root"] / "other")
    original = Store(data["root"] / "state")
    for kind, address in (
        ("snapshots", data["snapshot_digest"]),
        ("plans", key),
        ("approvals", approval),
    ):
        other.put(kind, original.get(kind, address))
    with pytest.raises(ValueError):
        recovery.execute(other, approval, cli.capture)


@pytest.mark.parametrize("mode", ["malformed", "oversized", "wrong-phase", "extra-field"])
def test_protocol_refusals_are_sanitized(fixture, mode, capsys):
    data = fixture(mode=mode)
    result = cli.main(
        [
            "--state-root",
            str(data["root"] / "state"),
            "plan",
            data["snapshot_digest"],
            "--intent",
            "reconstruct",
            "--adapter-config",
            str(data["root"] / "config.json"),
        ]
    )
    assert result == 2
    output = capsys.readouterr()
    assert "FABRICATED-SECRET" not in output.out + output.err
    assert not (data["root"] / "effects.jsonl").exists()


def test_noisy_diagnostics_are_discarded(fixture, capsys):
    plan(fixture(mode="noisy"))
    output = capsys.readouterr()
    assert "FABRICATED-SECRET" not in output.out + output.err


@pytest.mark.parametrize(
    "mode,expected", [("wrong-cwd", "partial"), ("die-after-intent", "indeterminate")]
)
def test_interrupted_history_never_upgrades(fixture, mode, expected):
    data = fixture(mode=mode)
    key = approve(data, plan(data))
    report, status = execute(data, key)
    assert status == 2 and report["status"] == expected
    report, status = command(data, "verify", key, "--kind", "reconstruction")
    assert status == 2 and report["status"] == "indeterminate"
    with pytest.raises(ValueError):
        execute(data, key)
    assert any(p.exists() for p in (data["root"] / "ledger/receipts").iterdir())


def test_omission_is_exact_separate_decision(fixture):
    data = fixture(missing=True)
    blocked = plan(data)
    with pytest.raises(ValueError):
        approve(data, blocked)
    key = plan(data, "--omit-association", data["omission"])
    with pytest.raises(ValueError):
        approve(data, key)
    with pytest.raises(ValueError):
        approve(data, key, "--accept-omission", "0" * 64)
    approval = approve(data, key, "--accept-omission", data["omission"])
    result, code = execute(data, approval)
    assert code == 0 and result["status"] == "verified-with-accepted-omissions"
    assert result["overall_native_coverage_complete"] is False
    assert result["coverage"] == {
        "owned_native_processes": 2,
        "associated_processes": 1,
        "omitted_associations": 1,
        "unique_saved_conversations": 1,
        "unresolved_associations": 1,
    }
    pin = result["accepted_omissions"][0]["pin"]
    assert (pin["boot_id"], pin["pid"], pin["start_ticks"], pin["exe_sha256"]) == (
        "fabricated",
        103,
        44,
        "b" * 64,
    )


def test_omission_never_waives_protection(fixture):
    data = fixture(missing=True, unsafe=True)
    key = plan(data, "--omit-association", data["omission"])
    with pytest.raises(ValueError):
        approve(data, key, "--accept-omission", data["omission"])


def test_legacy_incompleteness_blocks(fixture):
    data = fixture(mode="legacy-incomplete")
    with pytest.raises(ValueError):
        approve(data, plan(data))


@pytest.mark.parametrize("which", ["endpoint.py", "settings.json", "config.json", "profile.json"])
def test_pin_drift_before_invocation(fixture, which):
    data = fixture()
    path = data["root"] / which
    path.write_text(path.read_text() + " ")
    # Config/profile whitespace isn't a semantic pin change; make a conflicting schema instead.
    if which in {"config.json", "profile.json"}:
        value = json.loads(path.read_text())
        value["schema"] = "unsupported"
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        plan(data)
    assert not (data["root"] / "phases.jsonl").exists()


def test_phase_dispatch_rechecks_pins(fixture):
    data = fixture()
    key = plan(data)
    path = data["root"] / "endpoint.py"
    path.write_text(path.read_text() + "\n# drift\n")
    with pytest.raises(ValueError):
        approve(data, key)
    assert len((data["root"] / "phases.jsonl").read_text().splitlines()) == 1


def test_stale_and_expired_plans(fixture):
    data = fixture()
    key = plan(data)
    source = deepcopy(data["snapshot"])
    source["windows"][0]["is_focused"] = False
    store = Store(data["root"] / "state")
    with pytest.raises(ValueError):
        recovery.approve(
            store, key, lambda: source, confirmation=key, losses=CONTRACT, omissions=[]
        )
    value = store.get("plans", key)
    value["created_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
    value["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=100)).isoformat()
    expired = store.put("plans", value)
    with pytest.raises(ValueError):
        approve(data, expired)


@pytest.mark.parametrize("crash", ["before-consume", "before-ready"])
def test_incomplete_fence_blocks_cross_root(fixture, monkeypatch, crash):
    data = fixture()
    key = plan(data)
    approval = approve(data, key)
    ledger = Ledger(data["profile"])
    store = Store(data["root"] / "state")
    if crash == "before-consume":
        monkeypatch.setattr(store, "consume", lambda *a: (_ for _ in ()).throw(OSError()))
    else:
        original = ledger.store.recovery_marker

        def fail_ready(kind, *args):
            if kind == "recovery-ready":
                raise OSError()
            return original(kind, *args)

        monkeypatch.setattr(ledger.store, "recovery_marker", fail_ready)
    with pytest.raises(OSError):
        ledger.prepare(store, approval, key)
    assert Ledger(data["profile"]).disposition() == [
        {"attempt_digest": approval, "status": "indeterminate"}
    ]
    with pytest.raises(ValueError):
        Ledger(data["profile"]).available()
    with pytest.raises(ValueError):
        execute(data, approval)


def test_strict_counts_and_native_oracle(fixture):
    data = fixture()
    settings = json.loads((data["root"] / "settings.json").read_text())
    original = settings["proof"]
    for name in ("file", "cwd", "runtime", "bootstrap", "surface", "causal_window"):
        value = deepcopy(original)
        value["native"][0][name] = False
        assert proof(value, ["c" * 64]) is False
    for name in original["dimensions"]:
        value = deepcopy(original)
        value["dimensions"][name]["status"] = "unknown"
        assert proof(value, ["c" * 64]) is False
    for bad in (True, -1, 257, "1"):
        value = deepcopy(settings["observation"])
        value["legacy"]["unresolved"] = bad
        with pytest.raises(ValueError):
            observation(value, digest([]))
    with pytest.raises(ValueError):
        decode(b'{"x":1,"x":2}')
    value = deepcopy(settings["observation"])
    value["processes"][0]["session_ref"] = None
    for field in ("owned", "identity_proved", "protected_overlap"):
        altered = deepcopy(value)
        altered["processes"][0][field] = field == "protected_overlap"
        assert coverage(altered, [digest(altered["processes"][0]["pin"])])[2]


@pytest.mark.parametrize("cancel_at", ["intent", "result"])
def test_disconnect_ceases_new_effects_without_kill(fixture, monkeypatch, cancel_at):
    data = fixture()
    approval = approve(data, plan(data))
    original = Ledger.event

    def journal(self, attempt, kind, value):
        original(self, attempt, kind, value)
        if kind == cancel_at:
            raise KeyboardInterrupt

    monkeypatch.setattr(Ledger, "event", journal)
    with pytest.raises(KeyboardInterrupt):
        execute(data, approval)
    assert (data["root"] / "cancelled").exists()
    log = data["root"] / "effects.jsonl"
    assert (log.read_text().splitlines() if log.exists() else []) == (
        [] if cancel_at == "intent" else ['"shutdown"']
    )


def test_worker_retains_lock_after_coordinator_exit(fixture):
    data = fixture(mode="pause-after-effect")
    approval = approve(data, plan(data))
    root = data["root"]
    source = str(Path(__file__).resolve().parents[1] / "src")
    code = f"""
import sys, os, json, threading, time
sys.path.insert(0, {source!r})
from pathlib import Path
from niri_desktop_continuity import recovery, operation_lock, recovery_profile
from niri_desktop_continuity.store import Store
root = Path({str(root)!r})
operation_lock.runtime_root = lambda: root / "runtime"
recovery_profile.profile_path = lambda: root / "profile.json"
def disconnect():
    while not (root / "effect-waiting").exists(): time.sleep(0.01)
    os._exit(0)  # synthetic coordinator crash, no signals to any process
threading.Thread(target=disconnect, daemon=True).start()
recovery.execute(Store(root / "state"), {approval!r}, lambda: json.loads((root / "snapshot.json").read_text()))
"""
    parent = subprocess.Popen([sys.executable, "-I", "-c", code], cwd=root)
    try:
        assert parent.wait() == 0
        assert (root / "effect-waiting").exists()
        # Parent is gone; only the inherited worker FD maintains writer exclusion.
        with pytest.raises(ValueError):
            with operation_lock.operation_lock(data["snapshot"]["identity"]):
                pytest.fail("worker lost exclusion")
    finally:
        (root / "effect-release").touch()
    for _ in range(500):
        if (root / "cancelled").exists():
            break
        time.sleep(0.01)
    assert (root / "cancelled").exists()
    assert (root / "effects.jsonl").read_text().splitlines() == ['"shutdown"']
    assert Ledger(data["profile"]).disposition()[0]["status"] == "indeterminate"


def test_invalid_request_never_invokes_endpoint(fixture):
    data = fixture()
    for phase in ("invented", "observe", "admit", "verify", "inspect"):
        with pytest.raises(ValueError):
            Adapter(data["profile"]).call(phase, {})
    assert not (data["root"] / "phases.jsonl").exists()


def test_expiry_between_effects_stops_without_cleanup(fixture, monkeypatch):
    from niri_desktop_continuity import recovery_adapter

    data = fixture()
    approval = approve(data, plan(data))
    original = recovery_adapter.unexpired

    def expired_after_dispatch(deadline):
        if (data["root"] / "effects.jsonl").exists():
            raise ValueError("fabricated expiry")
        original(deadline)

    monkeypatch.setattr(recovery_adapter, "unexpired", expired_after_dispatch)
    result, status = execute(data, approval)
    assert status == 2 and result["status"] == "indeterminate"
    assert (data["root"] / "effects.jsonl").read_text().splitlines() == ['"shutdown"']
    inspected, _ = command(data, "inspect", approval, "--kind", "reconstruction")
    assert len(inspected["interruption_evidence"]) == 1


def test_drift_after_ready_is_fenced_without_invocation(fixture, monkeypatch):
    data = fixture()
    approval = approve(data, plan(data))
    original = Adapter.call

    def changed(adapter, phase, *args, **kwargs):
        if phase == "execute":
            path = data["root"] / "endpoint.py"
            path.write_text(path.read_text() + "\n# fabricated drift\n")
        return original(adapter, phase, *args, **kwargs)

    monkeypatch.setattr(Adapter, "call", changed)
    result, status = execute(data, approval)
    assert status == 2 and result["status"] == "indeterminate"
    assert Ledger(data["profile"]).disposition()[0]["status"] == "indeterminate"
    assert not (data["root"] / "effects.jsonl").exists()


def test_approval_requires_exact_confirmation_and_losses(fixture):
    data = fixture()
    key = plan(data)
    for confirm, losses in (("0" * 64, CONTRACT), (key, None)):
        with pytest.raises(ValueError):
            recovery.approve(
                Store(data["root"] / "state"),
                key,
                cli.capture,
                confirmation=confirm,
                losses=losses,
                omissions=[],
            )
    assert not list((data["root"] / "state/approvals").iterdir())


def test_interpreter_drift_is_not_executed(fixture, tmp_path):
    interpreter = tmp_path / "python"
    interpreter.write_bytes(Path(sys.executable).resolve().read_bytes())
    interpreter.chmod(0o700)
    data = fixture(interpreter=str(interpreter))
    interpreter.write_bytes(interpreter.read_bytes() + b"drift")
    with pytest.raises(ValueError):
        plan(data)
    assert not (data["root"] / "phases.jsonl").exists()


def test_indeterminate_inspection_retains_intent_ref(fixture):
    data = fixture(mode="die-after-intent")
    approval = approve(data, plan(data))
    execute(data, approval)
    inspected, status = command(data, "inspect", approval, "--kind", "reconstruction")
    assert status == 2 and inspected["status"] == "indeterminate"
    assert inspected["interruption_evidence"][0]["outcome"] == "unresolved"
    assert inspected["interruption_evidence"][0]["intent"]["intent_ref"] == "1" * 64
