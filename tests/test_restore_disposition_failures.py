"""Crash, raw-byte and closed-history adversaries for accounting-only disposition."""

import json
import os
from copy import deepcopy

import pytest
from test_restore_disposition import approval, fenced, proposal
from test_restore_disposition import ready as ready  # noqa: F401
from test_restore_disposition import retained as retained  # noqa: F401
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_disposition as disposition
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.store import Store


def fault():
    raise OSError("fabricated persistence crash")


@pytest.mark.parametrize(
    "where",
    [
        "consume-before",
        "consume-after",
        "receipt-before",
        "receipt-after",
        "stage-before",
        "stage-after",
        "rename-before",
        "rename-after",
        "response-loss",
    ],
)
def test_accounting_crash_boundaries(ready, monkeypatch, where):
    s = ready
    key = proposal(s)
    approved = approval(s, key)
    consume, put, stage, rename = s.store.consume, s.store.put, history.durable_create, os.rename

    def consume_fault(*args):
        if where == "consume-before":
            fault()
        consume(*args)
        if where == "consume-after":
            fault()

    def put_fault(*args):
        if where == "receipt-before":
            fault()
        result = put(*args)
        if where == "receipt-after":
            fault()
        return result

    def stage_fault(*args):
        if where == "stage-before":
            fault()
        stage(*args)
        if where == "stage-after":
            fault()

    def rename_fault(*args):
        if where == "rename-before":
            fault()
        rename(*args)
        if where == "rename-after":
            fault()

    with monkeypatch.context() as patch:
        patch.setattr(s.store, "consume", consume_fault)
        patch.setattr(s.store, "put", put_fault)
        patch.setattr(history, "durable_create", stage_fault)
        patch.setattr(disposition.os, "rename", rename_fault)
        if where == "response-loss":
            disposition.apply(s.store, approved, observer=s.observe)
        else:
            with pytest.raises(OSError):
                disposition.apply(s.store, approved, observer=s.observe)
    if where in {"rename-after", "response-loss"}:
        replay = disposition.apply(
            s.store, approved, observer=lambda: pytest.fail("historical only")
        )
        assert replay["historical"] and replay["effects"] == []
        with operation_lock.operation_lock(s.identity):
            pass
    else:
        fenced(s)
        if where != "consume-before":
            with pytest.raises((ValueError, OSError)):
                disposition.apply(s.store, approved, observer=s.observe)
    assert {p: p.read_bytes() for p in s.original} == s.original
    assert s.store.pointer("last-reopened") is None


@pytest.mark.parametrize(
    "boundary",
    [
        "consume-file",
        "consume-dir",
        "receipt-file",
        "receipt-dir",
        "stage-file",
        "stage-dir",
        "publish-dir",
    ],
)
def test_accounting_barrier_failures_never_admit_until_successful_revalidation(
    ready, monkeypatch, boundary
):
    from pathlib import Path

    s = ready
    key = proposal(s)
    approved = approval(s, key)
    directory = history.fence_path(s.identity)
    canonical = directory / "00000009.json"
    old_receipts = set((s.store.root / "receipts").iterdir())
    fsync, failures = os.fsync, []

    def fail(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        matched = {
            "consume-file": path == s.store.path("used", approved),
            "consume-dir": path == s.store.root / "used",
            "receipt-file": path.parent == s.store.root / "receipts" and path not in old_receipts,
            "receipt-dir": path == s.store.root / "receipts",
            "stage-file": path == directory / "00000009.pending",
            "stage-dir": path == directory and not canonical.exists(),
            "publish-dir": path == directory and canonical.exists(),
        }[boundary]
        if matched:
            failures.append(path)
            fault()
        fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail)
        with pytest.raises((OSError, ValueError)):
            disposition.apply(s.store, approved, observer=s.observe)
        fenced(s)  # INCLUDING persistent final-directory failure with a visible canonical file.
    assert failures
    if boundary == "publish-dir":
        assert disposition.apply(
            s.store, approved, observer=lambda: pytest.fail("historical only")
        )["historical"]
    else:
        fenced(s)
    assert {p: p.read_bytes() for p in s.original} == s.original


