"""Existing installed console + default producer/bootstrap + real pidfds, fabricated ELF/IPC."""

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_reopen import IDENTITY, saved, window
from test_restore_cli_grammar import niri_change
from test_restore_handshake import fabricated_elf as fabricated_elf  # noqa: F401
from test_restore_integration import Topology
from test_restore_lifecycle import Niri


@pytest.mark.parametrize("installation", ["editable", "wheel"])
def test_installed_console_restores_multiple_real_hosts_with_fake_ipc(
    tmp_path, fabricated_elf, installation
):
    # Extract only handwritten fixture classes, never import a test module into the wheel process:
    # test_reopen's development sys.path setup would otherwise silently substitute checkout code.
    fixture = tmp_path / "restore_fixture.py"
    fixture.write_text(
        "import re\nfrom copy import deepcopy\nfrom niri_desktop_continuity import restore\n"
        "from niri_desktop_continuity.model import normalized_snapshot\n"
        + f"IDENTITY = {IDENTITY!r}\n"
        + "\n".join(inspect.getsource(v) for v in (niri_change, window, saved, Topology, Niri))
    )
    python = Path(sys.executable)
    if installation == "wheel":
        root = Path(__file__).resolve().parents[1]

        def tool(*args):
            result = subprocess.run(
                args,
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "UV_OFFLINE": "1"},
            )
            assert result.returncode == 0, result.stderr

        tool("uv", "build", "--wheel", "--out-dir", str(tmp_path / "dist"))
        tool("uv", "venv", "--python", sys.executable, str(tmp_path / "venv"))
        python = tmp_path / "venv" / "bin" / "python"
        wheel = next((tmp_path / "dist").glob("*.whl"))
        tool("uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel))
    runner = tmp_path / "driver.py"
    output = tmp_path / "outcome.json"
    # Tests provide only IPC/capture/lock locations. No production launch/proof callback is replaced.
    runner.write_text(r"""
import json, os, runpy, socket, subprocess, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from restore_fixture import Niri, saved, window
from niri_desktop_continuity import operation_lock, probe, restore, restore_producer
if os.environ['NDC_TEST_INSTALLATION'] == 'wheel':
    import niri_desktop_continuity
    assert Path(niri_desktop_continuity.__file__).is_relative_to(Path(sys.prefix))
from niri_desktop_continuity.store import Store
root, elf, console = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
runtime = root / "runtime"
runtime.mkdir(mode=0o700)
operation_lock.runtime_root = lambda: runtime
quit = root / "quit"
children = []
desktop = Niri()
desktop.columns, desktop.windows_by_id, desktop.widths, desktop.focus = {41: []}, {}, {}, None
desktop.ws = [{'id': 41, 'idx': 1, 'output': 'DP-1', 'is_focused': True}]
desktop.initialize()
# Keep the actual action subprocess boundary; reads remain fabricated model observations.
model_action = desktop.action
desktop.action = restore.LiveDesktop().action
restore.LiveDesktop = lambda: desktop
probe.capture = desktop.observe
store = Store(root / "state")
multi = os.environ['NDC_TEST_INSTALLATION'] == 'wheel'
entries = [window(i, i if multi else 1, 1, tile=1 if multi else i, reopen={"kind": "command", "argv": [elf, "-e", "tool", "a b", "$HOME"], "cwd": str(root)}) for i in (1, 2)]
key = store.put("snapshots", saved(entries))
with tempfile.TemporaryDirectory(prefix="ni-", dir=os.environ["TMPDIR"]) as short:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        route = str(Path(short) / "sock")
        sock.bind(route)
        os.environ.update(NIRI_SOCKET=route, WAYLAND_DISPLAY="fabricated", XDG_RUNTIME_DIR=str(runtime), NDC_TEST_QUIT=str(quit), NORMAL_USER_SETTING="literal $HOME")
        def dispatch(argv, identity, deadline):
            # Bootstrap is still the installed isolated Python module; same-process fd exec.
            with operation_lock.operation_lock(identity, effectful=False):
                raise AssertionError("nested writer admitted")
        def fake_niri(argv, identity, deadline):
            try: dispatch(argv, identity, deadline)
            except ValueError as exc: assert "another continuity writer" in str(exc)
            report = root / ("report-" + str(len(children)))
            process = subprocess.Popen(argv, env={**os.environ, "NDC_TEST_REPORT": str(report)}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            children.append(process)
            desktop.add(process.pid)
        # Exercise the production niri_spawn subprocess transport too. Only the executable/server
        # are fabricated; the console, producer, handshake and process proof are installed code.
        bindir = root / 'bin'
        bindir.mkdir()
        executable = bindir / 'niri'
        executable.write_text('#!' + sys.executable + '\n' + '''import json, os, socket, sys
assert sys.argv[1:3] == ['msg', 'action']
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(5)
    client.connect(os.environ['NIRI_SOCKET'])
    client.sendall((json.dumps(sys.argv[1:])+'\\n').encode())
    sys.exit(0 if client.recv(16) == b'ok' else 2)
''')
        executable.chmod(0o700)
        os.environ['PATH'] = str(bindir) + os.pathsep + os.defpath
        sock.listen(4)
        sock.settimeout(0.1)
        stopped, errors = threading.Event(), []
        def serve():
            while not stopped.is_set():
                try: connection, _ = sock.accept()
                except TimeoutError: continue
                with connection:
                    connection.settimeout(5)
                    try:
                        data = connection.makefile('rb').readline(65537)
                        assert len(data) <= 65536 and data.endswith(b'\n')
                        args = json.loads(data)
                        assert args[:2] == ['msg', 'action']
                        if args[2:4] == ['spawn', '--']:
                            fake_niri(args[4:], probe.compositor_identity(), 0)
                        else:
                            # CLI parsing happens before any model effect, just as with clap.
                            from restore_fixture import niri_change
                            try:
                                if args[2] == 'set-column-width':
                                    niri_change(args[3])
                                elif args[2] == 'move-floating-window':
                                    niri_change(args[6], position=True)
                                    niri_change(args[8], position=True)
                            except ValueError:
                                connection.sendall(b'error')
                                continue
                            model_action(*args[2:])
                        connection.sendall(b'ok')
                    except BaseException as exc:
                        errors.append(repr(exc))
                        connection.sendall(b'error')
        server = threading.Thread(target=serve)
        server.start()
        sys.argv = [console, "--state-root", str(store.root), "restore", "--apply", key, "--spawn-timeout", "10"]
        try:
            # These must exit 2, not pass through Python float() or mutate the fake desktop.
            for invalid in ('800.0', '800.5', '2147483648', '-2147483649'):
                rejected = subprocess.run([str(executable), 'msg', 'action', 'set-column-width', invalid])
                assert rejected.returncode == 2 and not desktop.actions
            try: runpy.run_path(console, run_name="__main__")
            except SystemExit as exit: assert exit.code == 0
            pids = [p.pid for p in children]
            assert len(pids) == 2 and not errors, errors
            by_index = {w['idx']: desktop.columns[w['id']] for w in desktop.ws}
            assert by_index == ({1: [[pids[0]+10000]], 2: [[pids[1]+10000]], 3: []} if multi else {1: [[pids[0]+10000, pids[1]+10000]], 2: []})
            assert desktop.focus == pids[1 if multi else 0]+10000
            assert store.pointer("last-reopened") == key
            for pid in pids: assert desktop.widths[pid+10000] == 900.
            for index in range(2):
                lines = (root / ("report-" + str(index))).read_text().splitlines()
                assert [v for v in lines if v.startswith("fd=")] == ["fd=0", "fd=1", "fd=2"]
                assert [v[4:] for v in lines if v.startswith("arg=")][-4:] == ["-e", "tool", "a b", "$HOME"]
                assert "normal=literal $HOME" in lines and "backend=wayland" in lines
            (root / "outcome.json").write_text(json.dumps({"hosts": len(pids), "layout": "observed", "native": False}))
        finally:
            stopped.set()
            server.join(timeout=6)
            assert not server.is_alive()
            quit.touch()
            for p in children: p.wait(timeout=35)
""")
    console = python.parent / "niri-desktop-continuity"
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"NIRI_SOCKET", "WAYLAND_SOCKET", "DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH"}
    }
    env.update(
        NDC_TEST_INSTALLATION=installation,
        HOME=str(tmp_path),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        XDG_STATE_HOME=str(tmp_path / "state-home"),
    )
    result = subprocess.run(
        [
            str(python),
            str(runner),
            str(tmp_path),
            str(tmp_path),
            str(fabricated_elf),
            str(console),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=70,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(output.read_text()) == {"hosts": 2, "layout": "observed", "native": False}
    assert json.loads(result.stdout)["status"] == "reopened"
