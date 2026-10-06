"""Handwritten self theorem, status framing, mount provenance and refresh oracles."""

import ctypes
import errno
import os
from types import SimpleNamespace

import pytest
from test_restore_exited_native import isolated_namespace

from niri_desktop_continuity import restore_exited_proc as proc
from niri_desktop_continuity import restore_exited_syscalls as calls

STAT = b"42 (fixture (name)) S 1 " + b"0 " * 17 + b"123 0\n"
STATUS = (
    b"Name:\tfixture\nTgid:\t42\nPid:\t42\nPPid:\t1\nUid:\t1000 1000 1000 1000\n"
    b"NSpid:\t42\nNStgid:\t42\nVmSize:\t101 kB\nFDSize:\t64\n"
)
EXPECTED = {"process": {"boot_id": "fixture", "pid": 42, "start_ticks": 123}, "ppid": 1}


def test_stable_projection_accepts_mutable_irrelevant_counters_and_live_state():
    for i in range(3):
        status = STATUS.replace(b"101 kB", str(i).encode() + b" kB").replace(b"64\n", b"128\n")
        assert (
            proc.process_info(STAT.replace(b") S ", b") R "), status, 42, 1000, "fixture")
            == EXPECTED
        )


@pytest.mark.parametrize(
    "vector",
    [
        b"42 42",
        b"42 43",
        b"1 42 42",
        b"",
        b"0",
        b"-42",
        b"042",
        b"2147483648",
        b"true",
        b"42.0",
        b"43",
    ],
)
@pytest.mark.parametrize("field", [b"NSpid", b"NStgid"])
def test_ancestor_same_number_and_malformed_vectors_refuse(vector, field):
    status = STATUS.replace(field + b":\t42", field + b":\t" + vector)
    with pytest.raises(ValueError):
        proc.process_info(STAT, status, 42, 1000, "fixture")


@pytest.mark.parametrize("field", [b"Pid", b"Tgid", b"PPid", b"Uid", b"NSpid", b"NStgid"])
@pytest.mark.parametrize("change", ["missing", "duplicate", "malformed", "different"])
def test_required_identity_fields_are_closed(field, change):
    line = next(line for line in STATUS.splitlines(keepends=True) if line.startswith(field + b":"))
    replacement = {
        "missing": b"",
        "duplicate": line + line,
        "malformed": line.replace(b":", b" "),
        "different": field + b":\t999\n",
    }[change]
    with pytest.raises(ValueError):
        proc.process_info(STAT, STATUS.replace(line, replacement), 42, 1000, "fixture")


@pytest.mark.parametrize(
    "status",
    [
        STATUS[:-1],
        STATUS + b"garbage\n",
        STATUS + b"Name: duplicate\n",
        STATUS + b"x:\0\n",
        b"x:" + b"x" * (128 * 1024) + b"\n",
    ],
)
def test_framing_is_bounded_and_complete(status):
    with pytest.raises(ValueError):
        proc.process_info(STAT, status, 42, 1000, "fixture")


@pytest.mark.parametrize(
    "release,allowed",
    [
        ("7.2.6", True),
        ("7.2.6-arch2-1", True),
        ("7.10.0", True),
        ("8.0.0-custom", True),
        ("7.2.5", False),
        ("7.3.0-rc1", False),
        ("7.2", False),
        ("v7.2.6", False),
        ("07.2.6", False),
        ("7.2.6+", False),
        ("7.2.6\n", False),
        ("7.2.6-dirty", False),
        ("7.2.6-stable.GITabc-build", False),
        ("7.2.6-beta2", False),
        ("7.2.6-pre", False),
        ("7.2.6-next0", False),
        ("7.2.6-alpha", False),
        ("7.2.6-" + "x" * 123, False),
    ],
)
def test_release_profile(release, allowed, monkeypatch):
    monkeypatch.setattr(os, "uname", lambda: SimpleNamespace(release=release))
    if allowed:
        calls.profile()
    else:
        with pytest.raises(ValueError):
            calls.profile()


