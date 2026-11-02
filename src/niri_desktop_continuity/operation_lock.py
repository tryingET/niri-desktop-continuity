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


def fence_path(identity: dict) -> Path:
    """Where the retired strict restore engine kept one compositor instance's attempts."""
    pin = {key: identity.get(key) for key in ("boot_id", "socket_device", "socket_inode")}
    return runtime_root() / "niri-desktop-continuity-locks" / f"{digest(pin)}.restore"


def require_clear(identity: dict) -> None:
    """Any record that engine left for this compositor refuses effects; none is read or removed.

    Nothing writes these records any more, and they are named by boot and compositor socket, so
    the fence ends with the compositor it belongs to. A check that fails refuses too.
    """
    fence = fence_path(identity)
    for path in (fence, fence.with_suffix(".permit")):
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        raise ValueError(
            "a strict restore record fences this compositor until it restarts; no action taken"
        )


@contextmanager
def operation_lock(identity: dict, *, effectful: bool = True):
    """Serialize every caller; only effectful admission requires a clear restore fence.

    effectful=False confers no effect authority and does not change nested callers' defaults.
    """
    if type(effectful) is not bool:
        raise ValueError("effectful must be an explicit boolean")
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
        if effectful:
            require_clear(identity)
        # Only the explicitly pinned effect worker may receive this descriptor.
        # flock is retained by that worker's copy even if the coordinator exits.
        yield fd
    finally:
        # Never unlink a flock path; doing so could create two independently locked inodes.
        os.close(fd)
