"""Unbuffered request/return oracle at the opened-FD boundary, never legacy raw IO."""

import errno
import os
from pathlib import Path

import pytest
from test_restore_reader import private_file
from test_restore_reader_corrections import StopRead, retired

from niri_desktop_continuity import restore_reader_io as bounded
from niri_desktop_continuity import restore_retained as retained
from niri_desktop_continuity.restore_reader import DependencyReader, Limits, ReaderStore


@pytest.mark.parametrize("data,requests", [(b"", []), (b"{}", [2]), (b'{"x":1}', [2, 2, 2, 1])])
def test_success_has_exact_total_request_and_return_without_probe(
    tmp_path, monkeypatch, data, requests
):
    path = private_file(tmp_path, data=data)
    monkeypatch.setattr(bounded, "CHUNK", 2)
    monkeypatch.setattr(retained, "raw", lambda *_: pytest.fail("legacy raw fallback"))
    monkeypatch.setattr(os, "fdopen", lambda *_: pytest.fail("buffered read-ahead"))
    asked, got = [], []
    read = os.read

    def observed(fd, amount):
        asked.append(amount)
        value = read(fd, amount)
        got.append(len(value))
        return value

    monkeypatch.setattr(os, "read", observed)
    reader = DependencyReader(limits=Limits(raw_bytes=len(data), file_bytes=len(data)))
    assert reader.raw(path)[0] == data
    assert asked == got == requests
    assert sum(asked) == reader.counters.validation_requested_bytes == len(data)
    assert sum(got) == reader.counters.validation_bytes == len(data)
    assert reader.counters.validation_read_calls == len(requests)


@pytest.mark.parametrize(
    "change", ["grow", "truncate", "replace", "rewrite", "parent", "unsafe", "hardlink"]
)
@pytest.mark.parametrize(
    "when", ["before-open", "after-open", "before-read", "after-read", "between-reads"]
)
def test_drift_never_decodes_and_total_io_is_within_reservation(
    tmp_path, monkeypatch, change, when
):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    good = private_file(directory, "good", b"{}")
    path = private_file(directory, "pending", b'{"x":1}')
    reader = DependencyReader(limits=Limits(raw_bytes=9))
    reader.evidence(good)
    reader.reserve(path)
    monkeypatch.setattr(bounded, "CHUNK", 2)
    original = path.read_bytes()
    changed = []
    opened, closed, requested, returned = [], [], [], []
    open_file, close_file, read_file, unchanged = os.open, os.close, os.read, bounded._unchanged

    def mutate():
        assert not changed
        changed.append(True)
        if change == "grow":
            path.write_bytes(b" " * 8192)
        elif change == "truncate":
            path.write_bytes(b"{")
        elif change == "replace":
            path.rename(path.with_suffix(".old"))
            private_file(directory, path.name, original)
        elif change == "rewrite":
            path.write_bytes(original.replace(b"1", b"2"))
        elif change == "unsafe":
            path.chmod(0o644)
        elif change == "hardlink":
            os.link(path, directory / "link")
        else:
            directory.rename(tmp_path / "old")
            directory.mkdir(mode=0o700)
            private_file(directory, path.name, original)

    def opening(name, flags, *args, **kwargs):
        target = Path(name).name == path.name
        if target and when == "before-open":
            mutate()
        fd = open_file(name, flags, *args, **kwargs)
        opened.append(fd)
        if target and when == "after-open":
            mutate()
        return fd

    def closing(fd):
        closed.append(fd)
        return close_file(fd)

    def reading(fd, amount):
        requested.append(amount)
        if when == "before-read" and not changed:
            mutate()
        data = read_file(fd, amount)
        returned.append(len(data))
        if when == "after-read" and not changed:
            mutate()
        return data

    def checked(*args):
        unchanged(*args)
        if when == "between-reads" and returned and not changed:
            mutate()

    monkeypatch.setattr(os, "open", opening)
    monkeypatch.setattr(os, "close", closing)
    monkeypatch.setattr(os, "read", reading)
    monkeypatch.setattr(bounded, "_unchanged", checked)
    monkeypatch.setattr(retained, "json_bytes", lambda *_: pytest.fail("drift reached decoder"))
    with pytest.raises((ValueError, OSError)):
        reader.evidence(path)
    assert changed == [True]
    assert requested == ([] if when in {"before-open", "after-open"} else [2])
    if requested:
        assert returned == [1 if change == "truncate" and when == "before-read" else 2]
    assert reader.counters.validation_requested_bytes == 2 + sum(requested)
    assert reader.counters.validation_bytes == 2 + sum(returned)
    assert sum(returned) <= sum(requested) <= len(original)
    assert sorted(opened) == sorted(closed)
    retired(reader, good)


