"""Given genuine self coordinates, inaccessible init is not a scope prerequisite."""

import pytest
from test_restore_exited_native import isolated_namespace

MAPPED_USER = r"""
import ctypes, errno, os
before_pid = os.stat("/proc/self/ns/pid")
before_proc = os.stat("/proc")
before_user = os.stat("/proc/self/ns/user")
libc = ctypes.CDLL(None, use_errno=True)
assert libc.unshare(0x10000000) == 0, ctypes.get_errno()
with open('/proc/self/setgroups', 'w') as f:
    f.write('deny')
with open('/proc/self/uid_map', 'w') as f:
    f.write('1000 0 1\n')
with open('/proc/self/gid_map', 'w') as f:
    f.write('1000 0 1\n')
class Header(ctypes.Structure):
    _fields_ = [('version', ctypes.c_uint), ('pid', ctypes.c_int)]
class Caps(ctypes.Structure):
    _fields_ = [('effective', ctypes.c_uint), ('permitted', ctypes.c_uint),
                ('inheritable', ctypes.c_uint)]
h = Header(0x20080522, 0)
caps = (Caps * 2)()
assert libc.capset(ctypes.byref(h), caps) == 0
assert libc.capget(ctypes.byref(h), caps) == 0
assert all(c.effective == c.permitted == c.inheritable == 0 for c in caps)
assert libc.prctl(4, 1, 0, 0, 0) == 0  # dumpable, not a capability grant
assert os.getuid() == os.geteuid() == 1000
assert os.getppid() == 1
assert os.stat("/proc/self/ns/pid").st_ino == before_pid.st_ino
assert os.stat("/proc/self/ns/user").st_ino != before_user.st_ino
assert os.stat("/proc").st_ino == before_proc.st_ino
assert os.stat("/proc").st_uid != os.getuid()  # Structural overflow owner is NOT a process owner.
try:
    fd = os.open('/proc/1/ns/pid', os.O_RDONLY | os.O_CLOEXEC)
except OSError as e:
    assert e.errno == errno.EACCES, e
else:
    os.close(fd)
    raise AssertionError('init namespace was not denied')
print('init EACCES; uid/gid map 1000 0 1; all capabilities zero', flush=True)
"""


@pytest.mark.parametrize("denied_init", [False, True], ids=["readable-control", "denied-init"])
def test_given_genuine_self_when_init_denied_then_actual_scope_passes(denied_init):
    # Given outer proc/PID scope and direct child; optionally nested mapped user with no caps.
    # When actual product Scope proves itself, Then both cases pass without requiring init.
    result = isolated_namespace(
        (MAPPED_USER if denied_init else "")
        + """
import os, time
from niri_desktop_continuity.restore_exited_scope import Scope
scope = Scope(time.monotonic() + 5)
try:
    assert scope.info(os.getpid())["ppid"] == 1
    scope.check()
finally:
    scope.close()
"""
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_given_denied_init_when_full_product_current_then_passes(tmp_path):
    from pathlib import Path

    code = (
        MAPPED_USER
        + f"""
sys.path.insert(0, {str(Path(__file__).parent)!r})
from test_restore_exited_measurements import measurements
measurements({str(tmp_path)!r}, "success")
print("full actual current proof passed", flush=True)
"""
    )
    result = isolated_namespace(code, data_root=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "full actual current proof passed" in result.stdout


def test_nonleader_thread_uses_genuine_process_self():
    result = isolated_namespace("""
import threading, time
from niri_desktop_continuity.restore_exited_scope import Scope
errors = []
def worker():
    try:
        scope = Scope(time.monotonic()+5)
        scope.check()
        scope.close()
    except BaseException as e:
        errors.append(e)
t = threading.Thread(target=worker)
t.start(); t.join()
assert not errors, errors
""")
    assert result.returncode == 0, result.stderr
