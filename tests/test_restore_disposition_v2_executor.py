"""Unchanged executor/CLI failure and supported continuation; synthetic IPC, real producer/ELF."""

import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_reopen import saved, window
from test_restore_disposition import observer
from test_restore_disposition_v2 import approve, propose
from test_restore_lifecycle import Niri

from niri_desktop_continuity import (
    cli,
    operation_lock,
    probe,
    restore,
    restore_layout,
    restore_producer,
)
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity.store import Store


@pytest.fixture
def executor_original(tmp_path, monkeypatch):
    assert "NIRI_SOCKET" not in os.environ
    compiler = shutil.which("cc")
    assert compiler, "cooperative ELF proof requires a local C compiler"
    source, binary = tmp_path / "cooperative.c", tmp_path / "ghostty"
    source.write_text(
        "#include <unistd.h>\n#include <stdlib.h>\n"
        'int main(void){for(int i=0;i<6000 && access(getenv("NDC_TEST_QUIT"),F_OK);i++)'
        "usleep(10000);return 0;}\n"
    )
    quit_file = tmp_path / "cooperative-quit"
    subprocess.run([compiler, str(source), "-o", str(binary)], check=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    children = []
    with tempfile.TemporaryDirectory(prefix="v2-ipc-", dir=os.environ.get("TMPDIR")) as short:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as endpoint:
            route = str(Path(short) / "sock")
            endpoint.bind(route)  # Metadata-only fake compositor. No listener or real Niri.
            st = os.stat(route)
            identity = {
                "boot_id": host.boot_id(),
                "niri_socket": route,
                "socket_device": st.st_dev,
                "socket_inode": st.st_ino,
            }
            desktop = Niri()
            for w in desktop.windows_by_id.values():
                w["pid"] = os.getpid()
            desktop.initialize()
            monkeypatch.setattr(restore, "compositor_identity", lambda: identity)
            monkeypatch.setattr(host, "compositor_identity", lambda: identity)
            monkeypatch.setattr(restore, "LiveDesktop", lambda: desktop)
            monkeypatch.setattr(probe, "capture", desktop.observe)

            # Default installed bootstrap, credential handshake, permit and same-PID ELF exec.
            # Only the Niri spawn transport is replaced. The parent keeps NIRI_SOCKET unset.
            def spawn(argv, expected_identity, deadline):
                assert expected_identity == identity
                child = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    env={
                        "PATH": os.defpath,
                        "HOME": str(tmp_path),
                        "NIRI_SOCKET": route,
                        "WAYLAND_DISPLAY": "fabricated",
                        "XDG_RUNTIME_DIR": str(runtime),
                        "NDC_TEST_QUIT": str(quit_file),
                    },
                )
                children.append(child)
                desktop.add(child.pid)

            monkeypatch.setattr(restore_producer, "niri_spawn", spawn)
            store = Store(tmp_path / "state")

            def run(wid):
                cwd = tmp_path / f"cwd-{wid}"
                cwd.mkdir(mode=0o700)
                snapshot = saved(
                    [
                        window(
                            wid,
                            1,
                            1,
                            reopen={"kind": "shell", "argv": [str(binary)], "cwd": str(cwd)},
                        )
                    ]
                )
                key = store.put("snapshots", snapshot)
                args = cli.parser().parse_args(
                    [
                        "--state-root",
                        str(store.root),
                        "restore",
                        "--apply",
                        key,
                        "--spawn-timeout",
                        "10",
                    ]
                )
                value, code = cli.run(args)
                return key, value, code

            def foreign_active(layout, proof, index):
                # Failure is forced exactly at the read-only association entry, not by editing
                # the resulting row, receipt, chain or exit. The real executor sets the row status.
                paths = sorted(history.fence_path(identity).glob("*.json"))
                assert [json.loads(p.read_text())["type"] for p in paths] == [
                    "prepared",
                    "intent",
                    "observed",
                    "intent",
                    "observed",
                ]
                proof.validate()
                assert index == 0 and not desktop.actions
                raise ValueError("foreign active window")

            try:
                with monkeypatch.context() as patch:
                    patch.setattr(restore_layout.Layout, "associate", foreign_active)
                    key, value, code = run(1)
                assert code == 2 and value["status"] == "interrupted"
                assert value.get("error") == "foreign active window", value
                directory = history.fence_path(identity)
                first = json.loads((directory / "00000000.json").read_text())
                prepared = store.get("receipts", first["receipt"])
                observed = store.get(
                    "receipts", json.loads((directory / "00000004.json").read_text())["receipt"]
                )
                from test_restore_disposition_handwritten import sha

                assert value["windows"] == [
                    {
                        "entry": prepared["plan"]["entries"][0],
                        "window_id": 1,
                        "status": "launch-indeterminate",
                        "geometry_coverage": {
                            "width": "requested-pending",
                            "position": "not-recorded",
                        },
                        "process_receipt": sha(observed["evidence"]),
                    }
                ]
                assert (
                    value["error_type"] == "ValueError"
                    and value["error"] == "foreign active window"
                )
                assert value["effects"] == [] and not desktop.actions
                result, exit_file = (
                    store.root / "original-result.json",
                    store.root / "original-exit.txt",
                )
                result.write_text(json.dumps(value) + "\n")
                exit_file.write_text(f"{code}\n")
                result.chmod(0o600)
                exit_file.chmod(0o600)
                s = SimpleNamespace(
                    store=store,
                    source=key,
                    identity=identity,
                    directory=directory,
                    attempt=first["attempt"],
                    interrupted=value["receipt_digest"],
                    result=result,
                    exit_file=exit_file,
                    desktop=desktop,
                    children=children,
                    run=run,
                    original=value,
                )
                s.observe = observer(s)
                yield s
            finally:
                quit_file.touch()  # Fixture-only cooperative exit; no product termination.
                for child in children:
                    child.stdin.close()
                    assert child.wait(timeout=10) == 0


