"""Handwritten whole/split observations; no production topology predictors."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_restore_handshake import fabricated_elf as fabricated_elf  # noqa: F401
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import restore_host, restore_layout


def sample(mapped=False):
    # Given baseline columns [[10], [20]], focused 10; host PID 303 is distinct.
    ids = [10, 30, 20] if mapped else [10, 20]
    return {
        "windows": [
            {
                "id": wid,
                "pid": 303 if wid == 30 else wid + 100,
                "workspace_id": 1,
                "is_focused": wid == (30 if mapped else 10),
                "is_floating": False,
                "layout": {
                    "pos_in_scrolling_layout": [col, 1],
                    "tile_size": [800, 600],
                    "window_size": [788, 588],
                    "tile_pos_in_workspace_view": None,
                },
            }
            for col, wid in enumerate(ids, 1)
        ],
        "workspaces": [
            {
                "id": 1,
                "idx": 1,
                "output": "DP-1",
                "name": None,
                "is_focused": True,
                "is_active": True,
                "active_window_id": 30 if mapped else 10,
            }
        ],
        "outputs": [{"name": "DP-1", "logical": {"scale": 1.0}}],
    }


class Schedule:
    def __init__(self, samples, clock):
        self.samples, self.clock, self.count = samples, clock, 0
        self.current = sample()
        self.slow = False

    def windows(self, *, deadline=None):
        if self.samples:
            self.current = deepcopy(self.samples.pop(0))
        self.count += 1
        if self.slow:
            self.clock[0] += 2
        return deepcopy(self.current["windows"])

    def workspaces(self, *, deadline=None):
        return deepcopy(self.current["workspaces"])

    def outputs(self, *, deadline=None):
        return deepcopy(self.current["outputs"])

    def sleep(self, seconds):
        self.clock[0] += seconds

    def monotonic(self):
        return self.clock[0]


def setup(monkeypatch, samples):
    clock = [10.0]
    monkeypatch.setattr(restore_layout.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(restore_host, "route", lambda identity: None)
    records, deadlines = [], []
    attempt = SimpleNamespace(
        identity={}, check=lambda: None, append=lambda *args: records.append(deepcopy(args))
    )
    desktop = Schedule([sample(), *samples], clock)
    layout = restore_layout.Layout(attempt, desktop, sample(), 1)
    proof = SimpleNamespace(
        process=SimpleNamespace(pin={"pid": 303}),
        validate=lambda **kw: deadlines.append(kw["deadline"]),
    )
    return layout, desktop, proof, records, clock, deadlines


def split():
    value = sample()
    # When windows replied before map30 and workspaces replied after it.
    value["workspaces"][0]["active_window_id"] = 30
    return value


def test_given_split_mapping_when_next_whole_then_associate_exactly_once(monkeypatch):
    layout, desktop, proof, records, _, _ = setup(monkeypatch, [split(), sample(True)])
    assert layout.associate(proof, 0) == 30
    assert desktop.count == 3
    assert len(records) == 1 and records[0][0] == "association"
    after = records[0][1]["after"]
    assert [
        w["id"]
        for w in sorted(after["windows"], key=lambda w: w["layout"]["pos_in_scrolling_layout"])
    ] == [10, 30, 20]
    assert after["workspaces"][0]["active_window_id"] == 30
    assert all(w["layout"]["tile_size"] == [800, 600] for w in after["windows"])


@pytest.mark.parametrize("step", ["query", "proof"])
def test_given_matching_whole_when_deadline_overrun_then_no_association(monkeypatch, step):
    layout, desktop, proof, records, clock, _ = setup(monkeypatch, [sample(True)])
    if step == "query":
        desktop.slow = True
    else:
        proof.validate = lambda **kw: clock.__setitem__(0, 12.0)
    with pytest.raises(TimeoutError):
        layout.associate(proof, 0)
    assert records == [] and layout.owned == {}


@pytest.mark.parametrize("count", [1, 2, 3])
def test_fixed_allowance_keeps_original_before_and_one_deadline(monkeypatch, count):
    layout, _, proof, records, _, deadlines = setup(monkeypatch, [split()] * count + [sample(True)])
    original = deepcopy(layout.state)
    assert layout.associate(proof, 0) == 30
    assert len(records) == 1
    assert [w["id"] for w in records[0][1]["before"]["windows"]] == [10, 20]
    assert original[0][10]["is_focused"] and original[1][0]["active_window_id"] == 10
    assert deadlines and set(deadlines) == {11.0}


@pytest.mark.parametrize(
    "failure",
    [
        "fourth",
        "disappear",
        "change",
        "foreign-pid",
        "ref-reverted",
        "unowned",
        "size",
        "identity",
        "topology",
        "extra-owned",
        "extra-output",
        "scale",
        "focus",
        "workspace",
    ],
)
def test_observed_adverse_evidence_is_fatal_even_if_next_sample_recovers(monkeypatch, failure):
    bad = sample(True)
    prefix = [split()]
    if failure == "fourth":
        prefix, bad = [split()] * 3, split()
    elif failure == "disappear":
        bad = sample()
    elif failure == "change":
        bad = split()
        bad["workspaces"][0]["active_window_id"] = 31
    elif failure == "foreign-pid":
        bad["windows"][1]["pid"] = 999
    elif failure == "ref-reverted":
        bad["windows"][0]["is_focused"] = True
        bad["windows"][1]["is_focused"] = False
        bad["workspaces"][0]["active_window_id"] = 10
    elif failure in {"unowned", "extra-owned"}:
        extra = deepcopy(bad["windows"][1])
        extra.update(id=40, pid=999 if failure == "unowned" else 303, is_focused=False)
        extra["layout"]["pos_in_scrolling_layout"] = [4, 1]
        bad["windows"].append(extra)
    elif failure == "size":
        bad["windows"][0]["layout"]["tile_size"][1] += 1
    elif failure == "identity":
        bad["windows"][0]["pid"] += 1
    elif failure == "topology":
        bad["windows"][0]["layout"]["pos_in_scrolling_layout"] = [3, 1]
        bad["windows"][2]["layout"]["pos_in_scrolling_layout"] = [1, 1]
    elif failure == "extra-output":
        bad["outputs"].append({"name": "DP-2", "logical": {"scale": 1}})
    elif failure == "scale":
        bad["outputs"][0]["logical"]["scale"] = 2
    elif failure == "focus":
        bad["windows"][1]["is_focused"] = False
        bad["windows"][2]["is_focused"] = True
        bad["workspaces"][0]["active_window_id"] = 20
    else:
        bad["workspaces"][0]["name"] = "changed"
    layout, desktop, proof, records, _, _ = setup(monkeypatch, [*prefix, bad, sample(True)])
    with pytest.raises(ValueError):
        layout.associate(proof, 0)
    assert desktop.samples == [sample(True)]  # recovery never erases observed evidence
    assert not records and not layout.owned
    assert layout.state[1][0]["active_window_id"] == 10


@pytest.mark.parametrize(
    "damage",
    [
        "bool",
        "string",
        "negative",
        "known-foreign",
        "two-missing",
        "later-scale",
        "later-size",
        "later-workspace",
        "height-only",
        "view-position",
        "lifecycle",
        "reindex",
        "pid",
        "duplicate",
        "invalid-layout",
        "invalid-window-flag",
        "invalid-workspace-flag",
    ],
)
def test_combined_missing_ref_never_masks_independent_defects(monkeypatch, damage):
    bad = split()
    if damage in {"bool", "string", "negative"}:
        bad["workspaces"][0]["active_window_id"] = {"bool": True, "string": "30", "negative": -1}[
            damage
        ]
    elif damage in {"known-foreign", "two-missing", "later-workspace", "lifecycle", "reindex"}:
        bad["workspaces"].append(
            {
                "id": 2,
                "idx": 2,
                "output": "DP-1",
                "name": None,
                "is_active": False,
                "is_focused": False,
                "active_window_id": None,
            }
        )
        if damage == "known-foreign":
            bad["workspaces"][1]["active_window_id"] = 10
        elif damage == "two-missing":
            bad["workspaces"][1]["active_window_id"] = 31
        elif damage == "later-workspace":
            bad["workspaces"][1]["idx"] = "invalid"
        elif damage == "reindex":
            bad["workspaces"][0]["idx"], bad["workspaces"][1]["idx"] = 2, 1
    elif damage == "later-scale":
        bad["outputs"].append({"name": "DP-2", "logical": {"scale": True}})
    elif damage in {"later-size", "height-only"}:
        bad["windows"][1]["layout"]["tile_size"][1] = -1 if damage == "later-size" else 601
    elif damage == "view-position":
        bad["windows"][1]["layout"]["tile_pos_in_workspace_view"] = [2, 3]
    elif damage == "pid":
        bad["windows"][1]["pid"] += 1
    elif damage == "duplicate":
        bad["windows"].append(deepcopy(bad["windows"][0]))
    elif damage == "invalid-layout":
        bad["windows"][1]["layout"]["pos_in_scrolling_layout"] = [8, 1]
    elif damage == "invalid-window-flag":
        bad["windows"][1]["is_focused"] = 0
    else:
        bad["workspaces"][0]["is_active"] = 1
    layout, desktop, proof, records, _, _ = setup(monkeypatch, [bad, sample(True)])
    with pytest.raises((ValueError, TypeError)):
        layout.associate(proof, 0)
    assert desktop.count == 2 and not records


@pytest.mark.parametrize("step", ["attempt", "route", "owned-proof", "sleep", "append"])
def test_absolute_deadline_covers_all_steps_and_retains_late_append(monkeypatch, step):
    layout, desktop, proof, records, clock, _ = setup(monkeypatch, [split(), sample(True)])

    def expire(*args, **kwargs):
        clock[0] = 12.0

    if step == "attempt":
        layout.attempt.check = expire
    elif step == "route":
        monkeypatch.setattr(restore_host, "route", expire)
    elif step == "owned-proof":
        layout.owned[10] = SimpleNamespace(
            process=SimpleNamespace(pin={"pid": 110}), validate=expire
        )
    elif step == "sleep":
        desktop.sleep = expire
    else:
        append = layout.attempt.append

        def late(*args):
            append(*args)
            expire()

        layout.attempt.append = late
    with pytest.raises(TimeoutError):
        layout.associate(proof, 0)
    assert len(records) == (1 if step == "append" else 0)
    assert 30 not in layout.owned and layout.state[1][0]["active_window_id"] == 10


def test_pending_and_previously_owned_proofs_share_nonrenewed_deadline(monkeypatch):
    layout, _, proof, records, _, deadlines = setup(monkeypatch, [split(), split(), sample(True)])
    layout.owned[10] = SimpleNamespace(
        process=SimpleNamespace(pin={"pid": 110}),
        validate=lambda **kw: deadlines.append(kw["deadline"]),
    )
    assert layout.associate(proof, 0) == 30
    assert set(deadlines) == {11.0} and len(records) == 1


@pytest.mark.parametrize("caller", ["read", "fresh", "initial", "decode"])
def test_other_callers_remain_strict(monkeypatch, caller):
    from niri_desktop_continuity import restore_state

    layout, desktop, _, records, _, _ = setup(monkeypatch, [split()])
    with pytest.raises(ValueError, match="active"):
        if caller == "read":
            layout.read()
        elif caller == "fresh":
            layout.fresh()
        elif caller == "initial":
            restore_layout.Layout(layout.attempt, desktop, sample(), 1)
        else:
            value = split()
            value["outputs"] = [{"name": "DP-1", "scale": 1}]
            restore_state.decode(value)
    assert not records


@pytest.mark.parametrize("failure", [ValueError, OSError, TimeoutError])
def test_transport_failure_is_not_resampled(monkeypatch, failure):
    layout, desktop, proof, records, _, _ = setup(monkeypatch, [split(), sample(True)])

    def fail(*args, **kwargs):
        raise failure("fabricated query failure")

    desktop.workspaces = fail
    with pytest.raises(failure):
        layout.associate(proof, 0)
    assert desktop.count == 2 and not records


def test_pending_deadline_exhaustion_does_not_renew(monkeypatch):
    layout, desktop, proof, records, clock, _ = setup(monkeypatch, [split()] * 3 + [sample(True)])
    desktop.sleep = lambda seconds: clock.__setitem__(0, clock[0] + 0.6)
    with pytest.raises(TimeoutError):
        layout.associate(proof, 0)
    assert desktop.count == 3 and not records


def test_each_query_receives_same_absolute_deadline(monkeypatch):
    layout, desktop, proof, _, clock, _ = setup(monkeypatch, [sample(True)])
    deadlines = []
    for name in ("windows", "workspaces", "outputs"):
        original = getattr(desktop, name)

        def query(*, deadline=None, original=original):
            deadlines.append(deadline)
            clock[0] += 0.1
            return original(deadline=deadline)

        setattr(desktop, name, query)
    assert layout.associate(proof, 0) == 30
    assert deadlines == [11.0, 11.0, 11.0]


def test_whole_sample_continues_one_launch_to_layout_and_normal_history(integrated, monkeypatch):
    from niri_desktop_continuity import restore_history as history

    s = integrated
    d = s.desktop
    d.columns = {1: [[10], [20]], 2: []}
    d.windows_by_id = {10: {"id": 10, "pid": 110}, 20: {"id": 20, "pid": 120}}
    d.widths, d.focus = {10: 640.0, 20: 720.0}, 10
    d.initialize()
    queued, queries = [], []
    monkeypatch.setattr(d, "add", lambda pid: queued.append(pid))
    windows = d.windows

    def split_windows(*, deadline=None):
        result = windows(deadline=deadline)
        if queued:
            assert not d.actions
            records = [
                history.read(p) for p in sorted(history.fence_path(s.identity).glob("*.json"))
            ]
            assert [r["type"] for r in records] == [
                "prepared",
                "intent",
                "observed",
                "intent",
                "observed",
            ]
            # Map between windows and workspaces, AFTER observed host exec.
            pid = queued.pop()
            d.columns[1] = [[10], [30], [20]]
            d.windows_by_id[30] = {"id": 30, "pid": pid}
            d.widths[30], d.previous[30] = 800.0, 10
            d.active[1] = d.focus = 30
            queries.append("split")
        elif queries and not d.actions:
            queries.append("whole")
        return result

    monkeypatch.setattr(d, "windows", split_windows)
    key, result = s.run([s.entry(1, 1)])
    assert result["status"] == "reopened", result
    assert len(s.proofs) == 1 and queries[:2] == ["split", "whole"]
    assert d.columns == {1: [[10], [20], [30]], 2: []}
    assert d.widths == {10: 640.0, 20: 720.0, 30: 900.0} and d.focus == 10
    final = {w["id"]: w for w in result["final_observation"]["windows"]}
    assert [final[i]["layout"]["tile_size"] for i in (10, 20, 30)] == [
        [640, 1200],
        [720, 1200],
        [900, 1200],
    ]
    assert [final[i]["layout"]["window_size"] for i in (10, 20, 30)] == [
        [628, 1188],
        [708, 1188],
        [888, 1188],
    ]
    assert d.actions == [
        ("move-column-to-index", "3"),
        ("set-column-width", "888"),
        ("focus-window", "--id", "10"),
    ]
    records = [history.read(p) for p in sorted(history.fence_path(s.identity).glob("*.json"))]
    payloads = [s.store.get("receipts", r["receipt"]) for r in records]
    assert sum(p.get("action") == "bootstrap" for p in payloads) == 1
    assert sum(p.get("action") == "exec" for p in payloads) == 1
    associations = [p for r, p in zip(records, payloads, strict=True) if r["type"] == "association"]
    assert len(associations) == 1
    assert associations[0]["after"]["workspaces"][0]["active_window_id"] == 30
    assert len(associations[0]["after"]["windows"]) == 3
    assert s.store.pointer("last-reopened") == key
    history.require_clear(s.identity)  # unchanged strict semantic history accepts the whole record


@pytest.mark.parametrize("step", ["windows", "workspaces", "outputs"])
def test_expiry_after_each_query_prevents_later_queries(monkeypatch, step):
    layout, desktop, proof, records, clock, _ = setup(monkeypatch, [sample(True)])
    original = getattr(desktop, step)

    def overdue(*, deadline=None):
        value = original(deadline=deadline)
        clock[0] = 12
        return value

    setattr(desktop, step, overdue)
    with pytest.raises(TimeoutError):
        layout.associate(proof, 0)
    assert not records


def test_complete_structure_is_validated_before_relational_classification():
    from niri_desktop_continuity import restore_observation, restore_state

    value = split()
    value["outputs"] = [{"name": "DP-1", "scale": True}]
    with pytest.raises(ValueError, match="scale"):
        restore_state.decode(value)
    before = sample()
    before["outputs"] = [{"name": "DP-1", "scale": 1}]
    with pytest.raises(ValueError, match="scale"):
        restore_observation.pending_reference(value, restore_state.decode(before))


# Installed code only in the child; no test_reopen import can inject checkout src.
WHEEL_DRIVER = r"""
import json, os, runpy, socket, subprocess, sys, tempfile
from pathlib import Path
from restore_fixture import Niri, saved, window
from niri_desktop_continuity import operation_lock, probe, restore, restore_producer
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.store import Store
import niri_desktop_continuity
assert Path(niri_desktop_continuity.__file__).is_relative_to(Path(sys.prefix))
root, elf = Path(sys.argv[1]), sys.argv[2]
runtime = root / 'runtime'
runtime.mkdir(mode=0o700)
operation_lock.runtime_root = lambda: runtime
d = Niri()
d.columns = {1: [[10], [20]], 2: []}
d.windows_by_id = {10: {'id': 10, 'pid': 110}, 20: {'id': 20, 'pid': 120}}
d.widths, d.focus = {10: 640., 20: 720.}, 10
d.initialize()
outputs = d.outputs
def inventory(*, deadline=None):
    return outputs(deadline=deadline) + [{'name': 'DP-DISABLED', 'logical': None,
                                         'make': 'Fabricated'}]
