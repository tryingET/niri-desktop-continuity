"""Checked v3 Linux GNU LP64 interfaces; no raw syscalls or namespace path fallback."""

import ctypes
import fcntl
import os
import re
import sys

from . import restore_exited_values as v
from .restore_wire import remaining


class Statfs(ctypes.Structure):
    _fields_ = [
        ("f_type", ctypes.c_long),
        ("f_bsize", ctypes.c_long),
        ("f_blocks", ctypes.c_ulong),
        ("f_bfree", ctypes.c_ulong),
        ("f_bavail", ctypes.c_ulong),
        ("f_files", ctypes.c_ulong),
        ("f_ffree", ctypes.c_ulong),
        ("f_fsid", ctypes.c_int * 2),
        ("f_namelen", ctypes.c_long),
        ("f_frsize", ctypes.c_long),
        ("f_flags", ctypes.c_long),
        ("f_spare", ctypes.c_long * 4),
    ]


def abi():
    if (
        sys.platform != "linux"
        or sys.byteorder != "little"
        or getattr(sys.implementation, "_multiarch", None) != "x86_64-linux-gnu"
        or [
            (ctypes.sizeof(t), ctypes.alignment(t))
            for t in (ctypes.c_int, ctypes.c_long, ctypes.c_ulong, ctypes.c_void_p)
        ]
        != [(4, 4), (8, 8), (8, 8), (8, 8)]
        or ctypes.sizeof(Statfs) != 120
        or ctypes.alignment(Statfs) != 8
        or [getattr(Statfs, k).offset for k, _ in Statfs._fields_]
        != [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88]
    ):
        raise ValueError("unverified fstatfs ABI; only Linux x86_64 GNU LP64 admitted")


def procfs(fd):
    v.integer(fd, 0, 2147483647)
    abi()
    libc = ctypes.CDLL(None, use_errno=True)
    if not hasattr(libc, "gnu_get_libc_version") or not hasattr(libc, "fstatfs"):
        raise ValueError("checked GNU libc fstatfs required")
    function = libc.fstatfs
    function.argtypes, function.restype = [ctypes.c_int, ctypes.POINTER(Statfs)], ctypes.c_int
    result = Statfs()
    status = function(fd, ctypes.byref(result))
    if status != 0:
        raise OSError(ctypes.get_errno(), "procfs fstatfs refused")
    if result.f_type != 0x9FA0:
        raise ValueError("held root is not procfs")


def profile():
    release = os.uname().release
    match = (
        re.fullmatch(
            r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([A-Za-z0-9][A-Za-z0-9._+-]*))?",
            release,
            re.ASCII,
        )
        if isinstance(release, str) and len(release) <= 128
        else None
    )
    if (
        match is None
        or tuple(int(x) for x in match.group(1, 2, 3)) < (7, 2, 6)
        or re.search(
            r"(?:^|[._+-])(?:rc[0-9]*|alpha[0-9]*|beta[0-9]*|pre[0-9]*|next[0-9]*|git[0-9a-f]*|dirty)(?:$|[._+-])",
            match.group(4) or "",
            re.IGNORECASE | re.ASCII,
        )
    ):
        raise ValueError("stable upstream-compatible Linux release >=7.2.6 required")


class Statx(ctypes.Structure):
    # Opaque timestamps/tail; naturally aligned full 256-byte kernel buffer.
    _fields_ = [
        ("mask", ctypes.c_uint32),
        ("blksize", ctypes.c_uint32),
        ("attributes", ctypes.c_uint64),
        ("nlink", ctypes.c_uint32),
        ("uid", ctypes.c_uint32),
        ("gid", ctypes.c_uint32),
        ("mode", ctypes.c_uint16),
        ("spare", ctypes.c_uint16),
        ("inode", ctypes.c_uint64),
        ("size", ctypes.c_uint64),
        ("blocks", ctypes.c_uint64),
        ("attributes_mask", ctypes.c_uint64),
        ("timestamps", ctypes.c_uint64 * 8),
        ("rdev_major", ctypes.c_uint32),
        ("rdev_minor", ctypes.c_uint32),
        ("dev_major", ctypes.c_uint32),
        ("dev_minor", ctypes.c_uint32),
        ("mount_id", ctypes.c_uint64),
        ("tail", ctypes.c_uint64 * 13),
    ]


def identity(fd, *, deadline=None):
    v.integer(fd, 0, 2147483647)
    abi()
    fields = ("mask", "uid", "gid", "mode", "inode", "dev_major", "dev_minor", "mount_id")
    if (
        ctypes.sizeof(Statx) != 256
        or ctypes.alignment(Statx) != 8
        or [getattr(Statx, k).offset for k in fields] != [0, 20, 24, 28, 32, 136, 140, 144]
        or [
            (ctypes.sizeof(t), ctypes.alignment(t))
            for t in (ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint64)
        ]
        != [(2, 2), (4, 4), (8, 8)]
    ):
        raise ValueError("unverified statx ABI")
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "statx", None)
    if function is None or not hasattr(libc, "gnu_get_libc_version"):
        raise ValueError("GNU libc statx required")
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(Statx),
    ]
    function.restype = ctypes.c_int
    result = Statx()
    if deadline is not None:
        remaining(deadline)
    status = function(fd, b"", 0x1000, 0x411B, ctypes.byref(result))
    if status != 0:
        raise OSError(ctypes.get_errno(), "statx refused")
    if deadline is not None:
        remaining(deadline)
    if result.mask & 0x411B != 0x411B:
        raise ValueError("statx UNIQUE/type/mode/owner/inode mask required")
    v.integer(result.mount_id, 1, 2**64 - 1)
    actual = os.fstat(fd)
    if deadline is not None:
        remaining(deadline)
    measured = (
        os.makedev(result.dev_major, result.dev_minor),
        result.inode,
        result.mode,
        result.uid,
        result.gid,
    )
    if measured != (actual.st_dev, actual.st_ino, actual.st_mode, actual.st_uid, actual.st_gid):
        raise ValueError("same-FD statx/fstat disagreement")
    return (*measured, result.mount_id)


def namespace(pidfd, command):
    v.integer(pidfd, 0, 2147483647)
    if type(command) is not int or command not in (0xFF05, 0xFF09):
        raise ValueError("only active pidfd namespace commands admitted")
    return fcntl.ioctl(pidfd, command, 0)
