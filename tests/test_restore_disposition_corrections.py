"""Review regressions: assertions describe authority, not a visible-file proxy for durability."""

import os
import time
from pathlib import Path

import pytest
from test_reopen import saved
from test_restore_disposition import approval, fenced, proposal
from test_restore_disposition import ready as ready  # noqa: F401
from test_restore_disposition import retained as retained  # noqa: F401
from test_restore_disposition_process import real_retained as real_retained  # noqa: F401
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity.restore_attempt import Attempt


@pytest.mark.parametrize("stage", ["approve", "apply"])
@pytest.mark.parametrize("change", ["focus", "cohort", "process", "surplus"])
def test_last_historical_read_drift_must_precede_authority(ready, monkeypatch, stage, change):
    s = ready
    plan = proposal(s)
    approved = approval(s, plan) if stage == "apply" else None
    original, calls, changed = d.historical_binding, [], []
    live = host.Process.live

    def binding(*args):
        original(*args)
        calls.append(True)
        if len(calls) == 2:
            changed.append(True)
            if change == "focus":
                s.desktop.focus = s.desktop.active[1] = 70
            elif change == "cohort":
                s.desktop.windows_by_id[70]["pid"] = 2000
            elif change == "surplus":
                s.desktop.add(9000)

    def process_live(self):
        if changed and change == "process":
            raise ValueError("fabricated ended process")
        live(self)

    monkeypatch.setattr(d, "historical_binding", binding)
    monkeypatch.setattr(host.Process, "live", process_live)
    with pytest.raises(ValueError):
        if stage == "approve":
            approval(s, plan)
        else:
            d.apply(s.store, approved, observer=s.observe)
    assert len(calls) == 2
    if stage == "approve":
        assert not list((s.store.root / "approvals").iterdir())
    assert not list((s.store.root / "used").iterdir())
    assert len(list(history.fence_path(s.identity).glob("*.json"))) == 9
    fenced(s)