d.outputs = inventory
restore.LiveDesktop = lambda: d
probe.capture = d.observe
store = Store(root / 'state')
key = store.put('snapshots', saved([window(1, 1, 1, reopen={
    'kind': 'command', 'argv': [elf, '-e', 'tool', 'literal'], 'cwd': str(root)
})]))
children, pending, schedule = [], [], []
quit = root / 'quit'
report = root / 'host-report'
windows = d.windows
def sampled_windows(*, deadline=None):
    value = windows(deadline=deadline)
    if pending:
        records = [history.read(p) for p in sorted(history.fence_path(probe.compositor_identity()).glob('*.json'))]
        assert [r['type'] for r in records] == ['prepared', 'intent', 'observed', 'intent', 'observed']
        assert not d.actions
        pid = pending.pop()
        d.columns[1] = [[10], [30], [20]]
        d.windows_by_id[30] = {'id': 30, 'pid': pid}
        d.widths[30], d.previous[30] = 800., 10
        d.active[1] = d.focus = 30
        schedule.append('split')
    elif schedule and not d.actions:
        schedule.append('whole')
    return value
d.windows = sampled_windows
with tempfile.TemporaryDirectory(prefix='coh-', dir=os.environ['TMPDIR']) as short:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        route = str(Path(short) / 'sock')
        sock.bind(route)  # fabricated route only, no native compositor
        os.environ.update(NIRI_SOCKET=route, WAYLAND_DISPLAY='fabricated',
                          XDG_RUNTIME_DIR=str(runtime), NDC_TEST_QUIT=str(quit),
                          NDC_TEST_REPORT=str(report), NORMAL_USER_SETTING='literal')
        def dispatch(argv, identity, deadline):
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, close_fds=True)
            children.append(child)
            pending.append(child.pid)
        restore_producer.niri_spawn = dispatch
        console = str(Path(sys.executable).parent / 'niri-desktop-continuity')
        sys.argv = [console, '--state-root', str(store.root), 'restore', '--apply', key,
                    '--spawn-timeout', '10']
        try:
            try: runpy.run_path(console, run_name='__main__')
            except SystemExit as exc: assert exc.code == 0
            assert len(children) == 1 and schedule[:2] == ['split', 'whole']
            assert d.columns == {1: [[10], [20], [30]], 2: []}
            assert d.widths == {10: 640., 20: 720., 30: 900.} and d.focus == 10
            assert d.actions == [('move-column-to-index', '3'), ('set-column-width', '888'),
                                 ('focus-window', '--id', '10')]
            observed = {w['id']: w for w in d.windows()}
            assert [observed[i]['layout']['tile_size'] for i in (10, 20, 30)] == [
                [640., 1200.], [720., 1200.], [900., 1200.]]
            assert [observed[i]['layout']['window_size'] for i in (10, 20, 30)] == [
                [628., 1188.], [708., 1188.], [888., 1188.]]
            records = [history.read(p) for p in sorted(history.fence_path(probe.compositor_identity()).glob('*.json'))]
            payloads = [store.get('receipts', r['receipt']) for r in records]
            assert sum(p.get('action') == 'bootstrap' for p in payloads) == 1
            assert sum(p.get('action') == 'exec' for p in payloads) == 1
            associations = [p for r, p in zip(records, payloads) if r['type'] == 'association']
            assert len(associations) == 1 and len(associations[0]['after']['windows']) == 3
            assert associations[0]['after']['workspaces'][0]['active_window_id'] == 30
            history.require_clear(probe.compositor_identity())
            assert store.pointer('last-reopened') == key
            lines = report.read_text().splitlines()
            assert [v for v in lines if v.startswith('fd=')] == ['fd=0', 'fd=1', 'fd=2']
            assert 'cwd=' + str(root) in lines
            assert children[0].poll() is None
        finally:
            quit.touch()  # cooperative fabricated ELF exit, never kill/terminate
            for child in children: child.wait(timeout=35)