@pytest.mark.parametrize(
    "mask", [0x411B | 0x800, 0x411B, *[0x411B & ~b for b in (1, 2, 8, 16, 256, 16384)], 0x111B]
)
@pytest.mark.parametrize("mount", [0, 1, 2**63, 2**64 - 1])
def test_statx_handwritten_bytes_preserve_uint64_and_require_every_bit(mask, mount, monkeypatch):
    def statx(fd, path, flags, requested, pointer):
        assert (fd, path, flags, requested) == (0, b"", 0x1000, 0x411B)
        raw = bytearray(256)
        for offset, size, value in [
            (0, 4, mask),
            (20, 4, 1000),
            (24, 4, 1001),
            (28, 2, 0o100444),
            (32, 8, 99),
            (136, 4, 0),
            (140, 4, 20),
            (144, 8, mount),
        ]:
            raw[offset : offset + size] = value.to_bytes(size, "little")
        raw[255] = 0xFF  # Unused kernel tail need not be zero on return.
        ctypes.memmove(pointer, bytes(raw), 256)
        return 0

    monkeypatch.setattr(
        ctypes, "CDLL", lambda *_a, **_k: SimpleNamespace(statx=statx, gnu_get_libc_version=True)
    )
    monkeypatch.setattr(
        os,
        "fstat",
        lambda fd: SimpleNamespace(
            st_dev=os.makedev(0, 20), st_ino=99, st_mode=0o100444, st_uid=1000, st_gid=1001
        ),
    )
    if mask & 0x411B == 0x411B and mount:
        assert calls.identity(0) == (os.makedev(0, 20), 99, 0o100444, 1000, 1001, mount)
    else:
        with pytest.raises(ValueError):
            calls.identity(0)


@pytest.mark.parametrize("error", [errno.ENOSYS, errno.EINVAL, errno.EACCES, errno.EIO])
def test_statx_errno_refuses(error, monkeypatch):
    def statx(*_):
        ctypes.set_errno(error)
        return -1

    monkeypatch.setattr(
        ctypes, "CDLL", lambda *_a, **_k: SimpleNamespace(statx=statx, gnu_get_libc_version=True)
    )
    with pytest.raises(OSError) as result:
        calls.identity(0)
    assert result.value.errno == error


def test_libc_statx_and_pidfd_ioctl_independent_headers(tmp_path):
    import subprocess

    source = tmp_path / "abi.c"
    source.write_text("""#define _GNU_SOURCE
#include <sys/stat.h>
#include <linux/pidfd.h>
#include <stddef.h>
_Static_assert(sizeof(struct statx)==256, "size");
_Static_assert(_Alignof(struct statx)==8, "alignment");
_Static_assert(offsetof(struct statx,stx_mask)==0, "mask");
_Static_assert(offsetof(struct statx,stx_uid)==20, "uid");
_Static_assert(offsetof(struct statx,stx_gid)==24, "gid");
_Static_assert(offsetof(struct statx,stx_mode)==28, "mode");
_Static_assert(offsetof(struct statx,stx_ino)==32, "ino");
_Static_assert(offsetof(struct statx,stx_dev_major)==136, "major");
_Static_assert(offsetof(struct statx,stx_dev_minor)==140, "minor");
_Static_assert(offsetof(struct statx,stx_mnt_id)==144, "mount");
_Static_assert(PIDFD_GET_PID_NAMESPACE==0xff05, "pid ioctl");
_Static_assert(PIDFD_GET_USER_NAMESPACE==0xff09, "user ioctl");
_Static_assert((STATX_MNT_ID_UNIQUE|STATX_TYPE|STATX_MODE|STATX_UID|STATX_GID|STATX_INO)==0x411b, "mask");
""")
    subprocess.run(["cc", "-c", str(source), "-o", str(tmp_path / "abi.o")], check=True)


@pytest.mark.parametrize(
    "target", ["root", "directory", "stat", "status", "sys", "kernel", "random", "boot_id"]
)
def test_actual_same_superblock_bind_graft_refuses(target):
    code = f"""
import os, subprocess, time
from niri_desktop_continuity.restore_exited_scope import Scope
scope = Scope(time.monotonic()+5)
paths = {{"root":"/proc", "directory":f"/proc/{{os.getpid()}}",
         "stat":f"/proc/{{os.getpid()}}/stat", "status":f"/proc/{{os.getpid()}}/status",
         "sys":"/proc/sys", "kernel":"/proc/sys/kernel", "random":"/proc/sys/kernel/random",
         "boot_id":"/proc/sys/kernel/random/boot_id"}}
path = paths[{target!r}]
before = os.stat(path)
subprocess.run(["mount", "--bind", path, path], check=True)
after = os.stat(path)
assert (before.st_dev,before.st_ino)==(after.st_dev,after.st_ino)
try:
    scope.check()
except ValueError as e:
    assert "mount" in str(e) or "root replaced" in str(e), str(e)
else:
    raise AssertionError("same-superblock graft accepted")
finally:
    scope.close()
"""
    result = isolated_namespace(code)
    assert result.returncode == 0, result.stderr


