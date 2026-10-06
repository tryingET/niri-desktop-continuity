"""Real v3 lifecycle: native predicates veto after last capacity / staged closure barriers."""

import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from test_restore_exited_history import FAMILY, fabricate, scene
from test_restore_exited_measurements import PEER, cooperative, wait
from test_restore_exited_native import isolated_namespace

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_disposition_v2_io as io
from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity.restore_reader import DependencyReader


def exercise(root, drift, phase):
    root = Path(root)
    c = root / "next.c"
    c.write_text(
        '#include <stdio.h>\n#include <unistd.h>\nint main(int n,char**v){FILE*f=fopen(v[1],"w");if(!f)return 2;fclose(f);char b;while(read(0,&b,1)>0){}return 0;}\n'
    )
    subprocess.run(["cc", str(c), "-o", str(root / "next-image")], check=True)
    old, protected = cooperative(), cooperative()
    original = host.process_pin(old.pid)
    old.stdin.close()
    assert old.wait(timeout=5) == 0
    state = scene(0)
    state["windows"][0]["pid"] = os.getpid()
    state["windows"][1]["pid"] = protected.pid
    values = {
        "Version": "fixture-version",
        "Windows": state["windows"],
        "Workspaces": state["workspaces"],
        "Outputs": {"FIXTURE-1": {"name": "FIXTURE-1", "logical": {"scale": 1.0}}},
    }
    (root / "values.json").write_text(json.dumps(values))
    server = PEER.replace(
        "        stream.sendall(",
        """        if (root/"focus-drift").exists() and name in ("Windows","Workspaces"):
            reply=json.loads(json.dumps(reply))
            for row in reply:
                row["is_focused"]=row["id"]==(70 if name=="Windows" else 1)
                if name=="Workspaces":row["is_active"]=row["id"]==1
        if (root/"ancestor-window").exists() and name=="Windows":
            reply=json.loads(json.dumps(reply));reply[0]["pid"]=int((root/"ancestor-window").read_text())
        stream.sendall(""",
    )
    (root / "peer.py").write_text(server)
    peer = subprocess.Popen(
        [sys.executable, "-I", str(root / "peer.py"), str(root)], stdin=subprocess.PIPE
    )
    try:
        wait(root / "ready")
        peer_pin = host.process_pin(peer.pid)
        sock = (root / "peer.sock").stat()
        identity = {
            "boot_id": peer_pin["boot_id"],
            "niri_socket": str(root / "peer.sock"),
            "socket_device": sock.st_dev,
            "socket_inode": sock.st_ino,
        }
        with pytest.MonkeyPatch.context() as monkey:
            s = fabricate(
                root,
                monkey,
                identity=identity,
                process=original,
                peer={
                    "pid": peer.pid,
                    "start_ticks": peer_pin["start_ticks"],
                    "ppid": os.getpid(),
                    "comm": "niri",
                    "cgroup": None,
                },
            )
            plan = d.propose(
                s.store, None, s.attempt, s.interrupted, s.result, s.exit_file, family=FAMILY
            )
            key = plan["plan_digest"]
            approval = d.approve(
                s.store,
                key,
                confirmation=key,
                acceptance="operator-accepted-partial",
                attest_client_returned=True,
                platform_ack=plan["platform_digest"],
            )["approval_digest"]
            expires = s.store.get("plans", key)["expires"]
            armed, injected = [False], [False]
            scopes = []
            scope_class = native.Scope
            real_pidfd, real_info, real_stat, real_clock = (
                host.open_pidfd,
                native.Scope.info,
                os.fstat,
                time.time,
            )
            reserve, fresh = DependencyReader.reserve_commit, io.fresh_chain

            class Scope(scope_class):
                def __init__(self, *a, **kw):
                    super().__init__(*a, **kw)
                    scopes.append(self)

            def arm():
                assert not armed[0]
                armed[0] = True
                if drift == "peer-exit":
                    peer.stdin.close()
                    assert peer.wait(timeout=5) == 0
                elif drift == "protected-exit":
                    protected.stdin.close()
                    assert protected.wait(timeout=5) == 0
                elif drift == "image":
                    (root / "exec-request").touch()
                    wait(root / "exec-done")
                    assert host.process_pin(peer.pid) == peer_pin
                elif drift in ("topology", "focus"):
                    (root / (drift + "-drift")).touch()
                elif drift in ("root-graft", "status-graft"):
                    path = "/proc" if drift == "root-graft" else f"/proc/{os.getpid()}/status"
                    subprocess.run(["mount", "--bind", path, path], check=True)
                elif drift == "ancestor-window":
                    assert os.getppid() != 1
                    (root / "ancestor-window").write_text(str(os.getppid()))
                    injected[0] = True
                elif drift == "endpoint":
                    (root / "peer.sock").chmod(0o620)

            def capacity(reader, artifacts, **kw):
                result = reserve(reader, artifacts, **kw)
                if phase == "capacity" and any(
                    p.suffix == ".pending" and p.exists() for p, _ in artifacts
                ):
                    arm()  # AFTER final prospective capacity work returned.
                return result

            def barrier(*a, **kw):
                result = fresh(*a, **kw)
                if phase == "prepublish" and kw.get("staged"):
                    arm()  # AFTER actual new-reader staged closure/barriers.
                return result

            def pidfd(pid):
                if armed[0] and drift == "occupied" and pid == original["pid"]:
                    # Exact primitive boundary double for reuse; a real FD to a known live
                    # fixture replaces ESRCH. Never search arbitrary numeric PIDs.
                    return real_pidfd(peer.pid)
                return real_pidfd(pid)

            def info(scope, pid, **kw):
                row = real_info(scope, pid, **kw)
                if armed[0] and drift == "controller" and pid == os.getpid():
                    row = deepcopy(row)
                    row["ppid"] = peer.pid
                if armed[0] and drift == "ancestor" and pid == os.getppid():
                    assert pid != 1
                    injected[0] = True
                    row = deepcopy(row)
                    row["ppid"] = peer.pid
                return row

            def fstat(fd):
                actual = real_stat(fd)
                if armed[0] and drift == "scope" and fd == scopes[-1].fd:
                    fields = list(actual)
                    fields[1] = actual.st_ino + 1
                    return os.stat_result(fields)
                return actual

            with (
                patch.object(native, "Scope", Scope),
                patch.object(scope_class, "info", info),
                patch.object(host, "open_pidfd", pidfd),
                patch.object(os, "fstat", fstat),
                patch.object(
                    time,
                    "time",
                    lambda: expires + 1 if armed[0] and drift == "expiry" else real_clock(),
                ),
                patch.object(DependencyReader, "reserve_commit", capacity),
                patch.object(io, "fresh_chain", barrier),
            ):
                with pytest.raises((ValueError, OSError)):
                    d.apply(s.store, approval)
            if drift in ("ancestor", "ancestor-window"):
                assert injected[0], "late weak-ancestor injection did not fire"
            assert armed[0], "failure occurred before the tested late boundary"
            assert (s.directory / "00000010.pending").exists()
            assert not (s.directory / "00000010.json").exists()
            assert s.store.path("used", approval).exists() == (phase == "prepublish")
            with pytest.raises(ValueError):
                with operation_lock.operation_lock(identity):
                    raise AssertionError("late-veto stage released an effectful writer")
            with pytest.raises(ValueError):
                d.apply(s.store, approval)
    finally:
        for child in (peer, protected):
            if not child.stdin.closed:
                child.stdin.close()
            assert child.wait(timeout=5) == 0


@pytest.mark.parametrize("phase", ["capacity", "prepublish"])
@pytest.mark.parametrize(
    "drift",
    [
        "occupied",
        "peer-exit",
        "protected-exit",
        "image",
        "endpoint",
        "scope",
        "root-graft",
        "status-graft",
        "controller",
        "topology",
        "focus",
        "expiry",
    ],
)
def test_native_veto_at_each_late_authority_boundary(tmp_path, phase, drift):
    code = f"""
sys.path.insert(0, {str(Path(__file__).parent)!r})
from test_restore_exited_late_native import exercise
exercise({str(tmp_path)!r}, {drift!r}, {phase!r})
"""
    result = isolated_namespace(code, data_root=tmp_path)
    assert result.returncode == 0, result.stderr
