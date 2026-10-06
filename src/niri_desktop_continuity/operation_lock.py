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
def operation_lock(
    identity: dict,
    *,
    effectful: bool = True,
    existing_only: bool = False,
    _preserve_disposition_failures: bool = False,
):
    """Serialize every caller; only effectful admission requires a clear restore fence.

    effectful=False confers no effect authority and does not change nested callers' defaults.
    """
    if type(effectful) is not bool:
        raise ValueError("effectful must be an explicit boolean")
    if type(existing_only) is not bool:
        raise ValueError("existing_only must be an explicit boolean")
    if existing_only and effectful:
        raise ValueError("existing-only admission confers no desktop effect authority")
    if type(_preserve_disposition_failures) is not bool:
        raise ValueError("disposition preservation must be an explicit boolean")
    if _preserve_disposition_failures and (effectful or not existing_only):
        raise ValueError("disposition preservation requires existing-only read-only admission")
    root = runtime_root()
    if not root.is_dir():
        raise ValueError("canonical user runtime directory is unavailable")
    private_directory(root, create=not existing_only)
    directory = root / "niri-desktop-continuity-locks"
    private_directory(directory, create=not existing_only)
    pin = {key: identity.get(key) for key in ("boot_id", "socket_device", "socket_inode")}
    if any(value is None for value in pin.values()):
        raise ValueError("complete compositor socket identity required for writer admission")
    path = directory / f"{digest(pin)}.lock"
    flags = os.O_RDONLY if existing_only else os.O_RDWR | os.O_CREAT
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    primary = None
    try:
        check_file(path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                "another continuity writer owns this compositor; no action taken"
            ) from None
        if effectful:
            from .restore_history import require_clear

            require_clear(identity)
        # Only the explicitly pinned effect worker may receive this descriptor.
        # flock is retained by that worker's copy even if the coordinator exits.
        yield fd
    except BaseException as failure:
        primary = failure
        raise
    finally:
        # Never unlink a flock path; doing so could create two independently locked inodes.
        held, fd = fd, None  # Retire before the sole close attempt, even on interruption.
        if _preserve_disposition_failures:
            from .restore_disposition_failure import release

            release(primary, [lambda: os.close(held)])
        else:
            os.close(held)
