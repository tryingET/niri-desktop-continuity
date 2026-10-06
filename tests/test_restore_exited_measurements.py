"""Actual running peer ELF/generations; only cooperative, test-owned processes."""

import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from test_restore_exited_history import scene
from test_restore_exited_native import isolated_namespace

from niri_desktop_continuity import restore_exited_proof as proof
from niri_desktop_continuity import restore_exited_scope as native
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity.restore_exited_resources import FDImage

PEER = """
import json,os,select,socket,sys
from pathlib import Path
root=Path(sys.argv[1]); values=json.loads((root/"values.json").read_text())
listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
listener.bind(str(root/"peer.sock"));os.chmod(root/"peer.sock",0o600);listener.listen(1)
(root/"ready").touch()
def connection():
    ready=select.select([listener,sys.stdin],[],[])[0]
    if sys.stdin in ready:
        sys.stdin.buffer.read()
        return None
    return listener.accept()[0]
stream=connection()
if stream is None:sys.exit(0)
buffer=b""
while True:
    if (root/"exec-request").exists():
        os.set_inheritable(stream.fileno(),True)
        os.execv(str(root/"next-image"),[str(root/"next-image"),str(root/"exec-done")])
    ready=select.select([stream,sys.stdin],[],[],0.01)[0]
    if sys.stdin in ready:
        assert sys.stdin.buffer.read()==b""
        break
    if stream not in ready:continue
    block=stream.recv(128)
    if not block:
        stream.close()
        stream=connection() # FD release is not a termination command.
        if stream is None:break
        buffer=b""
        continue
    buffer+=block
    while b"\\n" in buffer:
        line,buffer=buffer.split(b"\\n",1)
        name=json.loads(line)
        reply=values[name]
        if (root/"topology-drift").exists() and name=="Windows":
            reply=json.loads(json.dumps(reply));reply[0]["layout"]["tile_size"][1]+=1
        stream.sendall((json.dumps({"Ok":{name:reply}})+"\\n").encode())
if stream is not None:stream.close()
listener.close()
"""


def wait(path):
    until = time.monotonic() + 5
    while not path.exists():
        assert time.monotonic() < until, "cooperative fixture did not reach its checkpoint"
        time.sleep(0.005)


def cooperative():
    return subprocess.Popen(
        [sys.executable, "-I", "-c", "import sys;sys.stdin.buffer.read()"], stdin=subprocess.PIPE
    )


