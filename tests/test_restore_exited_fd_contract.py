"""Acquisition/teardown fault accounting and bounded simultaneous native descriptors."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from test_restore_exited_native import isolated_namespace


def fd_exercise(boundary, fault, weak=False):
    import time

    from niri_desktop_continuity import restore_exited_syscalls as calls
    from niri_desktop_continuity import restore_host as host
    from niri_desktop_continuity.restore_exited_image import image
    from niri_desktop_continuity.restore_exited_scope import AncestorGeneration, Generation, Scope

    owned, peak, count, injected = set(), [0], [0], [False]
    real_open, real_close, real_pidfd, real_ns = os.open, os.close, host.open_pidfd, calls.namespace
    real_identity, real_read, real_link = calls.identity, os.read, os.readlink
    closes = []

    def trigger(which):
        if which == boundary:
            count[0] += 1
            if count[0] == fault:
                injected[0] = True
                raise KeyboardInterrupt("primary-acquisition")

    def acquired(fd):
        assert fd not in owned
        owned.add(fd)
        peak[0] = max(peak[0], len(owned))
        return fd

    def opened(path, flags, **kw):
        # Product route must never use namespace paths, multi-component leaves or absolute exe.
        assert path == "/proc" or "/" not in path, path
        trigger("open")
        return acquired(real_open(path, flags, **kw))

    def pidfd(pid):
        assert pid != 1
        trigger("pidfd")
        return acquired(real_pidfd(pid))

    def namespace(fd, command):
        assert fd in owned and command in (0xFF05, 0xFF09)
        trigger("ioctl")
        return acquired(real_ns(fd, command))

    def close(fd):
        assert fd in owned, ("double/unowned close", fd)
        owned.remove(fd)  # A close error never permits a retry on this number.
        real_close(fd)
        closes.append(fd)
        if boundary == "close":
            injected[0] = True
            raise OSError("teardown-" + str(len(closes)))

    def identity(fd, **kw):
        trigger("statx")
        return real_identity(fd, **kw)

    def read(fd, size):
        trigger("read")
        return real_read(fd, size)

    def link(path, **kw):
        assert path == "" and kw["dir_fd"] in owned
        trigger("readlink")
        return real_link(path, **kw)

    with (
        patch.object(os, "open", opened),
        patch.object(os, "close", close),
        patch.object(host, "open_pidfd", pidfd),
        patch.object(calls, "namespace", namespace),
        patch.object(calls, "identity", identity),
        patch.object(os, "read", read),
        patch.object(os, "readlink", link),
    ):
        try:
            scope = Scope(time.monotonic() + 10)
            try:
                generation = (AncestorGeneration if weak else Generation)(scope, os.getpid())
                try:
                    measured = None if weak else image(scope, generation)
                    try:
                        held_count = len(owned)
                        for _ in range(20):
                            scope.check()
                            generation.check()
                            if not weak:
                                fresh = image(scope, generation)
                                assert fresh.pin == measured.pin
                                fresh.close()
                            assert len(owned) == held_count
                    finally:
                        if measured is not None:
                            measured.close()
                finally:
                    generation.close()
            finally:
                scope.close()
        except KeyboardInterrupt as e:
            assert str(e) == "primary-acquisition" and boundary != "none"
        except OSError:
            assert boundary == "close"
        else:
            assert boundary == "none", "requested acquisition fault did not fire"
    assert boundary == "none" or injected[0], "requested acquisition fault did not fire"
    assert not owned, owned
    assert peak[0] <= 24, (
        peak
    )  # Fixed handles plus short-lived proc route samples, not cycle count.


@pytest.mark.parametrize("weak", [False, True])
@pytest.mark.parametrize(
    "boundary,fault",
    [
        ("none", 0),
        ("close", 0),
        *[
            (b, n)
            for b in ("open", "pidfd", "ioctl", "statx", "read", "readlink")
            for n in ((1, 2) if b == "pidfd" else (1, 2, 7, 30))
        ],
    ],
)
def test_every_owned_fd_closes_on_baseexception_and_samples_stay_bounded(boundary, fault, weak):
    result = isolated_namespace(f"""
