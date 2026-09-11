"""Cooperating owner anchor → canonical ledger → existing compositor lock order."""

import fcntl
import os
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from . import recovery_profile
from .recovery_protocol import require
from .resolution_io import check_root, root_pin
from .store import check_file, private_directory

_HELD = ContextVar("resolution_owner_locks", default=None)


@contextmanager
def mutex(path):
    private_directory(path.parent, create=False)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        check_file(path)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(fd)
        require((info.st_dev, info.st_ino) == (path.stat().st_dev, path.stat().st_ino))
        yield
        require((info.st_dev, info.st_ino) == (path.stat().st_dev, path.stat().st_ino))
    finally:
        os.close(fd)  # Never unlink or unlock a descriptor owned by another process.


@contextmanager
def owner_guard():
    held = _HELD.get()
    if held is not None:
        check_root(held)
        yield
        return
    anchor = recovery_profile.profile_path()
    with mutex(anchor.parent / ".recovery-owner.lock"):
        profile = recovery_profile.identify_profile()
        root = root_pin(profile["ledger_root"])
        with mutex(Path(root["path"]) / ".recovery-ledger.lock"):
            check_root(root)
            token = _HELD.set(root)
            try:
                yield
                check_root(root)
            finally:
                _HELD.reset(token)


def serialized(function):
    @wraps(function)
    def call(*args, **kwargs):
        with owner_guard():
            return function(*args, **kwargs)

    return call
