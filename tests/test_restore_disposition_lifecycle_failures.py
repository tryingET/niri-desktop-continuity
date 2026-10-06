"""Existing-v3 publication diagnostics: real private files, mocked precommit proof ONLY.

These are fault/replay tests, not positive native-proof or prospective completion evidence.
"""

import json

import pytest
from test_restore_exited_contract import accounting as accounting  # noqa: F401
from test_restore_exited_history import legacy_ten as legacy_ten  # noqa: F401

from niri_desktop_continuity import cli
from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_exited as lifecycle
from niri_desktop_continuity import restore_exited_proof as proof
from niri_desktop_continuity import restore_history as history


@pytest.mark.parametrize("schedule", ["before-rename", "returned-rename", "parent-sync"])
def test_given_exact_old_v3_when_publication_faults_then_truthful_phase_no_retry(
    accounting, monkeypatch, capsys, schedule
):
    s = accounting
    originals = {p: (p.read_bytes(), p.stat().st_ino) for p in s.directory.iterdir()}
    ending = s.directory / "00000010.json"
    staged = ending.with_suffix(".pending")
    events = []
    real_rename, real_sync = lifecycle.os.rename, history.sync_directory

    def rename(source, destination):
        events.append("rename-entered")
        if schedule == "before-rename":
            raise OSError("PRIVATE-SENTINEL-before-rename")
        real_rename(source, destination)
        events.append("rename-returned")
        if schedule == "returned-rename":
            raise OSError("PRIVATE-SENTINEL-ambiguous")

    def sync(path):
        if ending.exists():
            events.append("canonical-directory-sync")
            if schedule == "parent-sync":
                raise OSError("PRIVATE-SENTINEL-directory-sync")
        return real_sync(path)

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.os, "rename", rename)
        patch.setattr(history, "sync_directory", sync)
        status = cli.main(
            ["--state-root", str(s.store.root), "restore-disposition", "apply", s.approval]
        )
    out = capsys.readouterr()
    assert (
        events
        == {
            "before-rename": ["rename-entered"],
            "returned-rename": ["rename-entered", "rename-returned"],
            "parent-sync": ["rename-entered", "rename-returned", "canonical-directory-sync"],
        }[schedule]
    )  # Boundary reached before the diagnostic assertion (genuine RED).
    assert status == 2 and not out.out and "PRIVATE-SENTINEL" not in out.err
    assert {p: (p.read_bytes(), p.stat().st_ino) for p in originals} == originals
    assert ending.exists() == (schedule != "before-rename")
    assert staged.exists() == (schedule == "before-rename")
    diagnostic = json.loads(out.err)["diagnostic"]
    assert diagnostic == {
        "schema": "restore-accounting-failure.v1",
        "phase": "canonical-directory-sync" if schedule == "parent-sync" else "publish",
        "phase_state": "entered",
        "reason": "io-failed",
        "publication": "unknown",
        "cleanup_failure": False,
    }
    if ending.exists():

        def forbid(*args, **kwargs):
            pytest.fail("historical replay contacted native proof or publisher")

        with monkeypatch.context() as patch:
            patch.setattr(proof, "current", forbid)
            patch.setattr(lifecycle.os, "rename", forbid)
            assert (
                cli.main(
                    ["--state-root", str(s.store.root), "restore-disposition", "apply", s.approval]
                )
                == 2
            )
        replay = capsys.readouterr()
        assert not replay.err
        body = json.loads(replay.out)
        assert body["historical"] is True and body["effects"] == []
        assert body["fresh_native_verification"] is False
        assert body["durability"] == "established-now"
    else:
        with pytest.raises(ValueError):
            history.admit(s.identity)
        with pytest.raises(ValueError):
            disposition.apply(s.store, s.approval)


def test_given_existing_pending_when_new_families_selected_then_remain_fail_closed(
    accounting, monkeypatch, capsys
):
    s = accounting
    reached = []
    real_create = history.durable_create

    def stage_then_fail(path, record):
        real_create(path, record)
        reached.append("retained-pending-created")
        raise OSError("fabricated-pre-consumption")

    with monkeypatch.context() as patch:
        patch.setattr(history, "durable_create", stage_then_fail)
        with pytest.raises(OSError):
            disposition.apply(s.store, s.approval)
    assert reached == ["retained-pending-created"]
    pending = s.directory / "00000010.pending"
    original = pending.read_bytes(), pending.stat().st_ino
    assert not s.store.path("used", s.approval).exists()
    for family in (
        "failed-v3-accounting-preparation",
        "failed-v3-accounting-preparation-diagnostic-v1",
    ):
        try:
            status = cli.main(["restore-disposition", "inspect", s.attempt, "--family", family])
        except SystemExit as refused:
            status = refused.code
        assert status == 2
        result = capsys.readouterr()
        assert not result.out
        assert json.loads(result.err)["diagnostic"]["reason"] == "invalid-arguments"
    assert (pending.read_bytes(), pending.stat().st_ino) == original
    with pytest.raises(ValueError):
        history.admit(s.identity)