sys.path.insert(0,{str(Path(__file__).parent)!r})
from test_restore_exited_fd_contract import fd_exercise
fd_exercise({boundary!r},{fault},{weak!r})
""")
    assert result.returncode == 0, result.stderr


def test_given_unreachable_fault_when_exercised_then_not_counted_as_injected():
    result = isolated_namespace(f"""
sys.path.insert(0,{str(Path(__file__).parent)!r})
from test_restore_exited_fd_contract import fd_exercise
try:
    fd_exercise('pidfd', 7)
except AssertionError as error:
    assert str(error) == 'requested acquisition fault did not fire', str(error)
else:
    raise AssertionError('unreachable injection incorrectly reported success')
""")
    assert result.returncode == 0, result.stderr


def test_namespace_fd_zero_is_owned_not_a_success_boolean():
    result = isolated_namespace("""
import os,time
from unittest.mock import patch
from niri_desktop_continuity import restore_exited_syscalls as calls
from niri_desktop_continuity.restore_exited_scope import Scope
real = calls.namespace
first = [True]
def namespace(fd, cmd):
    ns = real(fd,cmd)
    if first[0]:
        first[0] = False
        os.dup2(ns,0,inheritable=False)
        os.close(ns)
        return 0
    return ns
with patch.object(calls,'namespace',namespace):
    scope = Scope(time.monotonic()+5)
    assert scope.pidns[0] == 0
    scope.check()
    scope.close()
try:
    os.fstat(0)
except OSError:
    pass
else:
    raise AssertionError('namespace fd zero leaked')
""")
    assert result.returncode == 0, result.stderr


def test_foreign_readable_fd_is_rejected_before_any_read(tmp_path):
    result = isolated_namespace(
        """
import os,time
from pathlib import Path
from unittest.mock import patch
from niri_desktop_continuity.restore_exited_scope import Scope
Path('/e/foreign').write_text('not proc evidence')
real_open, real_read = os.open, os.read
foreign = []
def opened(path,flags,**kw):
    if path == 'status':
        fd = real_open('/e/foreign', flags)
        foreign.append(fd)
        return fd
    return real_open(path,flags,**kw)
def read(fd,size):
    assert fd not in foreign, 'foreign data was read before provenance rejection'
    return real_read(fd,size)
with patch.object(os,'open',opened), patch.object(os,'read',read):
    try:
        Scope(time.monotonic()+5)
    except ValueError as e:
        assert 'foreign proc mount' in str(e),str(e)
    else:
        raise AssertionError('foreign readable FD accepted')
assert foreign
""",
        data_root=tmp_path,
    )
    assert result.returncode == 0, result.stderr


def test_primary_baseexception_and_each_teardown_failure_remain_visible():
    result = isolated_namespace("""
import os,time
from unittest.mock import patch
from niri_desktop_continuity.restore_exited_scope import Scope
real_read,real_close = os.read,os.close
closed, armed = [], [False]
def read(*a):
    armed[0] = True
    raise KeyboardInterrupt('primary interruption')
def close(fd):
    real_close(fd)
    if not armed[0]: return
    closed.append(fd)
    raise OSError('close failure '+str(len(closed)))
try:
    with patch.object(os,'read',read),patch.object(os,'close',close):
        Scope(time.monotonic()+5)
except BaseException as e:
    pending,seen,messages = [e],set(),[]
    while pending:
        error = pending.pop()
        if id(error) in seen: continue
        seen.add(id(error));messages.append(str(error))
        pending.extend(getattr(error,"exceptions",()))
        pending.extend(x for x in (error.__context__,error.__cause__) if x is not None)
    assert 'primary interruption' in messages, messages
    assert len(closed)>=3,closed
    assert sum(m.startswith('close failure') for m in messages)==len(closed),messages
else:
    raise AssertionError('interruption was lost')
""")
    assert result.returncode == 0, result.stderr


def test_unrelated_open_failure_cannot_qualify_close_injection():
    result = isolated_namespace(f"""
sys.path.insert(0,{str(Path(__file__).parent)!r})
from unittest.mock import patch
from test_restore_exited_fd_contract import fd_exercise
with patch('os.open', side_effect=OSError('unrelated preacquisition failure')):
    try:
        fd_exercise('close',0,True)
    except AssertionError as error:
        assert str(error) == 'requested acquisition fault did not fire',str(error)
    else:
        raise AssertionError('unrelated refusal qualified as close fault')
""")
    assert result.returncode == 0, result.stderr
