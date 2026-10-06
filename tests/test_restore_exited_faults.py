"""V3 publication and first-observed evidence faults, not old-family proxy coverage."""

import json
from contextlib import contextmanager

import pytest
from test_restore_exited_contract import accounting as accounting  # noqa: F401
from test_restore_exited_history import legacy_ten as legacy_ten  # noqa: F401

from niri_desktop_continuity import operation_lock, restore_reader
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_disposition_v2_io as io
from niri_desktop_continuity import restore_exited as lifecycle
from niri_desktop_continuity import restore_history as history


@pytest.mark.parametrize(
    "boundary",
    [
        "stage-create",
        "stage-durable",
        "consume-before",
        "consume-after",
        "receipt",
        "barrier",
        "rename",
        "canonical-directory-sync",
    ],
)
def test_fault_never_repairs_or_bypasses_stage(accounting, monkeypatch, boundary):
    s = accounting
    initial = {p: p.read_bytes() for p in s.directory.iterdir()}
    canonical = s.directory / "00000010.json"
    pending = canonical.with_suffix(".pending")
    create, consume, put = history.durable_create, io.WriterView.consume, io.put
    sync, rename, barrier = (
        history.sync_directory,
        lifecycle.os.rename,
        restore_reader.sync_artifact,
    )

    def fail():
        raise OSError("fabricated durability failure")

    def create_fault(path, record):
        if boundary == "stage-create":
            fail()
        create(path, record)
        if boundary == "stage-durable":
            fail()

    def consume_fault(view, key, value):
        assert pending.exists() and not canonical.exists()
        if boundary == "consume-before":
            fail()
        consume(view, key, value)
        if boundary == "consume-after":
            fail()

    def put_fault(store, reader, kind, value):
        if boundary == "receipt" and kind == "receipts":
            fail()
        return put(store, reader, kind, value)

    def sync_fault(path):
        if boundary == "canonical-directory-sync" and canonical.exists():
            fail()
        return sync(path)

    def rename_fault(*args):
        if boundary == "rename":
            fail()
        return rename(*args)

    def barrier_fault(pin):
        if boundary == "barrier":
            fail()
        return barrier(pin)

    with monkeypatch.context() as patch:
        patch.setattr(history, "durable_create", create_fault)
        patch.setattr(io.WriterView, "consume", consume_fault)
        patch.setattr(io, "put", put_fault)
        patch.setattr(history, "sync_directory", sync_fault)
        patch.setattr(lifecycle.os, "rename", rename_fault)
        patch.setattr(restore_reader, "sync_artifact", barrier_fault)
        with pytest.raises(OSError, match="fabricated"):
            d.apply(s.store, s.approval)
    assert {p: p.read_bytes() for p in initial} == initial
    if boundary == "canonical-directory-sync":
        assert canonical.exists() and not pending.exists()
        # This new admission establishes durability NOW, not success of the failed invocation.
        assert d.apply(s.store, s.approval)["historical"] is True
    else:
        assert not canonical.exists()
        assert pending.exists() == (boundary != "stage-create")
        with pytest.raises(ValueError):
            with operation_lock.operation_lock(s.identity):
                pytest.fail("unfinished history cannot grant writer admission")
        if pending.exists():
            with pytest.raises(ValueError):
                d.apply(s.store, s.approval)


@pytest.mark.parametrize("kind", ["plans", "approvals"])
def test_route_first_raw_pin_survives_lock_transition(accounting, monkeypatch, kind):
    s = accounting
    lock = lifecycle.operation_lock
    key = s.plan if kind == "plans" else s.approval
    path = s.store.path(kind, key)

    @contextmanager
    def substitute(*args, **kwargs):
        path.write_bytes(path.read_bytes() + b" ")
        with lock(*args, **kwargs) as fd:
            yield fd

    monkeypatch.setattr(lifecycle, "operation_lock", substitute)
    with pytest.raises(ValueError):
        if kind == "plans":
            d.approve(
                s.store,
                s.plan,
                confirmation=s.plan,
                acceptance="operator-accepted-partial",
                attest_client_returned=True,
                platform_ack=s.proposed["platform_digest"],
            )
        else:
            d.apply(s.store, s.approval)
    assert not (s.directory / "00000010.pending").exists()


@pytest.mark.parametrize("name", ["cli", "compositor"])
def test_source_member_raw_change_blocks_historical_replay(accounting, name):
    s = accounting
    d.apply(s.store, s.approval)
    path = s.store.path("snapshots", s.source)
    value = json.loads(path.read_text())
    value["niri_version"][name] += "changed"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        d.apply(s.store, s.approval)


def test_visible_canonical_does_not_bypass_failed_admission_barrier(accounting, monkeypatch):
    s = accounting
    d.apply(s.store, s.approval)

    def failure(_):
        raise OSError("fabricated sync failure")

    monkeypatch.setattr("niri_desktop_continuity.store.sync_artifact", failure)
    with pytest.raises(ValueError, match="durability"):
        history.admit(s.identity)
