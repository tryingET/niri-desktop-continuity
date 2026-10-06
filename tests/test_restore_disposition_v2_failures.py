"""Staging, intervals and one-use refusal: no cleanup, repair, retry or post-publication veto."""

import os

import pytest
from test_restore_disposition_handwritten import handwritten as handwritten  # noqa: F401
from test_restore_disposition_v2 import approve, propose
from test_restore_disposition_v2 import unassociated as unassociated
from test_restore_disposition_v2_adversarial import replace

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_disposition_v2 as v2
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_reader as readers


@pytest.mark.parametrize("phase", ["stage", "used", "receipt", "rename", "directory"])
def test_partial_commit_is_fenced_and_never_repaired(unassociated, monkeypatch, phase):
    s = unassociated
    key = propose(s)
    approval = approve(s, key)
    final = s.directory / "00000005.json"
    create, durable, rename, sync = (
        s.store._create,
        history.durable_create,
        os.rename,
        history.sync_directory,
    )

    def fail_create(path, data):
        create(path, data)
        if path.parent.name == ("used" if phase == "used" else "receipts"):
            raise OSError("fabricated post-create failure")

    def fail_stage(path, record):
        durable(path, record)
        raise OSError("fabricated staged persistence interruption")

    def fail_rename(source, target):
        if str(target) == str(final):
            raise OSError("fabricated rename failure")
        rename(source, target)

    def fail_directory(path):
        if final.exists():
            raise OSError("fabricated visible-but-unestablished directory")
        sync(path)

    with monkeypatch.context() as patch:
        if phase in {"used", "receipt"}:
            patch.setattr(s.store, "_create", fail_create)
        elif phase == "stage":
            patch.setattr(history, "durable_create", fail_stage)
        elif phase == "rename":
            patch.setattr(os, "rename", fail_rename)
        else:
            patch.setattr(history, "sync_directory", fail_directory)
        with pytest.raises(OSError):
            d.apply(s.store, approval, observer=s.observe)
    used_before = tuple((s.store.root / "used").iterdir())
    if phase == "directory":
        assert final.exists()
        before = {p: p.read_bytes() for p in s.directory.iterdir()}
        result = d.apply(
            s.store, approval, observer=lambda: pytest.fail("historical accounting only")
        )
        assert result["historical"] and result["historical_completion"] == "unproved"
        assert {p: p.read_bytes() for p in before} == before
    else:
        assert not final.exists() and (s.directory / "00000005.pending").exists()
        with pytest.raises(ValueError):
            d.apply(s.store, approval, observer=lambda: pytest.fail("no incomplete retry"))
        with pytest.raises(ValueError):
            propose(s)  # A different approval may not bypass the staged attempt fence.
        with pytest.raises(ValueError):
            with operation_lock.operation_lock(s.identity):
                pytest.fail("partial stage cannot release a writer")
    assert tuple((s.store.root / "used").iterdir()) == used_before
    assert s.store.pointer("last-reopened") is None


@pytest.mark.parametrize("mode", ["inode", "whitespace", "parent"])
@pytest.mark.parametrize("stage", ["barrier", "publication"])
def test_first_observed_interval_pins_cannot_rebase(unassociated, monkeypatch, mode, stage):
    s = unassociated
    key = propose(s)
    approval = approve(s, key)
    path = s.store.path("plans", key)
    changed = []
    if stage == "barrier":
        original = readers.sync_artifact

        def sync(pin):
            original(pin)
            if pin["path"] == str(path) and not changed:
                changed.append(True)
                replace(path, mode)

        monkeypatch.setattr(readers, "sync_artifact", sync)
    else:
        original = os.rename

        def rename(source, destination):
            original(source, destination)
            if str(destination).endswith("00000005.json") and not changed:
                changed.append(True)
                replace(path, mode)

        monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(ValueError):
        d.apply(s.store, approval, observer=s.observe)
    assert changed
    if stage == "barrier":
        assert not list((s.store.root / "used").iterdir())
        assert len(list(s.directory.iterdir())) == 5
    else:
        assert (s.directory / "00000005.json").exists()


def test_expiry_after_staging_durability_is_a_preconsume_veto(unassociated, monkeypatch):
    s = unassociated
    key = propose(s)
    approval = approve(s, key)
    expires = s.store.get("plans", key)["expires"]
    original = history.durable_create

    def expire(path, record):
        original(path, record)
        monkeypatch.setattr(v2.model.time, "time", lambda: expires)

    monkeypatch.setattr(history, "durable_create", expire)
    with pytest.raises(ValueError, match="expired"):
        d.apply(s.store, approval, observer=s.observe)
    assert not list((s.store.root / "used").iterdir())
    assert (s.directory / "00000005.pending").exists()


@pytest.mark.parametrize("completed", [False, True])
def test_inspection_is_readonly_and_never_establishes_durability(
    unassociated, monkeypatch, completed
):
    from test_restore_disposition_v2_chain import finish

    s = unassociated
    if completed:
        finish(s)

    def forbidden(*_):
        pytest.fail("inspection cannot sync, observe, approve or consume")

    monkeypatch.setattr(os, "fsync", forbidden)
    monkeypatch.setattr(d.proof, "observe", forbidden)
    result = d.inspect(
        s.store,
        s.identity,
        s.attempt,
        s.interrupted,
        s.result,
        s.exit_file,
        family="exec-observed-unassociated",
    )
    assert result["admission"] == "not-granted" and result["approval"] == "not-granted"
    assert result["durability"] == "unestablished" and not result["fresh_native_verification"]
