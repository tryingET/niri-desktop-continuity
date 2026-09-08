"""One cooperating continuity writer per compositor, independent of state-root selection."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

from .model import digest
from .store import check_file, private_directory


def runtime_root() -> Path:
    # Canonical Linux runtime directory, not caller-controlled --state-root or XDG override.
    return Path(f"/run/user/{os.getuid()}")


@contextmanager
def operation_lock(identity: dict):
    root = runtime_root()
    if not root.is_dir():
        raise ValueError("canonical user runtime directory is unavailable")
    private_directory(root)
    directory = root / "niri-desktop-continuity-locks"
    private_directory(directory)
    pin = {key: identity.get(key) for key in ("boot_id", "socket_device", "socket_inode")}
    if any(value is None for value in pin.values()):
        raise ValueError("complete compositor socket identity required for writer admission")
    path = directory / f"{digest(pin)}.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        check_file(path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                "another continuity writer owns this compositor; no action taken"
            ) from None
        # Only the explicitly pinned effect worker may receive this descriptor.
        # flock is retained by that worker's copy even if the coordinator exits.
        yield fd
    finally:
        # Never unlink a flock path; doing so could create two independently locked inodes.
        os.close(fd)
