"""Exact immutable Store reuse and identity-checked durability, with fabricated private files."""

import os
from pathlib import Path

import pytest

from niri_desktop_continuity.restore_retained import evidence
from niri_desktop_continuity.store import Store, sync_artifact


@pytest.mark.parametrize("failure", ["file", "directory"])
def test_failed_put_retry_of_equal_bytes_still_requires_both_barriers(
    tmp_path, monkeypatch, failure
):
    store = Store(tmp_path / "store")
    value = {"fabricated": "immutable"}
    fsync, paths = os.fsync, []

    def broken(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if (failure == "file" and path.parent == store.root / "plans") or (
            failure == "directory" and path == store.root / "plans"
        ):
            raise OSError("fabricated persistent sync failure")
        fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", broken)
        for _ in range(2):
            with pytest.raises(OSError):
                store.put("plans", value)
    original = next((store.root / "plans").iterdir()).read_bytes()

    def traced(fd):
        paths.append(Path(os.readlink(f"/proc/self/fd/{fd}")))
        fsync(fd)

    monkeypatch.setattr(os, "fsync", traced)
    key = store.put("plans", value)
    assert paths == [store.path("plans", key), store.root / "plans"]
    assert store.path("plans", key).read_bytes() == original


@pytest.mark.parametrize(
    "change", ["truncated", "unsafe", "symlink", "file-inode", "directory-inode", "bytes"]
)
def test_barrier_refuses_damaged_or_replaced_validated_files(tmp_path, monkeypatch, change):
    store = Store(tmp_path / "store")
    key = store.put("plans", {"fabricated": 1})
    path = store.path("plans", key)
    _, pin = evidence(path)
    original = path.read_bytes()
    if change == "truncated":
        path.write_bytes(b"{")
    elif change == "unsafe":
        path.chmod(0o644)
    elif change == "bytes":
        path.write_bytes(original + b" ")
    elif change == "directory-inode":
        parent = path.parent
        displaced = parent.with_name("displaced")
        parent.rename(displaced)
        parent.mkdir(mode=0o700)
        (displaced / path.name).rename(path)
    else:
        displaced = path.with_suffix(".displaced")
        path.rename(displaced)
        if change == "symlink":
            path.symlink_to(displaced)
        else:
            path.write_bytes(original)
            path.chmod(0o600)
    calls = []
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append(fd))
    with pytest.raises((ValueError, OSError)):
        sync_artifact(pin)
    assert not calls


def test_substitution_between_file_and_directory_barriers_is_not_authority(tmp_path, monkeypatch):
    store = Store(tmp_path / "store")
    key = store.put("plans", {"fabricated": 1})
    path = store.path("plans", key)
    _, pin = evidence(path)
    fsync, calls = os.fsync, []

    def changed(fd):
        calls.append(Path(os.readlink(f"/proc/self/fd/{fd}")))
        fsync(fd)
        if len(calls) == 1:
            data = path.read_bytes()
            path.rename(path.with_suffix(".displaced"))
            path.write_bytes(data)
            path.chmod(0o600)

    monkeypatch.setattr(os, "fsync", changed)
    with pytest.raises(ValueError):
        sync_artifact(pin)
    assert calls == [path]


def test_existing_partial_json_is_not_repaired_by_put(tmp_path):
    from niri_desktop_continuity.model import digest

    store = Store(tmp_path / "store")
    value = {"fabricated": 1}
    path = store.path("plans", digest(value))
    path.write_bytes(b'{"fabricated":')
    path.chmod(0o600)
    with pytest.raises(ValueError):
        store.put("plans", value)
    assert path.read_bytes() == b'{"fabricated":'
