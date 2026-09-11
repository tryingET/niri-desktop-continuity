"""Bounded private resolution data. No Store construction or executable admission on reads."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from .model import digest
from .recovery_profile import pin_spec, safe_path
from .recovery_protocol import decode, encode, fields, hexkey, require
from .store import HEX, Store, private_directory

MARKERS = ("prepared", "used", "ready", "pending", "final")
LIMIT = 1024 * 1024


def raw(path, limit=LIMIT):
    path = safe_path(str(path), private=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require(len(data) <= limit)
    require(
        (before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns)
    )
    require(path.stat().st_ino == after.st_ino and path.stat().st_dev == after.st_dev)
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def retained(path):
    data = raw(path)
    return {
        "path": str(path),
        "sha256": sha(data),
        "raw_base64": base64.b64encode(data).decode("ascii"),
    }


def retained_bytes(value):
    fields(value, ("path", "sha256", "raw_base64"))
    pin_spec({k: value[k] for k in ("path", "sha256")})
    require(type(value["raw_base64"]) is str)
    try:
        data = base64.b64decode(value["raw_base64"], validate=True)
    except (ValueError, TypeError):
        raise ValueError("invalid retained bytes") from None
    require(len(data) <= LIMIT and sha(data) == value["sha256"])
    require(base64.b64encode(data).decode("ascii") == value["raw_base64"])
    return data


def root_pin(path):
    require(isinstance(path, (str, Path)) and str(Path(path)) == str(path))
    path = Path(path)
    require(path.is_absolute() and str(path) == str(path.absolute()) and ".." not in path.parts)
    private_directory(path, create=False)
    info = path.stat()
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino}


def check_root(value):
    fields(value, ("path", "device", "inode"))
    require(all(type(value[k]) is int and value[k] >= 0 for k in ("device", "inode")))
    require(root_pin(value["path"]) == value)


def names(path, maximum=4096):
    if not path.exists():
        require(not path.is_symlink())
        return []
    private_directory(path, create=False)
    result = []
    for entry in path.iterdir():
        require(len(result) < maximum and entry.suffix == ".json" and HEX.fullmatch(entry.stem))
        safe_path(str(entry), private=True)
        result.append(entry.stem)
    return sorted(result)


class Objects:
    """Only resolution-owned namespaces; construction is always read-only."""

    def __init__(self, root):
        self.root = Path(root)
        private_directory(self.root, create=False)

    def path(self, kind, key):
        require(kind in (*MARKERS, "objects", "archives"))
        hexkey(key)
        suffix = ".bin" if kind == "archives" else ".json"
        return (
            self.root
            / ("profile-archives" if kind == "archives" else f"resolution-{kind}")
            / f"{key}{suffix}"
        )

    def get(self, key):
        value = decode(raw(self.path("objects", key)))
        require(type(value) is dict and digest(value) == key)
        return value

    def create(self, kind, key, data):
        path = self.path(kind, key)
        private_directory(path.parent)
        Store._create(self, path, data)

    _sync_dir = staticmethod(Store._sync_dir)

    def put(self, value):
        key = digest(value)
        try:
            self.create("objects", key, encode(value))
        except FileExistsError:
            require(self.get(key) == value)
        return key

    def archive(self, data):
        key = sha(data)
        try:
            self.create("archives", key, data)
        except FileExistsError:
            require(raw(self.path("archives", key)) == data)
        return key

    def marker(self, kind, key, value=None):
        require(kind in MARKERS)
        if value is not None:
            self.create(kind, key, encode(value))
        return decode(raw(self.path(kind, key)))

    def markers(self):
        return {
            kind: {key: self.marker(kind, key) for key in names(self.path(kind, "0" * 64).parent)}
            for kind in MARKERS
        }