def test_fresh_namespace_membership_change_refuses_with_unchanged_old_handle():
    result = isolated_namespace("""
import ctypes, os, time
from niri_desktop_continuity.restore_exited_scope import Scope
scope = Scope(time.monotonic()+5)
old = os.fstat(scope.userns[0])
libc = ctypes.CDLL(None, use_errno=True)
assert libc.unshare(0x10000000) == 0, ctypes.get_errno()
with open('/proc/self/setgroups','w') as f: f.write('deny')
with open('/proc/self/uid_map','w') as f: f.write('0 0 1\\n')
with open('/proc/self/gid_map','w') as f: f.write('0 0 1\\n')
assert libc.prctl(4,1,0,0,0)==0
assert os.fstat(scope.userns[0]).st_ino == old.st_ino
try:
    scope.check()
except ValueError as e:
    assert 'namespace differs' in str(e), str(e)
else:
    raise AssertionError('retained handle mistaken for active membership')
finally:
    scope.close()
""")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("bad", [True, False, -1, 2**31, 0.0, "0"])
def test_statx_fd_is_checked_before_ctypes(bad, monkeypatch):
    monkeypatch.setattr(ctypes, "CDLL", lambda *_a, **_k: pytest.fail("bad fd reached libc"))
    with pytest.raises(ValueError):
        calls.identity(bad)


def test_statx_missing_symbol_and_wrong_abi_refuse(monkeypatch):
    import sys

    monkeypatch.setattr(
        ctypes, "CDLL", lambda *_a, **_k: SimpleNamespace(gnu_get_libc_version=True)
    )
    with pytest.raises(ValueError, match="statx required"):
        calls.identity(0)
    monkeypatch.setattr(sys.implementation, "_multiarch", "aarch64-linux-gnu")
    monkeypatch.setattr(ctypes, "CDLL", lambda *_a, **_k: pytest.fail("bad ABI reached libc"))
    with pytest.raises(ValueError, match="unverified"):
        calls.identity(0)


@pytest.mark.parametrize(
    "raw",
    [
        STAT.replace(b"42 ", b"43 ", 1),
        STAT.replace(b") S ", b") Z "),
        STAT.replace(b"123 0", b"0 0"),
        STAT.replace(b"S 1 ", b"S 0 "),
        STAT[:-1],
    ],
)
def test_stat_own_pid_live_state_parent_start_and_framing(raw):
    with pytest.raises(ValueError):
        proc.process_info(raw, STATUS, 42, 1000, "fixture")


@pytest.mark.parametrize("value", ["0", "01", "+2", "2/..", " 2", "2\n", "٢", "2147483648"])
def test_pinned_self_target_is_canonical_pid_not_a_numeric_task_fallback(value):
    code = f"""
import time
from unittest.mock import patch
from niri_desktop_continuity.restore_exited_scope import Scope
with patch('os.readlink',return_value={value!r}):
    try:
        Scope(time.monotonic()+5)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid self admitted')
"""
    result = isolated_namespace(code)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "error", [errno.ESRCH, errno.EACCES, errno.ENOSYS, errno.EINVAL, errno.EMFILE]
)
def test_pidfd_ioctl_errors_never_supply_absence(error):
    result = isolated_namespace(f"""
import os, time
from unittest.mock import patch
from niri_desktop_continuity import restore_exited_syscalls as calls
from niri_desktop_continuity.restore_exited_scope import Scope
scope = Scope(time.monotonic()+5)
try:
    with patch.object(calls, 'namespace', side_effect=OSError({error}, 'ioctl refused')):
        try:
            scope.check()
        except OSError as e:
            assert e.errno == {error}
        else:
            raise AssertionError('ioctl error accepted')
finally:
    scope.close()
""")
    assert result.returncode == 0, result.stderr
