"""Reservation-bound v2 raw IO only. The legacy retained.raw reader is unchanged."""

import hashlib
import os
import stat
from pathlib import Path

from .restore_disposition_failure import release
from .store import check_file, private_directory

STAT_FIELDS = "st_dev st_ino st_size st_mtime_ns st_ctime_ns st_uid st_mode st_nlink".split()
CHUNK = 64 * 1024


def signature(info):
    return tuple(getattr(info, key) for key in STAT_FIELDS)


def identity(path):
    path = Path(path)
    private_directory(path.parent, create=False)
    check_file(path)
    info, parent = path.lstat(), path.parent.lstat()
    return signature(info), (parent.st_dev, parent.st_ino)


def _parent(path, directory, expected):
    private_directory(path.parent, create=False)
    for info in (os.fstat(directory), path.parent.lstat()):
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or (info.st_dev, info.st_ino) != expected
        ):
            raise ValueError("reserved dependency parent changed")


def _unchanged(path, directory, fd, reservation):
    expected, parent = reservation
    _parent(path, directory, parent)
    for info in (os.fstat(fd), path.lstat()):
        # ubs:ignore[python.ctcompare.secret_eq] -- File metadata, not auth.
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or signature(info) != expected
        ):
            raise ValueError("reserved dependency changed, grew or was replaced")


def raw(path, reservation, counters):
    """Read at most the reserved length, with no buffering, read-ahead or extra probe byte.

    Held file/parent FDs and current path must match reservation BEFORE every read and
    afterward. Short reads refuse without retry, keeping total request sizes within the
    reservation too. Metadata checks are observations, not an atomic filesystem freeze.
    Counters count Python os.read calls/requested lengths and returned bytes, including
    bytes subsequently rejected for drift. No failed buffer is returned for decoding.
    """
    path = Path(path)
    expected, parent = reservation
    directory = fd = None
    failure = None
    try:
        directory = os.open(
            path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        _parent(path, directory, parent)
        fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=directory,
        )
        _unchanged(path, directory, fd, reservation)
        remaining = expected[2]
        blocks = []
        while remaining:
            _unchanged(path, directory, fd, reservation)
            requested = min(remaining, CHUNK)
            counters.validation_read_calls += 1
            counters.validation_requested_bytes += requested
            block = os.read(fd, requested)
            counters.validation_bytes += len(block)
            _unchanged(path, directory, fd, reservation)
            if len(block) != requested:
                raise ValueError("short reserved dependency read; no retry")
            blocks.append(block)
            remaining -= len(block)
        _unchanged(path, directory, fd, reservation)
        data = b"".join(blocks)
        return data, {
            "path": str(path),
            "directory": {"device": parent[0], "inode": parent[1]},
            "device": expected[0],
            "inode": expected[1],
            "sha256": hashlib.sha256(data).hexdigest(),
            "length": len(data),
        }
    except BaseException as exc:
        failure = exc
        raise
    finally:
        held, fd, directory = (fd, directory), None, None
        try:
            release(
                failure,
                [lambda value=value: os.close(value) for value in held if value is not None],
            )
        except BaseException:
            if failure is not None:
                try:
                    failure.add_note(
                        "A dependency descriptor cleanup also failed; original failure retained"
                    )
                except BaseException:
                    pass  # Compatibility note cannot replace the retained actual failures.
            raise