@pytest.mark.parametrize("short", [0, 1])
def test_short_read_refuses_without_retry_or_probe(tmp_path, monkeypatch, short):
    path = private_file(tmp_path, data=b"{}")
    requested = []
    read = os.read

    def shorter(fd, count):
        requested.append(count)
        return read(fd, short)

    monkeypatch.setattr(os, "read", shorter)
    monkeypatch.setattr(retained, "json_bytes", lambda *_: pytest.fail("short read decoded"))
    reader = DependencyReader()
    with pytest.raises(ValueError, match="short"):
        reader.evidence(path)
    assert requested == [2]
    assert reader.counters.validation_requested_bytes == 2
    assert reader.counters.validation_bytes == short
    retired(reader, path)


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit, StopRead])
@pytest.mark.parametrize("site", ["read", "metadata", "close", "read-and-close"])
def test_io_interruption_closes_descriptors_and_preserves_first_exception(
    tmp_path, monkeypatch, exception, site
):
    good = private_file(tmp_path, "good", b"{}")
    path = private_file(tmp_path, "pending", b"{}")
    reader = DependencyReader()
    reader.evidence(good)
    first, cleanup = exception("first failure"), StopRead("cleanup failure")
    opened, closed = [], []
    open_file, close_file = os.open, os.close

    def opening(*args, **kwargs):
        fd = open_file(*args, **kwargs)
        opened.append(fd)
        return fd

    def closing(fd):
        closed.append(fd)
        close_file(fd)
        if site == "close":
            raise first
        if site == "read-and-close":
            raise cleanup

    def fail(*_):
        raise first

    monkeypatch.setattr(os, "open", opening)
    monkeypatch.setattr(os, "close", closing)
    if site in {"read", "read-and-close"}:
        monkeypatch.setattr(os, "read", fail)
    elif site == "metadata":
        monkeypatch.setattr(bounded, "_unchanged", fail)
    # Each of the two release callbacks may raise the same ACTUAL object. With no
    # body error the new preservation contract groups both failure occurrences.
    with pytest.raises(BaseExceptionGroup if site == "close" else exception) as caught:
        reader.evidence(path)
    if site == "close":
        assert caught.value.exceptions == (first, first)
    else:
        assert caught.value is first
    if site == "read-and-close":
        assert any("cleanup also failed" in note for note in first.__notes__)
    assert len(opened) == 2 and sorted(opened) == sorted(closed)
    for fd in opened:
        with pytest.raises(OSError) as error:
            os.fstat(fd)
        assert error.value.errno == errno.EBADF
    retired(reader, good)


@pytest.mark.parametrize("exception", [KeyError, KeyboardInterrupt, StopRead])
def test_store_binding_failure_retires_reader_with_same_exception(tmp_path, exception):
    good = private_file(tmp_path, "good", b"{}")
    reader = DependencyReader()
    reader.evidence(good)
    fault = exception("fabricated binding")

    class BrokenStore:
        @property
        def root(self):
            raise fault

    with pytest.raises(exception) as caught:
        ReaderStore(BrokenStore(), reader)
    assert caught.value is fault
    retired(reader, good)


def test_commit_check_does_not_hold_future_capacity_or_freeze_footprint(tmp_path):
    path = private_file(tmp_path, data=b"{}")
    reader = DependencyReader(limits=Limits(raw_bytes=2))
    future = tmp_path / "future"
    assert reader.reserve_commit([(future, b"{}")], history_count=0)["unique_bytes"] == 2
    assert not reader.reservations and not future.exists()
    # Later reads may change the footprint. Phase two MUST check the complete set LAST.
    reader.evidence(path)
    with pytest.raises(ValueError, match="budget"):
        reader.reserve_commit([(future, b"{}")], history_count=0)
    retired(reader, path)
