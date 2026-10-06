"""Existing-binary routing, private witness projection and physically read-only inspection."""

import json
import os

import pytest
from test_restore_disposition import approval, proposal
from test_restore_disposition import ready as ready  # noqa: F401
from test_restore_disposition import retained as retained  # noqa: F401
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import cli, restore
from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_disposition_cli as routing
from niri_desktop_continuity import restore_disposition_evidence as evidence


def test_existing_cli_full_explicit_flow_and_original_replay_exit_two(ready, monkeypatch, capsys):
    s = ready
    monkeypatch.setenv("NIRI_SOCKET", "/fabricated/niri.sock")
    monkeypatch.setattr(routing, "compositor_identity", lambda: s.identity)
    monkeypatch.setattr(evidence, "observe", s.observe)
    root = ["--state-root", str(s.store.root)]
    selection = [
        s.attempt,
        "--interrupted-receipt",
        s.interrupted,
        "--client-result",
        str(s.result_path),
        "--client-exit",
        str(s.exit_path),
    ]

    def invoke(args, expected=0):
        assert cli.main(root + args) == expected
        output = capsys.readouterr()
        assert not output.err
        return json.loads(output.out)

    inspected = invoke(["restore-disposition", "inspect", *selection])
    assert inspected["approval"] == "not-granted"
    plan = invoke(["restore-disposition", "propose", *selection])["plan_digest"]
    approved = invoke(
        [
            "restore-disposition",
            "approve",
            plan,
            "--confirm",
            plan,
            "--accept",
            "operator-accepted-partial",
            "--attest-client-returned",
        ]
    )["approval_digest"]
    result = invoke(["restore-disposition", "apply", approved], expected=2)
    assert result["status"] == "operator-accepted-partial"
    replay = invoke(["restore-disposition", "apply", approved], expected=2)
    assert replay["historical"] and replay["effects"] == []
    monkeypatch.setattr(restore, "LiveDesktop", lambda: s.desktop)
    original = invoke(["restore", s.key, "--apply"], expected=2)
    assert original["status"] == "operator-accepted-partial"
    assert original["effects"] == [] and original["historical_effects"] == [
        ["move-column-to-index", "3"]
    ]


def test_inspection_does_not_write_create_or_fsync_anything(ready, monkeypatch):
    s = ready
    original_open = os.open

    def readonly(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", readonly)
    monkeypatch.setattr(os, "fsync", lambda *args: pytest.fail("inspection fsync mutation"))
    result = disposition.inspect(
        s.store, s.identity, s.attempt, s.interrupted, s.result_path, s.exit_path
    )
    assert result["approval"] == "not-granted"


def test_old_raw_diagnostic_payload_is_only_referenced_never_copied(ready):
    s = ready
    receipt = dict(s.receipt)
    receipt["final_observation"] = {
        "windows": [{"title": "FABRICATED-PRIVATE-TITLE"}],
        "environment": {"PRIVATE": "FABRICATED-PRIVATE-VALUE"},
    }
    s.interrupted = s.store.put("receipts", receipt)
    s.result_path.write_text(
        json.dumps({"snapshot_digest": s.key, "receipt_digest": s.interrupted, **receipt})
    )
    key = proposal(s)
    plan = s.store.get("plans", key)
    approved = approval(s, key)
    result = disposition.apply(s.store, approved, observer=s.observe)
    for value in (
        plan,
        result,
        s.store.get("approvals", approved),
        s.store.get("receipts", result["receipt_digest"]),
    ):
        text = json.dumps(value)
        assert "FABRICATED-PRIVATE-TITLE" not in text and "FABRICATED-PRIVATE-VALUE" not in text


@pytest.mark.parametrize("ttl", [0, 901, True, 1.5])
def test_ttl_bound(ready, ttl):
    s = ready
    with pytest.raises(ValueError):
        disposition.propose(
            s.store,
            s.identity,
            s.attempt,
            s.interrupted,
            s.result_path,
            s.exit_path,
            ttl=ttl,
            observer=s.observe,
        )


def test_cli_refusal_does_not_echo_private_original_error(ready, monkeypatch, capsys):
    s = ready
    monkeypatch.setenv("NIRI_SOCKET", "/fabricated/niri.sock")
    monkeypatch.setattr(routing, "compositor_identity", lambda: s.identity)
    s.result_path.write_text('{"private":"FABRICATED-PRIVATE-TITLE"}')
    assert (
        cli.main(
            [
                "--state-root",
                str(s.store.root),
                "restore-disposition",
                "inspect",
                s.attempt,
                "--interrupted-receipt",
                s.interrupted,
                "--client-result",
                str(s.result_path),
                "--client-exit",
                str(s.exit_path),
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert not output.out and "FABRICATED-PRIVATE-TITLE" not in output.err
