"""Residual review regressions: diagnostic authority, CLI routing and immutable evidence."""

import json

import pytest
from test_recovery_orchestration import approve, command, execute, plan
from test_recovery_orchestration import fixture as fixture

from niri_desktop_continuity import cli, recovery_adapter, recovery_profile


def forbidden(*args, **kwargs):
    raise AssertionError("unexpected writable CLI Store or adapter invocation")


@pytest.mark.parametrize("drift", ["endpoint-comment", "endpoint-delete", "source-drift"])
def test_pin_drift_preserves_canonical_inspection_only(fixture, monkeypatch, drift):
    data = fixture(mode="die-after-intent")
    key = plan(data)
    approval = approve(data, key)
    execute(data, approval)
    phases = (data["root"] / "phases.jsonl").read_bytes()
    if drift == "endpoint-comment":
        endpoint = data["root"] / "endpoint.py"
        endpoint.write_text(endpoint.read_text() + "\n# drift\n")
    elif drift == "endpoint-delete":
        (data["root"] / "endpoint.py").unlink()
    else:
        source = data["root"] / "settings.json"
        source.write_text(source.read_text() + " ")
    monkeypatch.setattr(recovery_adapter.subprocess, "Popen", forbidden)
    inspected, status = command(data, "inspect", approval, "--kind", "reconstruction")
    assert status == 2 and inspected["status"] == "indeterminate"
    assert inspected["adapter"] is None and inspected["adapter_accounting"] == "unknown"
    assert inspected["plan_accounting"] == "valid"
    intent = inspected["interruption_evidence"][0]
    assert intent["intent"]["kind"] == "shutdown" and intent["intent"]["intent_ref"] == "1" * 64
    assert intent["outcome"] == "unresolved"
    assert inspected["retry_authorized"] is False
    assert inspected["event_scan"]["absence_is_no_effects_proof"] is False
    # Fixed safe identity is readable, but never sufficient for any invocation.
    assert recovery_profile.identify_profile() == data["profile"]
    with pytest.raises(ValueError):
        recovery_profile.load_profile()
    with pytest.raises(ValueError):
        approve(data, key)
    with pytest.raises(ValueError):
        execute(data, approval)
    assert (data["root"] / "phases.jsonl").read_bytes() == phases


@pytest.mark.parametrize("root_kind", ["canonical", "existing-separate", "absent-separate"])
def test_cli_inspection_never_creates_store_children(fixture, monkeypatch, root_kind):
    data = fixture(mode="die-after-intent")
    approval = approve(data, plan(data))
    execute(data, approval)
    canonical = data["root"] / "ledger"
    terminal = canonical / "recovery-terminal"
    marker = terminal / (approval + ".json")
    marker.unlink()
    terminal.rmdir()
    malformed = canonical / "recovery-prepared" / ("0" * 64 + ".json")
    malformed.write_text("{")
    malformed.chmod(0o600)
    separate = data["root"] / "state"
    # The CLI receipt directory has a final receipt; remove a different empty child.
    (separate / "recovery-ready").rmdir()
    selected = {
        "canonical": canonical,
        "existing-separate": separate,
        "absent-separate": data["root"] / "absent",
    }[root_kind]
    monkeypatch.setattr(cli, "Store", forbidden)
    value, status = cli.run(
        cli.parser().parse_args(
            [
                "--state-root",
                str(selected),
                "inspect",
                approval,
                "--kind",
                "reconstruction",
            ]
        )
    )
    assert status == 2 and value["canonical_scan"]["scan"] == "unknown"
    assert "recovery-terminal:missing-or-unreadable" in value["canonical_scan"]["issues"]
    assert {v["attempt_digest"]: v["accounting"] for v in value["canonical"]}[
        "0" * 64
    ] == "invalid-or-unreadable"
    assert value["interruption_evidence"][0]["intent"]["kind"] == "shutdown"
    assert not terminal.exists() and not marker.exists()
    assert malformed.read_text() == "{"
    assert not (separate / "recovery-ready").exists()
    assert not (data["root"] / "absent").exists()


@pytest.mark.parametrize(
    "damage", ["malformed", "permissions", "symlink", "pin-schema", "extra-root"]
)
def test_diagnostic_identity_never_falls_back_from_unsafe_anchor(fixture, monkeypatch, damage):
    data = fixture(mode="die-after-intent")
    approval = approve(data, plan(data))
    execute(data, approval)
    anchor = data["root"] / "profile.json"
    if damage == "malformed":
        anchor.write_text("{")
    elif damage == "permissions":
        anchor.chmod(0o644)
    elif damage == "symlink":
        copy = data["root"] / "profile-copy.json"
        anchor.rename(copy)
        anchor.symlink_to(copy)
    else:
        value = json.loads(anchor.read_text())
        if damage == "pin-schema":
            value["endpoint"]["sha256"] = "not-a-pin"
        else:
            value["fallback_ledger_root"] = str(data["root"] / "state")
        anchor.write_text(json.dumps(value))
    monkeypatch.setattr(cli, "Store", forbidden)
    monkeypatch.setattr(recovery_adapter.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError):
        cli.run(
            cli.parser().parse_args(
                [
                    "--state-root",
                    str(data["root"] / "ledger"),
                    "inspect",
                    approval,
                    "--kind",
                    "reconstruction",
                ]
            )
        )