def test_executor_original_failure_then_supported_fresh_source_reopening(executor_original):
    s = executor_original
    prefix = {p: p.read_bytes() for p in s.directory.iterdir()}
    original = s.result.read_bytes()
    result = d.apply(s.store, approve(s, propose(s)), observer=s.observe)
    assert result["status"] == "operator-accepted-partial" and result["effects"] == []
    assert s.result.read_bytes() == original and s.store.pointer("last-reopened") is None
    assert not s.desktop.actions and len(s.children) == 1
    first_window = s.children[0].pid + 10000
    before = {w["id"]: w for w in s.desktop.windows()}
    key, continued, code = s.run(2)  # Actual CLI -> executor -> producer -> layout -> terminal.
    assert code == 0 and key != s.source and continued["status"] == "reopened"
    assert len(s.children) == 2 and all(p.poll() is None for p in s.children)
    row = continued["windows"][0]
    wid = s.children[1].pid + 10000
    assert row["status"] == "placed" and row["restored_window_id"] == wid
    assert row["geometry_coverage"] == {"width": "requested-observed", "position": "not-recorded"}
    assert s.desktop.columns[1] == [[70, 71], [first_window], [80], [wid]]
    assert s.desktop.widths[wid] == 900.0 and s.desktop.focus == first_window
    after = {w["id"]: w for w in s.desktop.windows()}
    for old in before:
        assert after[old]["pid"] == before[old]["pid"]
        assert after[old]["layout"]["tile_size"] == before[old]["layout"]["tile_size"]
    assert continued["effects"] and s.desktop.actions
    assert s.store.pointer("last-reopened") == key
    process = s.store.get("receipts", row["process_receipt"])
    assert process["process"] == host.process_pin(s.children[1].pid)
    with operation_lock.operation_lock(s.identity):
        completed, active, count, _ = history.admit(s.identity)
    assert (
        active is None and len(completed) == 2 and completed[-1]["result"]["status"] == "reopened"
    )
    assert {p: p.read_bytes() for p in prefix} == prefix
    actions = list(s.desktop.actions)
    replay = restore.restore(
        s.store,
        s.source,
        s.desktop,
        apply=True,
        observe=lambda: pytest.fail("no original-source relaunch"),
    )
    assert replay["historical"] and replay["effects"] == []
    assert len(s.children) == 2 and s.desktop.actions == actions
    assert len(list(s.directory.iterdir())) == count
