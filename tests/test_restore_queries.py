"""Actual launch-bound executor with native reads and a handwritten fake Niri server."""

import errno
import io
import json
import os
import runpy
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from test_reopen import saved, window
from test_restore_handshake import fabricated_elf as fabricated_elf  # noqa: F401
from test_restore_lifecycle import Niri

from niri_desktop_continuity import operation_lock, probe, restore
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.restore_attempt import Attempt
from niri_desktop_continuity.store import Store


def run_boundary(
    root,
    elf,
    failures=1,
    query="windows",
    damage=None,
    effect_fault=None,
    spawn_fault=None,
    console=None,
    scenario=None,
    cancellation=KeyboardInterrupt,
):
    """Only IPC, capture and fault boundaries are fabricated; launch/proof are real."""
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    quit_file = root / "quit"
    desktop = Niri()
    desktop.columns, desktop.windows_by_id, desktop.widths = {41: [], 42: []}, {}, {}
    desktop.focus = None
    desktop.ws = [
        {"id": 41, "idx": 1, "output": "DP-1", "is_focused": False},
        {"id": 42, "idx": 2, "output": "DP-1", "is_focused": True},
    ]
    protected = scenario in {"protected-overlap", "protected-drift"}
    if protected:
        desktop.columns[41] = [[999]]
        desktop.windows_by_id[999] = {"id": 999, "pid": os.getpid(), "is_floating": False}
        desktop.widths[999] = 640.0
    desktop.initialize()
    children, observed, errors, faults, attempts, quits = [], [], [], [], [], []
    real_popen, real_observed, real_append = subprocess.Popen, Attempt.observed, Attempt.append
    real_query, real_sleep = restore.LiveDesktop.__dict__["_query"], restore.LiveDesktop.sleep
    real_clock, real_ns, real_loads = time.monotonic, time.monotonic_ns, json.loads
    offset, baseline, samples, query_stack, queried, communications = [0.0], [], [0], [], [], []
    events, sleeps, version_faults, version_results, post = [], [], [], [], []
    cancelled, decode_armed = [], [False]
    cancel_error = cancellation("fabricated reached cancellation")
    stale = None
    if scenario == "stale-generation":
        from niri_desktop_continuity.restore_host import process_pin

        old = real_popen(
            [sys.executable, "-I", "-c", "import sys;sys.stdin.read()"], stdin=subprocess.PIPE
        )
        stale = process_pin(old.pid)
        old.stdin.close()
        assert old.wait(timeout=20) == 0
        events.append("actual old generation cooperatively exited and reaped")
    bindir = root / "bin"
    bindir.mkdir()
    executable = bindir / "niri"
    executable.write_text(
        "#!"
        + sys.executable
        + "\n"
        + r"""
import json, os, socket, sys
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(20)
    client.connect(os.environ['NIRI_SOCKET'])
    client.sendall((json.dumps(sys.argv[1:]) + '\n').encode())
    reply = client.makefile('rb').readline(1048577)
    value = json.loads(reply)
    if value['status']:
        sys.exit(value['status'])
    if sys.argv[1:3] == ['msg', '--json']:
        print(json.dumps(value['body']))
"""
    )
    executable.chmod(0o700)
    store = Store(root / "state")
    previous = store.put("snapshots", saved([]))
    store.pointer("last-reopened", previous)
    entries = [
        window(
            i, i, 1, reopen={"kind": "command", "argv": [str(elf), "-e", "tool"], "cwd": str(root)}
        )
        for i in (1, 2)
    ]
    key = store.put("snapshots", saved(entries))

    def observed_record(attempt, evidence):
        result = real_observed(attempt, evidence)
        if evidence.get("phase") == "process-observed":
            assert evidence["process"]["pid"] == children[len(observed)].pid
            assert evidence["ownership"] == "process-only"
            observed.append(dict(evidence))
        return result

    action_constructions = []

    def tracked_query(self, name, *, deadline=None):
        row = {
            "name": name,
            "deadline": deadline,
            "start": real_clock() + offset[0],
            "constructions": 0,
            "after_proofs": len(observed),
        }
        queried.append(row)
        query_stack.append(row)
        try:
            # Exact descriptor binding works on both original static and adopted instance query;
            # no signature probing, TypeError fallback or second call.
            return real_query.__get__(self, type(self))(name, deadline=deadline)
        finally:
            query_stack.pop()

    def appended(attempt, kind, payload):
        result = real_append(attempt, kind, payload)
        if scenario == "persist-expiry" and kind == "association" and payload["entry"] == 1:
            events.append("actual second association persisted before expiry")
            offset[0] += 21.0
        return result

    def cancel(phase):
        assert len(observed) == 2 and all(c.poll() is None for c in children)
        assert not cancelled
        cancelled.append(phase)
        print("REACHED cancellation", phase, file=sys.stderr, flush=True)
        raise cancel_error

    def sleep(self, seconds):
        sleeps.append(seconds)
        if scenario == "cancel-sleep" and len(observed) == 2:
            cancel("sleep")
        return real_sleep(self, seconds)

    def loads(value, *args, **kwargs):
        if (
            scenario == "cancel-decode"
            and decode_armed[0]
            and threading.current_thread() is threading.main_thread()
        ):
            decode_armed[0] = False
            cancel("decode")
        return real_loads(value, *args, **kwargs)

    class NoKillClient:
        def __init__(self, client, row, action):
            self.client, self.row, self.action = client, row, action
            self.used = False

        @property
        def returncode(self):
            return self.client.returncode

        def communicate(self, *, timeout):
            assert not self.used and 0 < timeout <= 10.001
            self.used = True
            if self.row["deadline"] is not None:
                # Independently bracket the supplied remaining caller budget, not a production helper.
                assert timeout <= self.row["deadline"] - (real_clock() + offset[0]) + 0.05
            communications.append(
                {"name": self.row["name"], "deadline": self.row["deadline"], "timeout": timeout}
            )
            result = self.client.communicate(timeout=timeout)
            if len(observed) == 2 and self.row["name"] == "windows":
                if scenario == "cancel-communicate":
                    cancel("communicate")
                decode_armed[0] = scenario == "cancel-decode"
            if (
                scenario == "shared-expiry"
                and len(observed) == 2
                and self.row["deadline"] is not None
            ):
                offset[0] += 7.0
                events.append("charged-" + self.row["name"])
            if (
                scenario == "caller-expiry"
                and len(observed) == 2
                and self.row["name"] == "windows"
                and self.row["deadline"] is not None
            ):
                assert len(children) == 2 and all(c.poll() is None for c in children)
                assert len(desktop.actions) == 1 and not faults
                offset[0] += 21.0
                events.append("actual second Windows reply returned beyond caller deadline")
                print("REACHED post-launch caller expiry", file=sys.stderr, flush=True)
            if post and len(post) == 4 and self.row["name"] == "outputs":
                post.append(real_clock() + offset[0])
            return result

        def wait(self, *, timeout):
            assert not self.used
            self.used = True
            result = self.client.wait(timeout=timeout)
            if len(observed) == 2 and self.action[0] != "spawn":
                if scenario == "cancel-action":
                    cancel("action")
                if scenario == "postcondition-limit" and not post:
                    post.append(real_clock() + offset[0])
            return result

        def kill(self):
            raise AssertionError("kill forbidden")

        def terminate(self):
            raise AssertionError("terminate forbidden")

        def __enter__(self):
            raise AssertionError("context cleanup forbidden")

        def __exit__(self, *args):
            raise AssertionError("context cleanup forbidden")

    def constructor(argv, *args, **kwargs):
        if argv[:3] == ["niri", "msg", "--json"]:
            query_stack[-1]["constructions"] += 1
        if argv[:3] == ["niri", "msg", "action"]:
            action_constructions.append(list(argv[3:]))
            if argv[3] == "spawn" and len(observed) == 1:
                baseline[:] = [desktop.windows(), desktop.workspaces(), desktop.outputs()]
            selected = (
                spawn_fault
                if argv[3] == "spawn" and len(observed) == 1
                else effect_fault
                if argv[3] != "spawn" and len(observed) == 2
                else None
            )
            if selected is not None and not faults:
                error = (
                    BlockingIOError(errno.EAGAIN, "effect constructor")
                    if selected == "constructor"
                    else subprocess.TimeoutExpired(argv, 10)
                    if selected == "timeout"
                    else subprocess.CalledProcessError(2, argv)
                )
                faults.append(error)
                print(
                    "REACHED real producer/action", argv[3], selected, file=sys.stderr, flush=True
                )
                if selected == "constructor":
                    raise error
                # Real IPC was dispatched; even a late/nonzero client result cannot authorize
                # another action or constructor. Wait itself never performs timeout cleanup.
                client = real_popen(argv, *args, **kwargs)

                class AmbiguousClient:
                    def wait(self, *, timeout):
                        assert client.wait(timeout=timeout) == 0
                        if selected == "timeout":
                            raise error
                        return 2

                    def __getattr__(self, name):
                        raise AssertionError("no ambiguous effect cleanup: " + name)

                return AmbiguousClient()
        if argv[:3] == ["niri", "msg", "--json"] and len(observed) == 2:
            attempts.append(argv[3])
            if argv[3] == query and (failures == "persistent" or len(faults) < failures):
                # Given: earlier placement actually observed, second real exec already proved.
                records = [
                    history.read(p) for p in sorted(history.fence_path(identity).glob("*.json"))
                ]
                payloads = [store.get("receipts", r["receipt"]) for r in records]
                assert len(children) == len(observed) == 2
                assert all(p.poll() is None for p in children)
                first = children[0].pid + 10000
                assert desktop.columns[41] == ([[999], [first]] if protected else [[first]])
                assert desktop.actions == [
                    ("move-window-to-workspace", "--window-id", str(first), "--focus", "false", "1")
                ]
                assert sum(p.get("action") == "bootstrap" for p in payloads) == 2
                assert sum(p.get("action") == "exec" for p in payloads) == 2
                assert (
                    sum(p.get("evidence", {}).get("phase") == "process-observed" for p in payloads)
                    == 2
                )
                fault = BlockingIOError(errno.EAGAIN, "fabricated constructor boundary")
                faults.append(fault)
                print(
                    "REACHED real-dispatch/process-observed/earlier-placement",
                    query,
                    len(faults),
                    file=sys.stderr,
                    flush=True,
                )
                raise fault
            if (
                faults
                and scenario in {"version-persistent", "version-nonzero"}
                and argv[3] == "version"
            ):
                if scenario == "version-persistent":
                    error = BlockingIOError(errno.EAGAIN, "Version constructor")
                    version_faults.append(error)
                    raise error
            if (
                faults
                and scenario in {"version-persistent", "version-nonzero"}
                and argv[3] == "windows"
                and not version_results
            ):
                version_results.append(restore.LiveDesktop().ready())
                assert version_results == [False]
                events.append("actual Version ready(False)")
            if (
                faults
                and scenario
                in {"protected-overlap", "protected-drift", "stale-generation", "pending-exit"}
                and not damage_events
            ):
                damage_events.append(scenario)
                if scenario == "protected-overlap":
                    desktop.windows_by_id[999]["pid"] = children[1].pid
                elif scenario == "protected-drift":
                    desktop.widths[999] += 1.0
                elif scenario == "stale-generation":
                    assert stale["pid"] != children[1].pid
                    desktop.windows_by_id[children[1].pid + 10000]["pid"] = stale["pid"]
                else:
                    quits[1].touch()
                    assert children[1].wait(timeout=35) == 0 and children[0].poll() is None
                events.append("after-constructor-retry-" + scenario)
            if (
                scenario == "protected-drift"
                and damage_events
                and query_stack[-1]["deadline"] is None
            ):
                desktop.widths[999] = (
                    642.0  # Later diagnostic differs; first rejected projection must not rebase.
                )
            if faults and damage is not None and not damage_events:
                mutate = damage
                if mutate == "unowned":
                    desktop.add(9000)
                elif mutate == "surplus":
                    wid = desktop.add(9000)
                    desktop.windows_by_id[wid]["pid"] = children[1].pid
                elif mutate == "exit":
                    quits[1].touch()
                    assert children[1].wait(timeout=35) == 0
                elif mutate == "outputs":
                    desktop.outputs = lambda **kw: [{"name": "DP-1", "logical": {"scale": 9.0}}]
                elif mutate == "malformed":
                    desktop.windows_by_id[children[1].pid + 10000]["id"] = True
                else:
                    raise AssertionError(mutate)
                # Mutation is a single between-attempt event, never a new launch.
                damage_events.append(mutate)
        row = query_stack[-1] if argv[:3] == ["niri", "msg", "--json"] else None
        client = real_popen(argv, *args, **kwargs)
        if scenario == "postcondition-limit" and row is not None and post and len(post) < 4:
            assert (
                row["deadline"] is None
                and row["name"] == ("windows", "workspaces", "outputs")[len(post) - 1]
            )
            offset[0] += 8.0
            post.append(row["name"])
        return NoKillClient(client, row, list(argv[3:]))

    damage_events = []
    stopped = threading.Event()

    @contextmanager
    def retained_path():
        # No automatic fixture-directory deletion: all new evidence survives every outcome.
        yield tempfile.mkdtemp(prefix="query-", dir=os.environ["TMPDIR"])

    with retained_path() as short:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            route = str(Path(short) / "ipc")
            sock.bind(route)
            sock.listen(4)
            sock.settimeout(0.1)
            environment = {
                **os.environ,
                "NIRI_SOCKET": route,
                "WAYLAND_DISPLAY": "fabricated",
                "XDG_RUNTIME_DIR": str(runtime),
                "NDC_TEST_QUIT": str(quit_file),
                "NORMAL_USER_SETTING": "literal",
                "PATH": str(bindir) + os.pathsep + os.defpath,
            }
            with (
                patch.dict(os.environ, environment),
                patch.object(operation_lock, "runtime_root", lambda: runtime),
            ):
                identity = probe.compositor_identity()

                def serve():
                    while not stopped.is_set():
                        try:
                            connection, _ = sock.accept()
                        except TimeoutError:
                            continue
                        with connection:
                            try:
                                args = json.loads(connection.makefile("rb").readline(65537))
                                body = None
                                if args[:2] == ["msg", "--json"]:
                                    name = args[2]
                                    if name == "windows" and len(observed) == 2:
                                        samples[0] += 1
                                    body = {
                                        "windows": desktop.windows,
                                        "workspaces": desktop.workspaces,
                                        "outputs": desktop.outputs,
                                        "version": lambda: "fabricated",
                                    }[name]()
                                    if faults and len(observed) == 2:
                                        count = {
                                            "poll-budget": 2,
                                            "split-1": 1,
                                            "split-3": 3,
                                            "split-4": 4,
                                            "split-reference": 2,
                                            "split-drift": 1,
                                            "split-malformed": 1,
                                        }.get(scenario, 0)
                                        if samples[0] <= count:
                                            if scenario == "poll-budget":
                                                body = deepcopy(
                                                    baseline[
                                                        ("windows", "workspaces", "outputs").index(
                                                            name
                                                        )
                                                    ]
                                                )
                                            elif name == "windows":
                                                body = deepcopy(baseline[0])
                                                if scenario == "split-drift":
                                                    body[0]["layout"]["tile_size"][0] += 1.0
                                                elif scenario == "split-malformed":
                                                    body[0]["workspace_id"] = True
                                            elif (
                                                name == "workspaces"
                                                and scenario == "split-reference"
                                                and samples[0] == 2
                                            ):
                                                body = deepcopy(body)
                                                next(w for w in body if w["is_focused"])[
                                                    "active_window_id"
                                                ] += 1
                                        if (
                                            scenario == "outputs-nonzero" and name == "outputs"
                                        ) or (scenario == "version-nonzero" and name == "version"):
                                            events.append("actual native nonzero-" + name)
                                            connection.sendall(b'{"status":2,"body":null}\n')
                                            continue
                                elif args[:4] == ["msg", "action", "spawn", "--"]:
                                    report = root / ("report-" + str(len(children)))
                                    child_quit = root / ("quit-" + str(len(children)))
                                    quits.append(child_quit)
                                    child = real_popen(
                                        args[4:],
                                        env={
                                            **os.environ,
                                            "NDC_TEST_REPORT": str(report),
                                            "NDC_TEST_QUIT": str(child_quit),
                                        },
                                        stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,
                                        close_fds=True,
                                    )
                                    children.append(child)
                                    desktop.add(child.pid)
                                else:
                                    assert args[:2] == ["msg", "action"]
                                    desktop.action(*args[2:])
                                connection.sendall(
                                    (json.dumps({"status": 0, "body": body}) + "\n").encode()
                                )
                            except BaseException as exc:
                                errors.append(repr(exc))
                                connection.sendall(b'{"status":2,"body":null}\n')

                server = threading.Thread(target=serve)
                server.start()
                try:
                    with (
                        patch.object(Attempt, "observed", observed_record),
                        patch.object(Attempt, "append", appended),
                        patch.object(restore.LiveDesktop, "_query", tracked_query),
                        patch.object(restore.LiveDesktop, "sleep", sleep),
                        patch.object(time, "monotonic", lambda: real_clock() + offset[0]),
                        patch.object(
                            time, "monotonic_ns", lambda: real_ns() + int(offset[0] * 1_000_000_000)
                        ),
                        patch.object(json, "loads", loads),
                        patch.object(subprocess, "Popen", constructor),
                    ):
                        if console is None:
                            result = restore.restore(
                                store,
                                key,
                                restore.LiveDesktop(),
                                apply=True,
                                observe=desktop.observe,
                                spawn_timeout=20,
                            )
                        else:
                            output = io.StringIO()
                            argv = [
                                str(console),
                                "--state-root",
                                str(store.root),
                                "restore",
                                "--apply",
                                key,
                                "--spawn-timeout",
                                "20",
                            ]
                            with (
                                patch.object(probe, "capture", desktop.observe),
                                patch.object(sys, "argv", argv),
                                redirect_stdout(output),
                            ):
                                try:
                                    runpy.run_path(str(console), run_name="__main__")
                                except SystemExit as exit:
                                    code = exit.code
                            result = json.loads(output.getvalue())
                            assert code == (0 if result["status"] == "reopened" else 2)
                    assert not errors, errors
                    assert faults or (scenario == "caller-expiry" and events), (
                        "required fault boundary not reached"
                    )
                    print(
                        "OUTCOME",
                        json.dumps(
                            {
                                "status": result["status"],
                                "effects": result["effects"],
                                "faults": len(faults),
                                "attempts": attempts,
                                "proofs": observed,
                            }
                        ),
                        file=sys.stderr,
                        flush=True,
                    )
                    pids = [c.pid for c in children]
                    for i, pid in enumerate(pids[: len(observed)]):
                        lines = (root / ("report-" + str(i))).read_text().splitlines()
                        assert f"pid={pid}" in lines and f"cwd={root}" in lines
                        assert [v for v in lines if v.startswith("fd=")] == ["fd=0", "fd=1", "fd=2"]
                    if (
                        failures != "persistent"
                        and damage is None
                        and effect_fault is None
                        and spawn_fault is None
                        and scenario
                        in {
                            None,
                            "poll-budget",
                            "split-1",
                            "split-3",
                            "postcondition-limit",
                            "version-persistent",
                            "version-nonzero",
                        }
                    ):
                        assert result["status"] == "reopened", result
                        assert len(faults) == failures
                        first, second = [pid + 10000 for pid in pids]
                        assert result["effects"] == [
                            [
                                "move-window-to-workspace",
                                "--window-id",
                                str(first),
                                "--focus",
                                "false",
                                "1",
                            ],
                            ["focus-window", "--id", str(first)],
                            ["set-column-width", "888"],
                            ["focus-window", "--id", str(second)],
                            ["set-column-width", "888"],
                        ]
                        assert {w["idx"]: desktop.columns[w["id"]] for w in desktop.ws} == {
                            1: [[first]],
                            2: [[second]],
                            3: [],
                        }
                        assert [r["status"] for r in result["windows"]] == ["placed", "placed"]
                        assert store.pointer("last-reopened") == key
                        # Completed replay is historical/native-free, including a different Store.
                        other = Store(root / "other")
                        other.put("snapshots", store.get("snapshots", key))
                        with patch.object(
                            subprocess, "Popen", side_effect=AssertionError("replay IPC")
                        ):
                            replay = restore.restore(
                                other,
                                key,
                                restore.LiveDesktop(),
                                apply=True,
                                observe=lambda: (_ for _ in ()).throw(
                                    AssertionError("replay capture")
                                ),
                            )
                        assert (
                            replay["historical"]
                            and replay["receipt_digest"] == result["receipt_digest"]
                        )
                    else:
                        assert result["status"] == "interrupted", result
                        assert store.pointer("last-reopened") == previous
                        assert len(result["effects"]) == 1
                        assert result["windows"][0]["status"] == "owned-not-placed"
                        assert result["windows"][1]["status"] == (
                            "owned-not-placed"
                            if effect_fault is not None
                            else "launch-indeterminate"
                        )
                        other = Store(root / "other")
                        for source in (key, previous):
                            other.put("snapshots", store.get("snapshots", source))
                        for target in (store, other):
                            for source in (key, previous):
                                with pytest.raises(ValueError, match="unresolved restore"):
                                    restore.restore(
                                        target, source, restore.LiveDesktop(), apply=True
                                    )
                        if failures == "persistent":
                            # Separate unchanged diagnostic read: 3 association + 3 diagnostic,
                            # NOT an illicit 6-attempt retry invocation.
                            assert len(faults) == (6 if query in {"windows", "workspaces"} else 2)
                        elif damage is not None:
                            assert damage_events
                        elif effect_fault is not None:
                            assert sum(a[0] == "focus-window" for a in action_constructions) == 1
                            assert not any(a[0] == "set-column-width" for a in action_constructions)
                        else:
                            assert sum(a[0] == "spawn" for a in action_constructions) == 2
                    records = [
                        history.read(p) for p in sorted(history.fence_path(identity).glob("*.json"))
                    ]
                    payloads = [store.get("receipts", r["receipt"]) for r in records]
                    assert sum(p.get("action") == "bootstrap" for p in payloads) == 2
                    expected_processes = 1 if spawn_fault is not None else 2
                    assert sum(p.get("action") == "exec" for p in payloads) == expected_processes
                    assert len(observed) == expected_processes
                    assert len(children) == (1 if spawn_fault == "constructor" else 2)
                    assert sum(a[0] == "spawn" for a in action_constructions) == 2
                    if effect_fault is not None or spawn_fault is not None:
                        assert records[-1]["type"] == "intent"
                    # Only the second association, after two actual process proofs.
                    association = [
                        r
                        for r in queried
                        if r.get("after_proofs") == 2 and r["deadline"] is not None
                    ]
                    if scenario == "poll-budget":
                        assert [r["name"] for r in association] == [
                            "windows",
                            "workspaces",
                            "outputs",
                        ] * 3
                        assert len({r["deadline"] for r in association}) == 1
                        assert [r["constructions"] for r in association] == [
                            2,
                            1,
                            1,
                            1,
                            1,
                            1,
                            1,
                            1,
                            1,
                        ]
                        assert sleeps == [0.05, 0.05, 0.05]
                    elif scenario == "shared-expiry":
                        assert events == [
                            "charged-windows",
                            "charged-workspaces",
                            "charged-outputs",
                        ]
                        assert len({r["deadline"] for r in association}) == 1
                        assert result["error_type"] == "TimeoutError"
                        assert sum(r["type"] == "association" for r in records) == 1
                    elif scenario == "caller-expiry":
                        assert events == [
                            "actual second Windows reply returned beyond caller deadline"
                        ]
                        assert result["error_type"] == "TimeoutError"
                        assert result["error"] == "bootstrap absolute deadline exceeded or invalid"
                        assert [r["name"] for r in association] == ["windows"]
                        assert [r["constructions"] for r in association] == [1]
                        assert sum(r["type"] == "association" for r in records) == 1
                        assert not any(r["type"] == "terminal" for r in records)
                        assert not faults and not sleeps
                    elif scenario == "persist-expiry":
                        assert events == ["actual second association persisted before expiry"]
                        assert result["error_type"] == "TimeoutError"
                        assert sum(r["type"] == "association" for r in records) == 2
                    elif scenario == "postcondition-limit":
                        assert (
                            post[1:4] == ["windows", "workspaces", "outputs"]
                            and post[4] - post[0] >= 24
                        )
                        assert (
                            result["status"] == "reopened"
                        )  # Explicit unchanged limitation, not a repaired bound.
                    elif scenario in {
                        "split-1",
                        "split-3",
                        "split-4",
                        "split-reference",
                        "split-drift",
                        "split-malformed",
                    }:
                        expected = {
                            "split-1": 2,
                            "split-3": 4,
                            "split-4": 4,
                            "split-reference": 2,
                            "split-drift": 1,
                            "split-malformed": 1,
                        }[scenario]
                        assert sum(r["name"] == "windows" for r in association) == expected
                        assert sum(r["type"] == "association" for r in records) == (
                            2 if scenario in {"split-1", "split-3"} else 1
                        )
                    elif scenario == "protected-drift":
                        rejected = result["first_rejected_observation"]
                        assert (
                            rejected["phase"] == "association"
                            and rejected["schema"] == "restore-protected-dimensions.v1"
                        )
                        assert {(c["field"], tuple(c["delta"])) for c in rejected["changes"]} == {
                            ("tile_size", (1.0, 0.0)),
                            ("window_size", (1.0, 0.0)),
                        }
                        assert next(r for r in rejected["sample"] if r["id"] == 999)[
                            "tile_size"
                        ] == [641.0, 1200.0]
                        assert next(
                            r for r in result["final_observation"]["windows"] if r["id"] == 999
                        )["layout"]["tile_size"] == [642.0, 1200.0]
                        assert (
                            rejected["queries_ns"]["windows"][1]
                            - rejected["queries_ns"]["windows"][0]
                            >= 50_000_000
                        )
                        assert rejected["queries_ns"]["outputs"][1] <= rejected["refusal_check_ns"]
                    elif scenario in {"protected-overlap", "stale-generation", "pending-exit"}:
                        assert damage_events == [scenario] and result["error_type"] == "ValueError"
                        assert sum(r["type"] == "association" for r in records) == 1
                    elif scenario == "outputs-nonzero":
                        assert result["error_type"] == "CalledProcessError"
                        assert events == ["actual native nonzero-outputs"] * 2
                        assert all(
                            r["constructions"] == 1 for r in queried if r["name"] == "outputs"
                        )
                    elif scenario in {"version-persistent", "version-nonzero"}:
                        assert version_results == [False]
                        assert len(version_faults) == (3 if scenario == "version-persistent" else 0)
                        assert [r["constructions"] for r in queried if r["name"] == "version"] == (
                            [3] if version_faults else [1]
                        )
                    (root / "boundary-evidence.json").write_text(
                        json.dumps(
                            {
                                "scenario": scenario,
                                "queries": queried,
                                "communications": communications,
                                "events": events,
                                "postcondition": post,
                                "faults": len(faults),
                                "processes": observed,
                                "actions": action_constructions,
                                "status": result["status"],
                                "effects": result["effects"],
                            }
                        )
                    )
                    return result
                except (KeyboardInterrupt, SystemExit) as raised:
                    assert scenario in {
                        "cancel-communicate",
                        "cancel-sleep",
                        "cancel-decode",
                        "cancel-action",
                    }
                    assert raised is cancel_error and cancelled == [
                        scenario.removeprefix("cancel-")
                    ]
                    assert len(observed) == len(children) == 2 and not errors
                    assert sum(a[0] == "spawn" for a in action_constructions) == 2
                    records = [
                        history.read(p) for p in sorted(history.fence_path(identity).glob("*.json"))
                    ]
                    payloads = [store.get("receipts", r["receipt"]) for r in records]
                    assert not any(r["type"] == "terminal" for r in records)
                    assert sum(p.get("action") == "exec" for p in payloads) == 2
                    assert sum("layout" in p.get("evidence", {}) for p in payloads) == 1
                    assert store.pointer("last-reopened") == previous
                    other = Store(root / "other")
                    for source in (key, previous):
                        other.put("snapshots", store.get("snapshots", source))
                        for target in (store, other):
                            with pytest.raises(ValueError, match="unresolved restore"):
                                restore.restore(target, source, restore.LiveDesktop(), apply=True)
                    assert records[-1]["type"] == (
                        "intent" if scenario == "cancel-action" else "observed"
                    )
                    (root / "cancellation-evidence.json").write_text(
                        json.dumps(
                            {
                                "scenario": scenario,
                                "kind": type(raised).__name__,
                                "processes": observed,
                                "actions": action_constructions,
                                "faults": len(faults),
                                "unwound": True,
                            }
                        )
                    )
                    print(
                        "CANCELLED original exception after actual proof; unresolved fence retained",
                        file=sys.stderr,
                        flush=True,
                    )
                    raise  # The outer explicit raises oracle, not this fixture, decides cancellation success.
                finally:
                    stopped.set()
                    server.join(timeout=25)
                    assert not server.is_alive()
                    # Reviewed cooperative test-fixture completion, never product termination.
                    for marker in quits:
                        marker.touch()
                    for child in children:
                        child.wait(timeout=35)