@pytest.mark.parametrize("artifact", ["record", "snapshot", "prepared", "interrupted", "process"])
def test_semantically_identical_original_byte_drift_invalidates_approval(ready, artifact):
    s = ready
    key = proposal(s)
    approved = approval(s, key)
    records = [history.read(p) for p in s.original]
    path = {
        "record": next(iter(s.original)),
        "snapshot": s.store.path("snapshots", s.key),
        "prepared": s.store.path("receipts", records[0]["receipt"]),
        "interrupted": s.store.path("receipts", s.interrupted),
        "process": s.store.path("receipts", s.receipt["windows"][0]["process_receipt"]),
    }[artifact]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        disposition.apply(s.store, approved, observer=s.observe)
    fenced(s)


@pytest.mark.parametrize("replace_directory", [False, True])
def test_original_controller_witness_directory_is_independent_and_pinned(
    ready, tmp_path, replace_directory
):
    s = ready
    directory = tmp_path / "original-controller-witnesses"
    directory.mkdir(mode=0o700)
    s.result_path = s.result_path.rename(directory / s.result_path.name)
    s.exit_path = s.exit_path.rename(directory / s.exit_path.name)
    key = proposal(s)
    plan = s.store.get("plans", key)
    assert plan["origin"]["root"] == str(s.store.root)
    assert plan["witness"]["client_result"]["directory"] == {
        "device": directory.stat().st_dev,
        "inode": directory.stat().st_ino,
    }
    approved = approval(s, key)
    if replace_directory:
        displaced = directory.with_name("displaced-witnesses")
        directory.rename(displaced)
        directory.mkdir(mode=0o700)
        for path in (s.result_path, s.exit_path):
            (displaced / path.name).rename(path)  # Same file bytes/inodes, different parent inode.
        with pytest.raises(ValueError):
            disposition.apply(s.store, approved, observer=s.observe)
        fenced(s)
    else:
        assert (
            disposition.apply(s.store, approved, observer=s.observe)["status"] == disposition.ACCEPT
        )


def test_store_inode_replacement_and_other_root_never_bypass(ready, tmp_path):
    s = ready
    key = proposal(s)
    other = Store(tmp_path / "other")
    other.put("plans", s.store.get("plans", key))
    with pytest.raises(ValueError):
        disposition.approve(
            other,
            key,
            confirmation=key,
            acceptance=disposition.ACCEPT,
            attest_client_returned=True,
            observer=s.observe,
        )
    s.store.root.rename(s.store.root.with_name("displaced"))
    Store(s.store.root)
    with pytest.raises((ValueError, OSError)):
        proposal(s)
    fenced(s)


@pytest.mark.parametrize(
    "change",
    [
        "earlier-invalid",
        "other-pending",
        "old-v2",
        "unknown",
        "followup-observed",
        "terminal",
        "prediction",
        "extra-field",
    ],
)
def test_only_exact_reviewed_special_history_can_be_read_as_retained_data(ready, change):
    s = ready
    paths = list(s.original)
    records = [history.read(p) for p in paths]
    if change in {"followup-observed", "terminal"}:
        payload = {"intent": records[-1]["receipt"], "evidence": {}}
        if change == "terminal":
            payload = {"status": "operator-accepted-partial"}
        history.durable_create(
            history.fence_path(s.identity) / "00000009.json",
            {
                **records[-1],
                "seq": 9,
                "previous": digest(records[-1]),
                "type": "observed" if change == "followup-observed" else "terminal",
                "receipt": s.store.put("receipts", payload),
            },
        )
    else:
        index = 6 if change == "earlier-invalid" else 8
        payload = deepcopy(s.store.get("receipts", records[index]["receipt"]))
        if change == "earlier-invalid":
            payload["details"]["argv"] = ["set-column-width", "888.0"]
        elif change == "other-pending":
            payload["details"]["argv"] = ["move-column-to-index", "4.0"]
        elif change == "prediction":
            payload["details"]["expected"]["windows"][-1]["layout"]["tile_size"][0] += 1
        elif change == "extra-field":
            payload["details"]["invented"] = True
        elif change == "old-v2":
            records[index]["schema"] = "desktop-continuity.restore-history.v2"
        else:
            records[index]["type"] = "invented-terminal"
        records[index]["receipt"] = s.store.put("receipts", payload)
        for i in range(index, len(records)):
            records[i]["previous"] = digest(records[i - 1])
            paths[i].write_text(json.dumps(records[i]))
    with pytest.raises(ValueError):
        history.load(s.identity)
    fenced(s)