"""


def test_installed_wheel_split_single_real_exec_and_complete_layout(tmp_path, fabricated_elf):
    import inspect
    import os
    import subprocess
    import sys
    from pathlib import Path

    from test_reopen import IDENTITY, saved, window
    from test_restore_cli_grammar import niri_change
    from test_restore_integration import Topology
    from test_restore_lifecycle import Niri

    fixture = tmp_path / "restore_fixture.py"
    fixture.write_text(
        "import re\nfrom copy import deepcopy\nfrom niri_desktop_continuity import restore\n"
        "from niri_desktop_continuity.model import normalized_snapshot\n"
        + f"IDENTITY = {IDENTITY!r}\n"
        + "\n".join(inspect.getsource(v) for v in (niri_change, window, saved, Topology, Niri))
    )
    root = Path(__file__).resolve().parents[1]

    def tool(*args):
        result = subprocess.run(
            args, cwd=root, capture_output=True, text=True, env={**os.environ, "UV_OFFLINE": "1"}
        )
        assert result.returncode == 0, result.stderr

    tool("uv", "build", "--wheel", "--out-dir", str(tmp_path / "dist"))
    tool("uv", "venv", "--python", sys.executable, str(tmp_path / "venv"))
    python = tmp_path / "venv" / "bin" / "python"
    tool(
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--no-deps",
        str(next((tmp_path / "dist").glob("*.whl"))),
    )
    driver = tmp_path / "driver.py"
    driver.write_text(WHEEL_DRIVER)
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"NIRI_SOCKET", "WAYLAND_SOCKET", "DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH"}
    }
    env.update(
        HOME=str(tmp_path),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        XDG_STATE_HOME=str(tmp_path / "state-home"),
    )
    result = subprocess.run(
        [str(python), str(driver), str(tmp_path), str(fabricated_elf)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=70,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    import json

    assert json.loads(result.stdout)["status"] == "reopened"


def test_late_durable_association_stays_fenced_without_layout_or_second_launch(
    integrated, monkeypatch
):
    from niri_desktop_continuity import restore, restore_history
    from niri_desktop_continuity.restore_attempt import Attempt

    s = integrated
    clock = [10.0]
    monkeypatch.setattr(restore_layout.time, "monotonic", lambda: clock[0])
    append = Attempt.append

    def slow(self, kind, payload):
        result = append(self, kind, payload)
        if kind == "association":
            clock[0] = 12.0
        return result

    monkeypatch.setattr(Attempt, "append", slow)
    key, result = s.run([s.entry(1, 1), s.entry(2, 2)])
    assert result["status"] == "interrupted" and result["error_type"] == "TimeoutError"
    assert result["effects"] == [] and not s.desktop.actions and len(s.proofs) == 1
    records = [
        restore_history.read(p)
        for p in sorted(restore_history.fence_path(s.identity).glob("*.json"))
    ]
    assert sum(r["type"] == "association" for r in records) == 1
    assert records[-1]["type"] == "association"
    with pytest.raises(ValueError, match="unresolved restore"):
        restore.restore(s.store, key, s.desktop, apply=True)
    assert len(s.proofs) == 1 and s.store.pointer("last-reopened") is None


def test_expiry_during_association_payload_build_prevents_append(monkeypatch):
    from niri_desktop_continuity import restore_geometry, restore_state

    layout, _, proof, records, clock, _ = setup(monkeypatch, [sample(True)])
    associate, record = restore_geometry.associate, restore_state.record

    def validated(*args):
        result = associate(*args)

        def slow(state):
            value = record(state)
            clock[0] = 12.0
            return value

        monkeypatch.setattr(restore_state, "record", slow)
        return result

    monkeypatch.setattr(restore_geometry, "associate", validated)
    with pytest.raises(TimeoutError):
        layout.associate(proof, 0)
    assert not records


@pytest.mark.parametrize("split_first", [False, True])
def test_unchanged_disabled_output_without_workspace_allows_owned_arrival(monkeypatch, split_first):
    initial = sample()
    initial["outputs"].append({"name": "DP-DISABLED", "logical": None, "make": "Fabricated"})
    values = [split(), sample(True)] if split_first else [sample(True)]
    for value in values:
        value["outputs"] = deepcopy(initial["outputs"])
    layout, desktop, proof, records, _, _ = setup(monkeypatch, [])
    desktop.samples = [initial, *values]
    layout = restore_layout.Layout(layout.attempt, desktop, initial, 1)
    assert layout.associate(proof, 0) == 30
    assert len(records) == 1 and not desktop.samples
    assert records[0][1]["before"]["outputs"] == [{"name": "DP-1", "scale": 1.0}]
    assert records[0][1]["after"]["outputs"] == [{"name": "DP-1", "scale": 1.0}]


@pytest.mark.parametrize("workspace_id", [True, 1.0])
def test_strict_window_workspace_id_rejects_numeric_aliases(workspace_id):
    from niri_desktop_continuity import restore_state

    value = sample()
    value["outputs"] = [{"name": "DP-1", "scale": 1.0}]
    value["windows"][0]["workspace_id"] = workspace_id
    with pytest.raises(ValueError, match="workspace/process"):
        restore_state.decode(value)


@pytest.mark.parametrize("damage", ["new", "removed", "make", "enabled", "scale", "malformed"])
def test_disabled_output_inventory_drift_is_fatal_and_never_rebased(monkeypatch, damage):
    initial = sample()
    initial["outputs"].append({"name": "DP-DISABLED", "logical": None, "make": "Fabricated"})
    first, bad, whole = split(), split(), sample(True)
    for value in (first, bad, whole):
        value["outputs"] = deepcopy(initial["outputs"])
    if damage == "new":
        bad["outputs"].append({"name": "DP-NEW", "logical": None})
    elif damage == "removed":
        bad["outputs"].pop()
    elif damage == "make":
        bad["outputs"][1]["make"] = "Changed"
    elif damage == "enabled":
        bad["outputs"][1]["logical"] = {"scale": 1}
    elif damage == "scale":
        bad["outputs"][0]["logical"]["scale"] = 2
    else:
        bad["outputs"][1]["logical"] = {"scale": True}
    layout, desktop, proof, records, _, _ = setup(monkeypatch, [])
    desktop.samples = [initial, first, bad, whole]
    layout = restore_layout.Layout(layout.attempt, desktop, initial, 1)
    frozen = deepcopy(layout.output_inventory)
    with pytest.raises(ValueError):
        layout.associate(proof, 0)
    assert desktop.samples == [whole] and not records and not layout.owned
    assert layout.output_inventory == frozen


def test_inventory_freezes_before_launch_ignoring_only_outer_and_object_order(monkeypatch):
    initial, whole = sample(), sample(True)
    initial["outputs"].append({"name": "DP-DISABLED", "logical": None, "make": "Fabricated"})
    whole["outputs"] = {
        "DP-DISABLED": {"make": "Fabricated", "logical": None, "name": "DP-DISABLED"},
        "DP-1": {"logical": {"scale": 1.0}, "name": "DP-1"},
    }
    layout, desktop, proof, records, _, _ = setup(monkeypatch, [])
    desktop.samples = [initial, whole]
    layout = restore_layout.Layout(layout.attempt, desktop, initial, 1)
    # Neither the input buffer nor caller's capture is the frozen owner.
    initial["outputs"][1]["make"] = "Changed after initial read"
    assert layout.associate(proof, 0) == 30 and len(records) == 1


@pytest.mark.parametrize(
    "metadata",
    [
        {"logical": {"scale": -1}},
        {"logical": {"height": True}},
        {"make": []},
        {"vrr_enabled": 1},
        {"physical_size": [True, 100]},
        {"modes": {}},
        {"modes": [{"width": 800, "height": 600, "refresh_rate": True}]},
        {"current_mode": True},
        {"modes": [], "current_mode": 0},
        {"logical": {"transform": False}},
        {"extra": float("nan")},
    ],
)
def test_malformed_disabled_inventory_refuses_before_launch(monkeypatch, metadata):
    initial = sample()
    initial["outputs"].append({"name": "DP-DISABLED", "logical": None, **metadata})
    layout, desktop, _, records, _, _ = setup(monkeypatch, [])
    desktop.samples = [initial]
    with pytest.raises(ValueError):
        restore_layout.Layout(layout.attempt, desktop, initial, 1)
    assert not records


def test_output_metadata_numeric_equality_does_not_alias_boolean():
    from niri_desktop_continuity import restore_observation as observation

    initial = [{"name": "DP-1", "logical": {"scale": 1.0}, "extra": True}]
    frozen = observation.output_inventory(initial)
    observation.check_outputs([{"name": "DP-1", "logical": {"scale": 1}, "extra": True}], frozen)
    with pytest.raises(ValueError, match="outputs changed"):
        observation.check_outputs([{"name": "DP-1", "logical": {"scale": 1}, "extra": 1}], frozen)


@pytest.mark.parametrize("phase", ["initial", "prelaunch"])
@pytest.mark.parametrize("damage", ["manufacturer", "malformed-vrr", "added-disabled"])
def test_prelaunch_or_initial_inventory_drift_never_launches_or_reads_recovery(
    integrated, monkeypatch, phase, damage
):
    from niri_desktop_continuity import restore_history as history

    s = integrated
    baseline = [
        {"name": "DP-1", "logical": {"scale": 8.0}},
        {"name": "DP-DISABLED", "logical": None, "make": "Fabricated"},
    ]
    bad = deepcopy(baseline)
    if damage == "manufacturer":
        bad[1]["make"] = "Changed"
    elif damage == "malformed-vrr":
        bad[1]["vrr_enabled"] = 1
    else:
        bad.append({"name": "DP-ADDED", "logical": None})
    # capture -> constructor -> prelaunch fresh; recovery must remain unconsumed.
    replies = [baseline, *([baseline] if phase == "prelaunch" else []), bad, baseline]

    def outputs(*, deadline=None):
        assert replies, "unexpected output resampling"
        return deepcopy(replies.pop(0))

    monkeypatch.setattr(s.desktop, "outputs", outputs)
    _, result = s.run([s.entry(1, 1)])
    assert result["status"] == "interrupted"
    assert not s.proofs and not s.desktop.actions and not result["effects"]
    records = [history.read(p) for p in sorted(history.fence_path(s.identity).glob("*.json"))]
    assert [r["type"] for r in records] == ["prepared"]  # no launch/exec permit/association
    assert replies == [baseline]
    assert result["final_observation"] in ({}, {"unavailable": True})


@pytest.mark.parametrize("method", ["read", "fresh"])
@pytest.mark.parametrize("damage", ["manufacturer", "malformed-vrr", "added-disabled"])
def test_every_read_inventory_refusal_is_sticky_without_rebasing(monkeypatch, method, damage):
    initial = sample()
    initial["outputs"].append({"name": "DP-DISABLED", "logical": None, "make": "Fabricated"})
    bad = deepcopy(initial)
    if damage == "manufacturer":
        bad["outputs"][1]["make"] = "Changed"
    elif damage == "malformed-vrr":
        bad["outputs"][1]["vrr_enabled"] = 1
    else:
        bad["outputs"].append({"name": "DP-ADDED", "logical": None})
    layout, desktop, _, records, _, _ = setup(monkeypatch, [])
    desktop.samples = [initial, bad, initial]
    layout = restore_layout.Layout(layout.attempt, desktop, initial, 1)
    frozen = deepcopy(layout.output_inventory)
    with pytest.raises(ValueError):
        getattr(layout, method)()
    # Strict error fallback also refuses without reading a recovery or clearing evidence.
    with pytest.raises(ValueError):
        layout.read()
    assert desktop.samples == [initial] and layout.output_inventory == frozen and not records


@pytest.mark.parametrize("missing", ["capture", "transport"])
def test_no_invented_unavailable_full_inventory(monkeypatch, missing):
    initial = sample()
    initial["outputs"] = [{"name": "DP-1", "logical": {}}]  # genuinely unknown scale
    layout, desktop, _, records, _, _ = setup(monkeypatch, [])
    desktop.samples = [deepcopy(initial)]
    if missing == "capture":
        del initial["outputs"]
    else:
        desktop = SimpleNamespace(windows=desktop.windows, workspaces=desktop.workspaces)
    with pytest.raises(ValueError, match="inventory"):
        restore_layout.Layout(layout.attempt, desktop, initial, 1)
    assert not records


def test_capture_inventory_and_first_read_accept_equivalent_transport_forms(monkeypatch):
    initial, reply = sample(), sample()
    initial["outputs"].append({"name": "DP-DISABLED", "logical": None, "make": "Fabricated"})
    reply["outputs"] = {
        "DP-DISABLED": {"make": "Fabricated", "logical": None, "name": "DP-DISABLED"},
        "DP-1": {"logical": {"scale": 1}, "name": "DP-1"},
    }
    layout, desktop, _, records, _, _ = setup(monkeypatch, [])
    desktop.samples = [reply, reply]
    layout = restore_layout.Layout(layout.attempt, desktop, initial, 1)
    initial["outputs"][1]["make"] = "caller buffer changed"
    layout.fresh()
    assert not records and not desktop.samples


@pytest.mark.parametrize("phase", ["pre-effect", "postcondition"])
@pytest.mark.parametrize("damage", ["manufacturer", "malformed-vrr", "added-disabled"])
def test_effect_reads_preserve_adverse_inventory_and_never_read_recovery(
    integrated, monkeypatch, phase, damage
):
    s = integrated
    original_outputs = s.desktop.outputs
    pending, seen, recovered = [False], [], []

    def outputs(*, deadline=None):
        value = original_outputs(deadline=deadline) + [
            {"name": "DP-DISABLED", "logical": None, "make": "Fabricated"}
        ]
        if seen:
            recovered.append(True)
        if pending[0]:
            pending[0] = False
            seen.append(True)
            if damage == "manufacturer":
                value[-1]["make"] = "Changed"
            elif damage == "malformed-vrr":
                value[-1]["vrr_enabled"] = 1
            else:
                value.append({"name": "DP-ADDED", "logical": None})
        return value

    monkeypatch.setattr(s.desktop, "outputs", outputs)
    if phase == "pre-effect":
        effect = restore_layout.Layout.effect

        def before(self, *args, **kwargs):
            pending[0] = True
            return effect(self, *args, **kwargs)

        monkeypatch.setattr(restore_layout.Layout, "effect", before)
    else:
        action = s.desktop.action

        def after(*args):
            action(*args)
            pending[0] = True

        monkeypatch.setattr(s.desktop, "action", after)
    _, result = s.run([s.entry(1, 1)])
    assert result["status"] == "interrupted" and result["final_observation"] == {
        "unavailable": True
    }
    assert len(s.proofs) == 1 and len(s.desktop.actions) == (phase == "postcondition")
    assert len(seen) == 1 and not recovered and not result["effects"]
    assert s.store.pointer("last-reopened") is None