@pytest.mark.parametrize("failures", [1, 2])
def test_given_real_exec_and_earlier_placement_when_constructor_eagain_then_one_launch_each(
    tmp_path, fabricated_elf, failures
):
    run_boundary(tmp_path, fabricated_elf, failures)


def test_installed_wheel_console_actual_executor_reads_and_ambiguities(tmp_path, fabricated_elf):
    import hashlib
    import inspect
    import zipfile

    from test_reopen import IDENTITY
    from test_restore_cli_grammar import niri_change
    from test_restore_integration import Topology

    root = Path(__file__).resolve().parents[1]
    runtime = root / "src" / "niri_desktop_continuity"
    expected = {
        str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in runtime.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }

    def tool(*args):
        result = subprocess.run(
            args, cwd=root, capture_output=True, text=True, env={**os.environ, "UV_OFFLINE": "1"}
        )
        assert result.returncode == 0, result.stdout + result.stderr

    tool("uv", "build", "--wheel", "--out-dir", str(tmp_path / "dist"))
    tool("uv", "venv", "--python", sys.executable, str(tmp_path / "venv"))
    python = tmp_path / "venv" / "bin" / "python"
    wheel = next((tmp_path / "dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        actual = {
            name.removeprefix("niri_desktop_continuity/"): hashlib.sha256(
                archive.read(name)
            ).hexdigest()
            for name in archive.namelist()
            if name.startswith("niri_desktop_continuity/") and not name.endswith("/")
        }
    assert actual == expected
    tool("uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel))
    tool("uv", "pip", "install", "--python", str(python), "pytest==9.1.1")
    # Copy only fully read handwritten fixture definitions, never the checkout's sys.path setup.
    fixture = tmp_path / "fixture.py"
    fixture.write_text(
        "import errno, io, json, os, re, runpy, socket, subprocess, sys, tempfile, threading, time\n"
        "from contextlib import contextmanager, redirect_stdout\nfrom copy import deepcopy\n"
        "from pathlib import Path\nfrom unittest.mock import patch\nimport pytest\n"
        "from niri_desktop_continuity import operation_lock, probe, restore\n"
        "from niri_desktop_continuity import restore_history as history\n"
        "from niri_desktop_continuity.restore_attempt import Attempt\n"
        "from niri_desktop_continuity.store import Store\n"
        "from niri_desktop_continuity.model import normalized_snapshot\n"
        + f"IDENTITY = {IDENTITY!r}\n"
        + "\n".join(
            inspect.getsource(v) for v in (niri_change, window, saved, Topology, Niri, run_boundary)
        )
    )
    members = tmp_path / "members.json"
    members.write_text(json.dumps(expected))
    runner = tmp_path / "driver.py"
    runner.write_text(r"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import fixture
import niri_desktop_continuity
from niri_desktop_continuity import restore_execute, restore_producer, restore_bootstrap
package = Path(niri_desktop_continuity.__file__).parent
assert package.is_relative_to(Path(sys.prefix))
expected = json.loads(Path(sys.argv[2]).read_text())
actual = {str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in package.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual == expected
for module in (fixture.restore, restore_execute, restore_producer, restore_bootstrap):
    assert Path(module.__file__).is_relative_to(package), module.__file__
console = Path(sys.executable).parent / 'niri-desktop-continuity'
cases = [{'failures': 1}, {'failures': 2},
         {'failures': 'persistent'}, {'failures': 'persistent', 'query': 'workspaces'},
         {'failures': 'persistent', 'query': 'outputs'},
         *[{'failures': 0, 'effect_fault': fault} for fault in ('constructor', 'timeout', 'nonzero')],
         *[{'failures': 0, 'spawn_fault': fault} for fault in ('constructor', 'timeout', 'nonzero')]]
for i, case in enumerate(cases):
    root = Path(__file__).parent / ('case-' + str(i))
    root.mkdir(mode=0o700)
    fixture.run_boundary(root, Path(sys.argv[1]), console=console, **case)
for name, module in list(sys.modules.items()):
    if name.startswith('niri_desktop_continuity') and hasattr(module, '__file__'):
        assert Path(module.__file__).is_relative_to(package), (name, module.__file__)
print(json.dumps({'cases': len(cases), 'origin': str(package), 'members': len(actual), 'native': False}))
""")
    environment = {
        k: v
        for k, v in os.environ.items()
        if k not in {"NIRI_SOCKET", "WAYLAND_SOCKET", "WAYLAND_DISPLAY", "DISPLAY", "PYTHONPATH"}
    }
    result = subprocess.run(
        [str(python), "-B", str(runner), str(fabricated_elf), str(members)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    outcome = json.loads(result.stdout)
    assert outcome["cases"] == 11 and outcome["members"] == len(expected)
    assert not outcome["native"]
    print("INSTALLED", result.stdout, result.stderr, flush=True)
