"""Actual writer/read/fsync syscall boundaries on test-owned v3 artifacts."""

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from test_restore_exited_contract import accounting as accounting  # noqa: F401
from test_restore_exited_history import legacy_ten as legacy_ten  # noqa: F401

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_disposition as d


@pytest.mark.parametrize("kind", ["stage", "used", "receipt"])
@pytest.mark.parametrize(
    "boundary", ["open", "write", "partial-write", "flush", "file-fsync", "directory-fsync", "read"]
)
def test_every_new_artifact_io_boundary_remains_fenced(accounting, monkeypatch, kind, boundary):
    s = accounting
    before = {p: p.read_bytes() for p in s.directory.iterdir()}
    originals = set((s.store.root / "receipts").iterdir())
    pending = s.directory / "00000010.pending"
    canonical = pending.with_suffix(".json")
    used = s.store.path("used", s.approval)
    real_open, real_fdopen, real_fsync, real_read = os.open, os.fdopen, os.fsync, os.read
    created, fired = [], []

    def classify(path):
        path = Path(path)
        if path == pending:
            return "stage"
        if path == used:
            return "used"
        if path.parent == s.store.root / "receipts" and path not in originals:
            return "receipt"
        return None

    def fail():
        fired.append(True)
        raise OSError("fabricated exact IO boundary")

    def opened(path, flags, *a, **kw):
        target = (
            classify(path) if isinstance(path, (str, Path)) and Path(path).is_absolute() else None
        )
        if target == kind:
            if flags & os.O_CREAT:
                if boundary == "open":
                    fail()
                created.append(Path(path))
        return real_open(path, flags, *a, **kw)

    def read(fd, size):
        if boundary == "read" and created and classify(os.readlink(f"/proc/self/fd/{fd}")) == kind:
            fail()
        return real_read(fd, size)

    @contextmanager
    def fdopen(fd, *a, **kw):
        target = classify(os.readlink(f"/proc/self/fd/{fd}"))
        with real_fdopen(fd, *a, **kw) as stream:
            if target != kind or "w" not in (a[0] if a else kw.get("mode", "r")):
                yield stream
                return

            class Stream:
                def write(self, data):
                    if boundary == "partial-write":
                        stream.write(data[:3])
                        stream.flush()
                        fail()
                    if boundary == "write":
                        fail()
                    return stream.write(data)

                def flush(self):
                    if boundary == "flush":
                        fail()
                    return stream.flush()

                def fileno(self):
                    return stream.fileno()

            yield Stream()

    def fsync(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if boundary == "file-fsync" and classify(path) == kind:
            fail()
        if boundary == "directory-fsync" and created and path == created[0].parent:
            fail()
        return real_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", opened)
        patch.setattr(os, "fdopen", fdopen)
        patch.setattr(os, "fsync", fsync)
        patch.setattr(os, "read", read)
        with pytest.raises(OSError, match="exact IO"):
            d.apply(s.store, s.approval)
    assert fired, "target boundary was not reached"
    assert not canonical.exists()
    assert pending.exists() == (kind != "stage" or boundary != "open")
    assert {p: p.read_bytes() for p in before} == before
    assert not used.exists() if kind == "stage" else True
    with pytest.raises(ValueError):
        with operation_lock.operation_lock(s.identity):
            pytest.fail("IO failure released an effectful writer")
    if pending.exists():
        with pytest.raises(ValueError):
            d.apply(s.store, s.approval)
