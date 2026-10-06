"""Handwritten reserved-byte and irreversible-retirement oracles; fabricated files only."""

import os
from functools import partial
from pathlib import Path

import pytest
from test_restore_reader import private_file

from niri_desktop_continuity import restore_reader as module
from niri_desktop_continuity import restore_retained as retained
from niri_desktop_continuity.restore_reader import DependencyReader, Limits, ReaderStore
from niri_desktop_continuity.store import Store


class StopRead(BaseException):
    pass


def retired(reader, good):
    assert reader.closed and not reader.cache and not reader.parsed
    for call in (
        lambda: reader.raw(good),
        lambda: reader.evidence(good),
        reader.manifest,
        reader.barriers,
        lambda: reader.reserve(good),
        lambda: reader.reserve_pins([]),
        lambda: reader.reserve_commit([], history_count=0),
        lambda: reader.capacity(0, 0),
        lambda: reader.artifact(None, "receipts", "a" * 64),
        lambda: reader.get(None, "receipts", "a" * 64),
        lambda: ReaderStore(None, reader),
    ):
        with pytest.raises(ValueError, match="closed"):
            call()


@pytest.mark.parametrize("when", ["before-open", "after-open"])
def test_given_two_reserved_bytes_when_file_grows_then_no_unreserved_read(
    tmp_path, monkeypatch, when
):
    """Given a 2-byte reservation, when it grows at open, then reject without data IO."""
    good = private_file(tmp_path, "good", b"{}")
    pending = private_file(tmp_path, "pending", b"{}")
    reader = DependencyReader(limits=Limits(raw_bytes=4, file_bytes=2))
    reader.evidence(good)
    reader.reserve(pending)
    open_file = os.open
    calls = []

    def opening(path, flags, *args, **kwargs):
        target = Path(path).name == pending.name
        if target and when == "before-open":
            pending.write_bytes(b" " * 8192)
        fd = open_file(path, flags, *args, **kwargs)
        if target:
            calls.append(True)
            if when == "after-open":
                pending.write_bytes(b" " * 8192)
        return fd

    monkeypatch.setattr(os, "open", opening)
    monkeypatch.setattr(retained, "json_bytes", lambda *_: pytest.fail("drift reached decoder"))
    with pytest.raises(ValueError):
        reader.evidence(pending)
    assert calls == [True]
    assert reader.counters.validation_reserved_bytes == 4
    assert reader.counters.validation_bytes == 2  # Only the previously cached good file.
    retired(reader, good)


def test_exact_requested_and_returned_bytes_without_extra_probe(tmp_path, monkeypatch):
    path = private_file(tmp_path, data=b"{}")
    requested, returned = [], []
    read, fdopen = os.read, os.fdopen

    def bounded_read(fd, count):
        requested.append(count)
        block = read(fd, count)
        returned.append(len(block))
        return block

    class BufferedProbe:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, count):
            requested.append(count)
            data = self.stream.read(count)
            returned.append(len(data))
            return data

    monkeypatch.setattr(os, "read", bounded_read)
    monkeypatch.setattr(os, "fdopen", lambda *a, **k: BufferedProbe(fdopen(*a, **k)))
    reader = DependencyReader(limits=Limits(raw_bytes=2, file_bytes=2))
    assert reader.evidence(path)[0] == {}
    assert requested == returned == [2]


@pytest.mark.parametrize(
    "entry", ["batch", "barrier", "duplicate", "retained-conflict", "decode", "object"]
)
def test_every_rejected_entrypoint_irreversibly_retires(tmp_path, entry):
    good = private_file(tmp_path, "good", b"{}")
    pending = private_file(tmp_path, "pending", b"{")
    reader = DependencyReader()
    reader.evidence(good)
    if entry == "barrier":
        reader.reserve(pending)
        call = reader.barriers
    elif entry == "batch":
        call = partial(reader.reserve_pins, [{}])
    elif entry == "duplicate":
        call = partial(reader.reserve_commit, [(pending, b"a"), (pending, b"b")], history_count=0)
    elif entry == "retained-conflict":
        call = partial(reader.reserve_commit, [(good, b"wrong")], history_count=0)
    elif entry == "decode":
        call = partial(reader.evidence, pending)
    else:
        store = Store(tmp_path / "store")
        key = store.put("receipts", [])
        call = partial(ReaderStore(store, reader).get, "receipts", key)
    with pytest.raises((ValueError, KeyError)):
        call()
    retired(reader, good)


@pytest.mark.parametrize(
    "exception",
    [ValueError, KeyError, RuntimeError, KeyboardInterrupt, SystemExit, GeneratorExit, StopRead],
)
@pytest.mark.parametrize(
    "entry", ["reserve", "batch", "open", "decode", "prospective", "barrier", "view"]
)
def test_same_exception_instance_propagates_after_retirement(
    tmp_path, monkeypatch, exception, entry
):
    good = private_file(tmp_path, "good", b"{}")
    pending = private_file(tmp_path, "pending", b"{}")
    reader = DependencyReader()
    reader.evidence(good)
    fault = exception("fabricated interruption")

    def fail(*_, **__):
        raise fault

    def broken_iter():
        raise fault
        yield  # Generator protocol, not a callable failing before entry.

    if entry == "reserve":
        monkeypatch.setattr(module, "identity", fail)
        call = partial(reader.reserve, pending)
    elif entry == "batch":
        call = partial(reader.reserve_pins, broken_iter())
    elif entry == "open":
        monkeypatch.setattr(os, "open", fail)
        call = partial(reader.evidence, pending)
    elif entry == "decode":
        monkeypatch.setattr(retained, "json_bytes", fail)
        call = partial(reader.evidence, pending)
    elif entry == "prospective":
        call = partial(reader.reserve_commit, broken_iter(), history_count=0)
    elif entry == "barrier":
        monkeypatch.setattr(module, "sync_artifact", fail)
        call = reader.barriers
    else:
        store = Store(tmp_path / "store")
        view = ReaderStore(store, reader)
        monkeypatch.setattr(view, "path", fail)
        call = partial(view.get, "receipts", "a" * 64)
    with pytest.raises(exception) as caught:
        call()
    assert caught.value is fault
    retired(reader, good)