def test_canonical_disposition_does_not_accept_substituted_approval(ready):
    s = ready
    key = proposal(s)
    approved = approval(s, key)
    result = disposition.apply(s.store, approved, observer=s.observe)
    receipt = s.store.get("receipts", result["receipt_digest"])
    receipt["retry_authorized"] = True
    path = history.fence_path(s.identity) / "00000009.json"
    record = history.read(path)
    record["receipt"] = s.store.put("receipts", receipt)
    path.write_text(json.dumps(record))
    fenced(s)


def test_new_source_has_its_own_baseline_and_terminal_without_old_retry(ready):
    s = ready
    key = proposal(s)
    disposition.apply(s.store, approval(s, key), observer=s.observe)
    entry = s.entry(2, 1)
    entry["reopen"] = {"kind": "unknown", "argv": []}
    _, result = s.run([entry])
    assert result["status"] == "partial" and result["effects"] == []
    assert result["windows"][0]["status"] == "unsupported"
    with operation_lock.operation_lock(s.identity):
        pass
    replay = restore.restore(
        s.store,
        s.key,
        s.desktop,
        apply=True,
        observe=lambda: pytest.fail("old source must not observe or launch"),
    )
    assert replay["status"] == "operator-accepted-partial" and replay["effects"] == []
    assert s.store.pointer("last-reopened") is None


@pytest.mark.parametrize("stage", ["proposal", "approval"])
@pytest.mark.parametrize("boundary", [1, 2])
def test_plan_and_approval_fsync_failures_cannot_clear_history(ready, monkeypatch, stage, boundary):
    s = ready
    key = proposal(s) if stage == "approval" else None
    fsync, calls = os.fsync, []

    def fail(fd):
        calls.append(fd)
        if len(calls) == boundary:
            fault()
        fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail)
        with pytest.raises(OSError):
            if stage == "proposal":
                proposal(s)
            else:
                approval(s, key)
    assert len(calls) == boundary
    fenced(s)
    assert not list((s.store.root / "used").iterdir())


@pytest.mark.parametrize("stage", ["approval", "apply"])
def test_expiry_during_last_original_byte_revalidation_precedes_consumption(
    ready, monkeypatch, stage
):
    s = ready
    key = proposal(s)
    approved = approval(s, key) if stage == "apply" else None
    plan = s.store.get("plans", key)
    clock, calls = [plan["created"]], []
    original = disposition.historical_binding

    def slow(*args):
        original(*args)
        calls.append(True)
        if len(calls) == 2:
            clock[0] = plan["expires"]

    monkeypatch.setattr(disposition.time, "time", lambda: clock[0])
    monkeypatch.setattr(disposition, "historical_binding", slow)
    with pytest.raises(ValueError, match="expired"):
        if stage == "approval":
            approval(s, key)
        else:
            disposition.apply(s.store, approved, observer=s.observe)
    assert len(calls) == 2 and not list((s.store.root / "used").iterdir())
    fenced(s)


@pytest.mark.parametrize("kind", ["plans", "approvals", "used", "receipts", "canonical"])
def test_partial_write_is_never_a_canonical_disposition(ready, monkeypatch, kind):
    s = ready
    key = proposal(s) if kind != "plans" else None
    approved = approval(s, key) if kind not in {"plans", "approvals"} else None
    create = s.store._create

    def partial(path, content):
        if path.parent.name == kind:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content[:5])
            fault()
        return create(path, content)

    def canonical_partial(path, record):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(b'{"sch')
        fault()

    monkeypatch.setattr(s.store, "_create", partial)
    if kind == "canonical":
        monkeypatch.setattr(history, "durable_create", canonical_partial)
    with pytest.raises(OSError):
        if kind == "plans":
            proposal(s)
        elif kind == "approvals":
            approval(s, key)
        else:
            disposition.apply(s.store, approved, observer=s.observe)
    fenced(s)
    assert {p: p.read_bytes() for p in s.original} == s.original