def measurements(root, case):
    root = Path(root)
    compiler = root / "next.c"
    compiler.write_text(
        "#include <stdio.h>\n#include <unistd.h>\n"
        'int main(int n,char **v){FILE *f=fopen(v[1],"w");if(!f)return 2;'
        'fputs("ready",f);fclose(f);char b;while(read(0,&b,1)>0){}return 0;}\n'
    )
    subprocess.run(["cc", str(compiler), "-o", str(root / "next-image")], check=True)
    old, protected = cooperative(), cooperative()
    original = host.process_pin(old.pid)
    if case not in ("occupied-original", "occupied-replacement"):
        old.stdin.close()
        assert old.wait(timeout=5) == 0
    if case == "occupied-replacement":
        original["start_ticks"] -= 1  # Purported older generation; real numeric slot occupied.
    state = scene(0)
    state["windows"][0]["pid"] = os.getpid()  # Allowed protected/controller overlap.
    state["windows"][1]["pid"] = protected.pid
    if case == "associated-id":
        state["windows"][0]["id"] = 12000
        state["workspaces"][0]["active_window_id"] = 12000
    if case == "old-pid-window":
        state["windows"][0]["pid"] = old.pid
    (root / "values.json").write_text(
        json.dumps(
            {
                "Version": "fixture-version",
                "Windows": state["windows"],
                "Workspaces": state["workspaces"],
                "Outputs": {"FIXTURE-1": {"name": "FIXTURE-1", "logical": {"scale": 1.0}}},
            }
        )
    )
    (root / "peer.py").write_text(PEER)
    peer = subprocess.Popen(
        [sys.executable, "-I", str(root / "peer.py"), str(root)], stdin=subprocess.PIPE
    )
    try:
        wait(root / "ready")
        pin = host.process_pin(peer.pid)
        info = (root / "peer.sock").stat()
        source = {
            "identity": {
                "boot_id": pin["boot_id"],
                "niri_socket": str(root / "peer.sock"),
                "socket_device": info.st_dev,
                "socket_inode": info.st_ino,
            },
            "inventory_complete": True,
            "niri_version": {"compositor": "fixture-version", "cli": "different-client"},
            "process_inventory": [
                {
                    "pid": peer.pid,
                    "start_ticks": pin["start_ticks"],
                    "ppid": os.getpid(),
                    "comm": "niri",
                    "cgroup": None,
                },
                {"pid": 2147483600, "start_ticks": 1, "ppid": 1, "comm": "niri", "cgroup": None},
            ],
        }
        holders, phase = [], [False]
        scope_class, generation_class, transport_class = (
            native.Scope,
            native.Generation,
            proof.Transport,
        )
        image_close = FDImage.close

        class Scope(scope_class):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                holders.extend([self.fd, self.pidns[0], self.userns[0], self.own_fd])

            def info(self, pid, **kw):
                value = super().info(pid, **kw)
                if phase[0] and case == "controller-reparent" and pid == os.getpid():
                    value = deepcopy(value)
                    value["ppid"] = peer.pid
                return value

        class Generation(generation_class):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                holders.append(self.fd)

        class Transport(transport_class):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                holders.append(self.socket.fileno())

        def close(image):
            if image.fd is not None:
                holders.append(image.fd)
            image_close(image)
            if phase[0] and case == "baseexception-close":
                raise OSError("fabricated post-close error")

        with (
            patch.object(native, "Scope", Scope),
            patch.object(native, "Generation", Generation),
            patch.object(proof, "Transport", Transport),
            patch.object(FDImage, "close", close),
        ):
            try:
                with proof.current(source, original, 12000, expires=int(time.time()) + 60) as (
                    current,
                    validate,
                ):
                    assert current["peer"]["process"] == pin
                    assert current["protected_window_ids"] == [70, 80]
                    assert current["caller"]["process"]["pid"] == os.getpid()
                    assert current["peer"]["running_image"]["sha256"] != "0" * 64
                    phase[0] = True
                    if case == "peer-exec":
                        (root / "exec-request").touch()
                        wait(root / "exec-done")
                        assert host.process_pin(peer.pid) == pin  # Same actual birth tuple.
                    elif case == "peer-exit":
                        peer.stdin.close()
                        assert peer.wait(timeout=5) == 0
                    elif case == "protected-exit":
                        protected.stdin.close()
                        assert protected.wait(timeout=5) == 0
                    elif case == "topology":
                        (root / "topology-drift").touch()
                    elif case == "baseexception-close":
                        raise KeyboardInterrupt("primary fixture interruption")
                    validate()
                    assert case == "success", "drift was accepted"
            except KeyboardInterrupt as exc:
                assert case == "baseexception-close" and str(exc) == "primary fixture interruption"
                assert isinstance(exc.__cause__, OSError)
            except (ValueError, OSError) as exc:
                assert case not in ("success", "baseexception-close"), repr(exc)
                if case == "peer-exec":
                    assert "executable changed" in str(exc), repr(exc)
            else:
                assert case == "success"
        for fd in holders:
            with pytest.raises(OSError):
                os.fstat(fd)
        if case != "peer-exit":
            assert peer.poll() is None  # Resource release did not terminate the peer.
        if case != "protected-exit":
            assert protected.poll() is None
    finally:
        for child in (peer, protected, old):
            if not child.stdin.closed:
                child.stdin.close()
            assert child.wait(timeout=5) == 0


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "peer-exec",
        "peer-exit",
        "protected-exit",
        "topology",
        "controller-reparent",
        "baseexception-close",
        "associated-id",
        "old-pid-window",
        "occupied-original",
        "occupied-replacement",
    ],
)
def test_real_measured_peer_protected_and_caller_vetoes(tmp_path, case):
    code = f"""
sys.path.insert(0, {str(Path(__file__).parent)!r})
from test_restore_exited_measurements import measurements
measurements({str(tmp_path)!r}, {case!r})
"""
    result = isolated_namespace(code, data_root=tmp_path)
    assert result.returncode == 0, result.stderr
