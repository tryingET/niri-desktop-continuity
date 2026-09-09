"""Actual scratch worker fault streams, not only plan-time malformed response tests."""

import json
import socket
import time

import pytest
from test_recovery_orchestration import approve, command, execute, plan
from test_recovery_orchestration import fixture as fixture

from niri_desktop_continuity import recovery_adapter
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.store import Store


@pytest.mark.parametrize(
    "mode,effects",
    [
        ("execute-wrong-request", []),
        ("execute-wrong-phase", []),
        ("execute-utf16", []),
        ("execute-duplicate-key", []),
        ("execute-nonfinite", []),
        ("execute-orphan-result", []),
        ("execute-out-of-order", []),
        ("execute-duplicate-intent", []),
        ("execute-pending-heartbeat", []),
        ("execute-correlated-pending-heartbeat", []),
        ("execute-dispatched-heartbeat", ["shutdown"]),
        ("execute-bad-result", ["shutdown"]),
        ("execute-duplicate-result", ["shutdown"]),
        ("execute-final-invalid", ["shutdown", "launch", "layout"]),
        ("execute-trailing", ["shutdown", "launch", "layout"]),
        ("execute-nonzero-final", ["shutdown", "launch", "layout"]),
        ("execute-over-frame", ["shutdown", "launch", "layout"]),
    ],
)
def test_execute_fault_stream_stops_and_retains_decision(fixture, mode, effects):
    data = fixture(mode=mode, missing=True)
    key = plan(data, "--omit-association", data["omission"])
    approval = approve(data, key, "--accept-omission", data["omission"])
    original = Store(data["root"] / "state").get("plans", key)["recovery"]
    report, status = execute(data, approval)
    assert status == 2 and report["status"] == "indeterminate"
    assert report["proof"] is None
    assert report["coverage"] == original["coverage"]
    assert report["accepted_omissions"] == original["omissions"]
    assert report["overall_native_coverage_complete"] is False
    assert report["process_memory"] == "unsupported"
    assert report["provider_usability"] == report["human_acceptance"] == "unverified"
    path = data["root"] / "effects.jsonl"
    actual = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    assert actual == effects  # handwritten physical-order oracle, no post-revocation effects
    assert "FABRICATED-SECRET" not in json.dumps(report)
    assert Ledger(data["profile"]).disposition()[0]["status"] == "indeterminate"
    if mode in {"execute-pending-heartbeat", "execute-dispatched-heartbeat"}:
        assert report["events"] == []
        intents = Ledger(data["profile"]).events(approval)
        assert len(intents) == 1 and intents[0]["outcome"] == "unresolved"
        assert intents[0]["intent"]["intent_ref"] == "1" * 64
    with pytest.raises(ValueError):
        execute(data, approval)
    if path.exists():
        assert [json.loads(line) for line in path.read_text().splitlines()] == effects
    if len(effects) < 3:
        assert (data["root"] / "cancelled").exists()
    verified, code = command(data, "verify", approval, "--kind", "reconstruction")
    assert code == 2 and verified["status"] == "indeterminate"


def test_execute_maximum_valid_final_frame(fixture):
    data = fixture(mode="execute-max-frame")
    approval = approve(data, plan(data))
    result, status = execute(data, approval)
    assert status == 0 and result["status"] == "verified"


def test_real_coordinator_socket_lease_revokes_stalled_worker(fixture):
    data = fixture(mode="execute-stall")
    approval = approve(data, plan(data))
    started = time.monotonic()
    report, status = execute(data, approval)
    assert time.monotonic() - started >= 5
    assert status == 2 and report["status"] == "indeterminate"
    assert (data["root"] / "worker-lease-expired").exists()
    assert (data["root"] / "cancelled").exists()
    assert not (data["root"] / "effects.jsonl").exists()


def test_worker_independently_expires_permit_without_parent_eof(fixture, monkeypatch):
    data = fixture(mode="execute-worker-lease")
    approval = approve(data, plan(data))
    pair = socket.socketpair

    class PatientPeer(socket.socket):
        def settimeout(self, seconds):
            super().settimeout(seconds * 2)

    def socketpair():
        parent, child = pair()
        return PatientPeer(fileno=parent.detach()), child

    # Test-only patient coordinator: wire lease stays five seconds. The actual worker
    # must cease effects before its peer's ten-second read timeout or EOF can revoke it.
    monkeypatch.setattr(recovery_adapter.socket, "socketpair", socketpair)
    started = time.monotonic()
    report, status = execute(data, approval)
    assert time.monotonic() - started >= 5
    assert status == 2 and report["status"] == "indeterminate"
    assert (data["root"] / "worker-lease-expired").exists()
    assert not (data["root"] / "effects.jsonl").exists()
    assert Ledger(data["profile"]).events(approval)[0]["outcome"] == "unresolved"