@pytest.mark.parametrize("acceptor", ["lock", "original", "new", "disposition"])
@pytest.mark.parametrize("failed", ["directory", "file"])
def test_persistent_barrier_failure_never_admits_visible_disposition(
    ready, monkeypatch, acceptor, failed
):
    s = ready
    plan = proposal(s)
    approved = approval(s, plan)
    new_key = s.store.put("snapshots", saved([]))
    directory = history.fence_path(s.identity)
    canonical = directory / "00000009.json"
    fsync = os.fsync

    def broken(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if canonical.exists() and path == (directory if failed == "directory" else canonical):
            raise OSError("fabricated persistent durability failure")
        fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", broken)
        try:
            d.apply(s.store, approved, observer=s.observe)
        except (OSError, ValueError):
            pass
        assert canonical.exists()  # A visible valid record is deliberately NOT the verdict.
        with pytest.raises((ValueError, OSError)):
            if acceptor == "lock":
                with operation_lock.operation_lock(s.identity):
                    pass
            elif acceptor == "original":
                restore.restore(
                    s.store,
                    s.key,
                    s.desktop,
                    apply=True,
                    observe=lambda: pytest.fail("historical only"),
                )
            elif acceptor == "new":
                with Attempt(s.store, new_key, s.identity):
                    pass
            else:
                d.apply(s.store, approved, observer=lambda: pytest.fail("historical only"))
    before = {p: p.read_bytes() for p in directory.iterdir()}
    used = {p: p.read_bytes() for p in (s.store.root / "used").iterdir()}
    result = d.apply(s.store, approved, observer=lambda: pytest.fail("no new observation"))
    assert result["historical"] and result["effects"] == []
    assert {p: p.read_bytes() for p in directory.iterdir()} == before
    assert {p: p.read_bytes() for p in (s.store.root / "used").iterdir()} == used
    assert s.store.pointer("last-reopened") is None


def test_equal_store_artifact_retry_requires_file_and_directory_barriers(ready, monkeypatch):
    s = ready
    plan = proposal(s)
    monkeypatch.setattr(d.time, "time", lambda: s.store.get("plans", plan)["created"])
    fsync, failed, retry = os.fsync, [], []

    def fail_approval(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if path.parent == s.store.root / "approvals":
            failed.append(path)
            raise OSError("fabricated approval file fsync failure")
        fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail_approval)
        with pytest.raises(OSError):
            approval(s, plan)
    assert len(failed) == 1

    def trace(fd):
        retry.append(Path(os.readlink(f"/proc/self/fd/{fd}")))
        fsync(fd)

    monkeypatch.setattr(os, "fsync", trace)
    approved = approval(s, plan)
    assert s.store.path("approvals", approved) in retry
    assert s.store.root / "approvals" in retry


@pytest.mark.parametrize("stage", ["approve", "apply"])
@pytest.mark.parametrize("change", ["replace-directory", "process-chdir"])
def test_real_launched_cwd_must_remain_bound(real_retained, stage, change):
    s = real_retained
    plan = proposal(s)
    approved = approval(s, plan) if stage == "apply" else None
    if change == "replace-directory":
        s.cwd.rename(s.cwd.with_name("old-host-cwd"))
        s.cwd.mkdir(mode=0o700)
    else:
        s.child.stdin.write(b"d")
        s.child.stdin.flush()
        deadline = time.monotonic() + 3
        while os.readlink(f"/proc/{s.child.pid}/cwd") != "/" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert os.readlink(f"/proc/{s.child.pid}/cwd") == "/"
    with pytest.raises((ValueError, OSError)):
        if stage == "approve":
            approval(s, plan)
        else:
            d.apply(s.store, approved, observer=s.observe)
    assert not list((s.store.root / "used").iterdir())
    fenced(s)


@pytest.mark.parametrize("kind", ["plans", "approvals", "used", "receipts"])
def test_direct_get_dependencies_need_fresh_barriers_for_every_acceptance(ready, monkeypatch, kind):
    s = ready
    plan = proposal(s)
    approved = approval(s, plan)
    result = d.apply(s.store, approved, observer=s.observe)
    keys = {
        "plans": plan,
        "approvals": approved,
        "used": approved,
        "receipts": result["receipt_digest"],
    }
    path = s.store.path(kind, keys[kind])
    fsync = os.fsync

    def refuse(fd):
        if Path(os.readlink(f"/proc/self/fd/{fd}")) == path:
            raise OSError("fabricated dependency barrier failure")
        fsync(fd)

    monkeypatch.setattr(os, "fsync", refuse)
    fenced(s)
    with pytest.raises(ValueError):
        d.apply(s.store, approved, observer=lambda: pytest.fail("historical only"))


def test_pure_inspection_of_visible_canonical_never_claims_durability(ready, monkeypatch):
    s = ready
    plan = proposal(s)
    approved = approval(s, plan)
    rename = os.rename

    def lost(*args):
        rename(*args)
        raise OSError("fabricated interruption before canonical directory sync")

    with monkeypatch.context() as patch:
        patch.setattr(d.os, "rename", lost)
        with pytest.raises(OSError):
            d.apply(s.store, approved, observer=s.observe)
    monkeypatch.setattr(os, "fsync", lambda *_: pytest.fail("pure validation cannot fsync"))
    with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
        assert history.load(s.identity)[1] is None  # Structurally valid, NOT admission.
    result = d.inspect(s.store, s.identity, s.attempt, s.interrupted, s.result_path, s.exit_path)
    assert result["canonical"] == "validated" and result["durability"] == "unestablished"
    assert result["admission"] == "not-granted" and result["approval"] == "not-granted"


@pytest.mark.parametrize("change", ["focus", "cohort", "process", "expiry"])
def test_staged_persistence_drift_vetoes_before_canonical_publication(ready, monkeypatch, change):
    s = ready
    plan = proposal(s)
    approved = approval(s, plan)
    create, live, changed = history.durable_create, host.Process.live, []

    def stage(*args):
        create(*args)
        changed.append(True)
        if change == "focus":
            s.desktop.focus = s.desktop.active[1] = 70
        elif change == "cohort":
            s.desktop.windows_by_id[70]["pid"] = 2000
        elif change == "expiry":
            monkeypatch.setattr(d.time, "time", lambda: s.store.get("plans", plan)["expires"])

    def process_live(self):
        if changed and change == "process":
            raise ValueError("fabricated staged-persistence process exit")
        live(self)

    monkeypatch.setattr(history, "durable_create", stage)
    monkeypatch.setattr(host.Process, "live", process_live)
    with pytest.raises(ValueError):
        d.apply(s.store, approved, observer=s.observe)
    assert not (history.fence_path(s.identity) / "00000009.json").exists()
    assert s.store.path("used", approved).exists()
    fenced(s)


@pytest.mark.parametrize("stage", ["approve", "apply"])
def test_real_pidfd_exit_in_final_history_read_is_a_prepublication_veto(
    real_retained, monkeypatch, stage
):
    s = real_retained
    plan = proposal(s)
    approved = approval(s, plan) if stage == "apply" else None
    original, calls = d.historical_binding, []

    def binding(*args):
        original(*args)
        calls.append(True)
        if len(calls) == 2:
            s.child.stdin.close()
            assert s.child.wait(timeout=10) == 0

    monkeypatch.setattr(d, "historical_binding", binding)
    with pytest.raises(ValueError):
        if stage == "approve":
            approval(s, plan)
        else:
            d.apply(s.store, approved, observer=s.observe)
    assert not list((s.store.root / "used").iterdir())
    if stage == "approve":
        assert not list((s.store.root / "approvals").iterdir())
    fenced(s)


@pytest.mark.parametrize("damage", ["missing-consumption", "bad-receipt", "witness-inode"])
def test_recovery_validates_all_evidence_before_any_barrier_or_authority(
    ready, monkeypatch, damage
):
    s = ready
    plan = proposal(s)
    approved = approval(s, plan)
    rename = os.rename

    def lost(*args):
        rename(*args)
        raise OSError("fabricated loss before canonical directory sync")

    with monkeypatch.context() as patch:
        patch.setattr(os, "rename", lost)
        with pytest.raises(OSError):
            d.apply(s.store, approved, observer=s.observe)
    canonical = history.fence_path(s.identity) / "00000009.json"
    if damage == "missing-consumption":
        s.store.path("used", approved).unlink()
    elif damage == "bad-receipt":
        record = history.read(canonical)
        s.store.path("receipts", record["receipt"]).write_bytes(b"{")
    else:
        data = s.result_path.read_bytes()
        s.result_path.rename(s.result_path.with_suffix(".old"))
        s.result_path.write_bytes(data)
        s.result_path.chmod(0o600)
    with monkeypatch.context() as patch:
        patch.setattr(
            os,
            "fsync",
            lambda *_: pytest.fail("unvalidated evidence cannot be barriered into authority"),
        )
        with pytest.raises(ValueError):
            d.apply(s.store, approved, observer=lambda: pytest.fail("no native recovery"))
        with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
            with pytest.raises(ValueError):
                history.admit(s.identity)
    # Default lock creation durably establishes its own runtime directory edges before
    # admission; those unrelated setup barriers are not evidence acceptance.
    fenced(s)
    assert len(list(history.fence_path(s.identity).glob("*.json"))) == 10


def test_no_fresh_veto_after_canonical_publication(real_retained, monkeypatch):
    s = real_retained
    plan = proposal(s)
    approved = approval(s, plan)
    rename = os.rename
    canonical = history.fence_path(s.identity) / "00000009.json"

    def publish(*args):
        rename(*args)
        s.child.stdin.close()
        assert s.child.wait(timeout=10) == 0

    def observe():
        assert not canonical.exists(), "post-publication state cannot retroactively veto accounting"
        return s.observe()

    monkeypatch.setattr(d.os, "rename", publish)
    result = d.apply(s.store, approved, observer=observe)
    assert result["status"] == "operator-accepted-partial" and result["effects"] == []
    replay = d.apply(s.store, approved, observer=lambda: pytest.fail("no current proof upgrade"))
    assert replay["historical"]
