"""Handwritten topology machine, not an action log or production-planner-derived oracle."""

import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_reopen import IDENTITY, recipe, saved, window
from test_restore_cli_grammar import niri_change

from niri_desktop_continuity import (
    operation_lock,
    restore,
    restore_execute,
    restore_host,
    restore_layout,
    restore_wire,
)
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.restore_attempt import Attempt
from niri_desktop_continuity.store import Store


class Topology:
    def __init__(self):
        self.decoration = 12.0
        self.window_widths = {}
        self.columns = {1: [[70, 71], [80]], 2: []}
        self.floats = {}
        self.windows_by_id = {i: window(i, 1, 1) for i in (70, 71, 80)}
        self.widths = {70: 640.0, 71: 640.0, 80: 720.0}
        self.focus = 70
        self.actions = []
        self.clock = 0.0
        self.ws = [
            {"id": 1, "idx": 1, "output": "DP-1", "is_focused": True},
            {"id": 2, "idx": 2, "output": "DP-1", "is_focused": False},
        ]

    def windows(self, *, deadline=None):
        result = []
        for workspace, columns in self.columns.items():
            for c, tiles in enumerate(columns, 1):
                for t, wid in enumerate(tiles, 1):
                    result.append(
                        {
                            **self.windows_by_id[wid],
                            "workspace_id": workspace,
                            "is_focused": wid == self.focus,
                            "is_floating": False,
                            "layout": {
                                "pos_in_scrolling_layout": [c, t],
                                "tile_size": [self.widths[wid], 1200.0 / len(tiles)],
                                "window_size": [
                                    self.window_widths.get(wid, self.widths[wid] - self.decoration),
                                    1200.0 / len(tiles) - 12.0,
                                ],
                            },
                        }
                    )
        for wid, (workspace, position) in self.floats.items():
            result.append(
                {
                    **self.windows_by_id[wid],
                    "workspace_id": workspace,
                    "is_focused": wid == self.focus,
                    "is_floating": True,
                    "layout": {
                        "pos_in_scrolling_layout": None,
                        "tile_size": [self.widths[wid], 600.0],
                        "window_size": [
                            self.window_widths.get(wid, self.widths[wid] - self.decoration),
                            588.0,
                        ],
                        "tile_pos_in_workspace_view": list(position),
                    },
                }
            )
        return deepcopy(result)

    def outputs(self, *, deadline=None):
        # Explicit fabricated grid for the original eighth-pixel fixture, not a runtime default.
        return [
            {"name": name, "logical": {"scale": 8.0}}
            for name in sorted({w["output"] for w in self.ws})
        ]

    def workspaces(self, *, deadline=None):
        return deepcopy(self.ws)

    def monotonic(self):
        return self.clock

    def sleep(self, seconds):
        self.clock += seconds

    def observe(self):
        return {
            **saved(self.windows(), self.workspaces()),
            "outputs": self.outputs(),
            "identity": restore.compositor_identity(),
        }

    def add(self, pid):
        wid = pid + 10000
        self.windows_by_id[wid] = window(wid, 1, 1, pid=pid)
        self.widths[wid] = 800.0
        self.columns[1].insert(1, [wid])  # deliberately interleaved with protected columns
        return wid

    def location(self, wid):
        for workspace, columns in self.columns.items():
            for index, tiles in enumerate(columns):
                if wid in tiles:
                    return workspace, index
        raise AssertionError("window not tiled")

    def action(self, *args):
        self.actions.append(args)
        name = args[0]
        if name == "focus-window":
            self.focus = int(args[-1])
            workspace = next(w["workspace_id"] for w in self.windows() if w["id"] == self.focus)
            for ws in self.ws:
                ws["is_focused"] = ws["id"] == workspace
        elif name == "move-column-to-index":
            workspace, index = self.location(self.focus)
            columns = self.columns[workspace]
            column = columns.pop(index)
            columns.insert(min(len(columns), int(args[1]) - 1), column)
        elif name == "consume-window-into-column":
            workspace, index = self.location(self.focus)
            columns = self.columns[workspace]
            donor = columns[index + 1].pop(0)  # actual Niri right TOP, never earlier focus
            columns[index].append(donor)
            seed = columns[index][0]
            self.widths[donor] = self.widths[seed]
            self.window_widths[donor] = self.window_widths.get(
                seed, self.widths[seed] - self.decoration
            )
            if not columns[index + 1]:
                columns.pop(index + 1)
        elif name == "set-column-width":
            kind, width = niri_change(args[1])
            assert kind == "SetFixed" and width > 0, "outside admitted fixed-width model"
            workspace, index = self.location(self.focus)
            for wid in self.columns[workspace][index]:
                tile = min(100000.0, max(1.0, width + self.decoration))
                # tile.rs 938–958: subtract border then floor Wayland's integer request.
                requested = int(max(1.0, tile - self.decoration))
                self.window_widths[wid] = requested
                self.widths[wid] = requested + self.decoration
        elif name == "move-window-to-workspace":
            wid = int(args[2])
            workspace, index = self.location(wid)
            self.columns[workspace][index].remove(wid)
            if not self.columns[workspace][index]:
                self.columns[workspace].pop(index)
            output = next(w["output"] for w in self.ws if w["is_focused"])
            target = next(
                w["id"] for w in self.ws if w["idx"] == int(args[-1]) and w["output"] == output
            )
            self.columns[target].append([wid])
        elif name == "move-window-to-floating":
            wid = int(args[-1])
            workspace, index = self.location(wid)
            assert self.columns[workspace].pop(index) == [wid]
            self.floats[wid] = (workspace, [123.25, 91.5])
        elif name == "move-floating-window":
            wid = int(args[2])
            old = self.floats[wid][1]
            # Signed CLI numbers are relative; unsigned positive numbers would be absolute.
            for i, arg in enumerate((args[4], args[6])):
                kind, value = niri_change(arg, position=True)
                assert kind in {"SetFixed", "AdjustFixed"}
                old[i] = old[i] + value if kind == "AdjustFixed" else value
        elif name == "set-workspace-name":
            next(w for w in self.ws if w["idx"] == int(args[2]))["name"] = args[3]
        else:
            raise AssertionError(f"unmodelled IPC {name}")


@pytest.fixture
def integrated(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    identity = {**IDENTITY, "boot_id": "new"}
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)
    monkeypatch.setattr(restore, "compositor_identity", lambda: identity)
    monkeypatch.setattr(restore_host, "route", lambda value: None)

    class Image:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(restore_execute, "Image", Image)
    from test_restore_lifecycle import Niri

    desktop = Niri()
    desktop.initialize()
    # Semantic/fault tests use the topology's controllable clock, not fsync/host latency.
    # Keep the short budget and the real deadline predicate. Scope its clock substitution
    # to each pure Layout check: producer/host/native deadlines must retain real time.
    # Sharing this clock object also preserves explicit restore_layout.time injections.
    clock = SimpleNamespace(monotonic=desktop.monotonic)

    def remaining(deadline):
        with monkeypatch.context() as clock_patch:
            clock_patch.setattr(restore_wire, "time", clock)
            return restore_wire.remaining(deadline)

    monkeypatch.setattr(restore_layout, "time", clock)
    monkeypatch.setattr(restore_layout, "remaining", remaining)
    proofs = []

    def launch(attempt, ticket, **kwargs):
        value = attempt.consume(ticket)
        assert value["cwd"] == str(tmp_path)
        attempt.intent(
            "bootstrap",
            {
                "entry": ticket.index,
                "nonce": "a" * 64,
                "spec": {"argv": value["argv"], "cwd": value["cwd"]},
                "image": {"device": 1, "inode": 2, "sha256": "b" * 64},
                "directory": {"device": 1, "inode": 3},
            },
        )
        with pytest.raises(ValueError, match="another continuity writer"):
            with operation_lock.operation_lock(identity, effectful=False):
                pass
        pid = 2000 + len(proofs)
        desktop.add(pid)
        pin = {"pid": pid, "boot_id": identity["boot_id"], "start_ticks": 1}
        attempt.observed({"bootstrap": pin, "binding": "c" * 64})
        attempt.intent("exec", {"entry": ticket.index, "process": pin, "binding": "c" * 64})
        proof = SimpleNamespace(
            process=SimpleNamespace(pin=pin), receipt="fabricated", invalid=False
        )

        def validate(**kwargs):
            if proof.invalid:
                raise ValueError("fabricated exited/reused proof")

        def close():
            proof.invalid = True

        proof.validate, proof.close = validate, close
        attempt.proofs.append(proof)
        evidence = {
            "phase": "process-observed",
            "ownership": "process-only",
            "process": pin,
            "binding": "c" * 64,
            "window_ownership": "not-proved",
            "placement": "not-attempted",
            "native_session": "not-proved",
            "settlement": "unresolved",
        }
        proof.receipt = attempt.store.put("receipts", evidence)
        attempt.observed(evidence)
        proofs.append(proof)
        return proof

    monkeypatch.setattr(restore_execute, "launch", launch)
    store = Store(tmp_path / "state")

    def entry(wid, col, tile=1, **kw):
        return window(
            wid,
            1,
            col,
            tile=tile,
            reopen={**recipe("shell", str(tmp_path / "ghostty")), "cwd": str(tmp_path)},
            **kw,
        )

    def run(windows):
        key = store.put("snapshots", saved(windows))
        return key, restore.restore(
            store, key, desktop, apply=True, observe=desktop.observe, spawn_timeout=0.1
        )

    return SimpleNamespace(
        desktop=desktop,
        store=store,
        run=run,
        entry=entry,
        proofs=proofs,
        identity=identity,
        runtime=runtime,
    )


def test_multiwindow_actual_topology_decorations_floating_and_focus(integrated):
    s = integrated
    floating = s.entry(
        4,
        3,
        is_floating=True,
        layout={
            "pos_in_scrolling_layout": None,
            "tile_size": [800.0, 600.0],
            "tile_pos_in_workspace_view": [-7.125, 32.75],
        },
    )
    key, result = s.run([s.entry(1, 1), s.entry(2, 1, 2), s.entry(3, 2), floating])
    assert result["status"] == "reopened", result
    assert s.desktop.columns == {1: [[70, 71], [80], [12000, 12001], [12002]], 2: []}
    assert s.desktop.widths == {
        70: 640.0,
        71: 640.0,
        80: 720.0,
        12000: 900.0,
        12001: 900.0,
        12002: 900.0,
        12003: 800.0,
    }
    assert s.desktop.floats == {12003: (1, [-7.125, 32.75])}
    final = {w["id"]: w["layout"] for w in result["final_observation"]["windows"]}
    assert [final[i]["tile_size"] for i in (12000, 12001, 12002)] == [
        [900.0, 600.0],
        [900.0, 600.0],
        [900.0, 1200.0],
    ]
    assert [final[i]["window_size"] for i in (12000, 12001, 12002)] == [
        [888.0, 588.0],
        [888.0, 588.0],
        [888.0, 1188.0],
    ]
    assert s.desktop.focus == 70
    assert s.store.pointer("last-reopened") == key
    assert all(p.invalid for p in s.proofs)  # closed only after last observation/commit
    with operation_lock.operation_lock(s.identity):
        pass  # valid terminal does not wedge unrelated writers


def test_completed_cross_store_replay_and_new_source(integrated, tmp_path):
    s = integrated
    key, first = s.run([s.entry(1, 1)])
    assert first["status"] == "reopened"
    count = len(s.desktop.actions)
    other = Store(tmp_path / "other")
    other.put("snapshots", s.store.get("snapshots", key))
    replay = restore.restore(
        other, key, s.desktop, apply=True, observe=lambda: pytest.fail("historical, not fresh")
    )
    assert replay["historical"] and replay["receipt_digest"] == first["receipt_digest"]
    assert len(s.desktop.actions) == count and len(s.proofs) == 1
    _, second = s.run([s.entry(2, 1)])
    assert second["status"] == "reopened" and len(s.proofs) == 2


def test_unprocessed_intents_and_poisoned_attempt_no_nested_writer(integrated):
    s = integrated
    key = s.store.put("snapshots", saved([]))
    with Attempt(s.store, key, s.identity) as attempt:
        recipe = s.entry(1, 1)["reopen"]
        recipe["argv"] = [
            recipe["argv"][0],
            "--config-default-files=false",
            "--gtk-single-instance=false",
            "--initial-window=true",
            f"--working-directory={recipe['cwd']}",
        ]
        attempt.prepare({"mode": "process-probe", "entries": [{"recipe": recipe}]})
        ticket = attempt.ticket(0)
        attempt.consume(ticket)
        with pytest.raises(ValueError):
            attempt.consume(ticket)
        with pytest.raises(ValueError, match="another continuity writer"):
            with Attempt(s.store, key, s.identity):
                pass
        attempt.poisoned = True
        with pytest.raises(ValueError):
            attempt.intent("layout", {})
    with pytest.raises(ValueError):
        attempt.check()
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pass


@pytest.mark.parametrize("change", ["surplus", "unowned", "focus", "exit", "shared"])
def test_after_launch_uncertainty_stops_all_layout_and_replay(integrated, monkeypatch, change):
    s = integrated
    original = restore_execute.launch

    def changed(attempt, ticket, **kwargs):
        proof = original(attempt, ticket, **kwargs)
        if change == "surplus":
            s.desktop.add(proof.process.pin["pid"] + 1)
            s.desktop.windows_by_id[12001]["pid"] = proof.process.pin["pid"]
        elif change == "unowned":
            s.desktop.add(9000)
        elif change == "focus":
            s.desktop.focus = 80
        elif change == "exit":
            proof.invalid = True
        else:
            s.desktop.columns[1] = [[70, 71, 12000], [80]]
        return proof

    monkeypatch.setattr(restore_execute, "launch", changed)
    key, result = s.run([s.entry(1, 1), s.entry(2, 2)])
    assert result["status"] == "interrupted"
    assert len(result["windows"]) == 2 and result["windows"][1]["status"] == "unprocessed"
    assert not s.desktop.actions and len(s.proofs) == 1
    assert s.store.pointer("last-reopened") is None
    with pytest.raises(ValueError, match="unresolved restore"):
        restore.restore(s.store, key, s.desktop, apply=True)


@pytest.mark.parametrize("damage", ["receipt", "store", "unknown", "legacy", "orphan"])
def test_damaged_terminal_never_releases_admission(integrated, damage):
    s = integrated
    _, result = s.run([s.entry(1, 1)])
    assert result["status"] == "reopened"
    if damage == "receipt":
        s.store.path("receipts", result["receipt_digest"]).unlink()
    elif damage == "store":
        s.store.root.rename(s.store.root.with_name("displaced"))
    elif damage == "unknown":
        (history.fence_path(s.identity) / "unrecognized").write_text("{}")
    elif damage == "legacy":
        history.fence_path(s.identity).with_suffix(".permit").write_text("{}")
    else:
        (history.fence_path(s.identity) / "00009999.json").write_text("{}")
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pass


def stall_host_clock_after_association(monkeypatch):
    """Model a one-second persistence/scheduling pause without sleeping or skipping IO."""
    clock, fired = [10.0], []
    append = Attempt.append
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    def stalled(attempt, kind, payload):
        result = append(attempt, kind, payload)
        if kind == "association":
            fired.append(kind)
            clock[0] += 1.0
        return result

    monkeypatch.setattr(Attempt, "append", stalled)
    return fired


@pytest.mark.parametrize("width", [900.0, 800.5])
def test_given_host_pause_when_semantic_restore_then_intended_width_outcome(
    integrated, monkeypatch, width
):
    s = integrated
    # Given a mocked launch and a host pause longer than the 0.1s semantic budget.
    fired = stall_host_clock_after_association(monkeypatch)
    entry = s.entry(1, 1)
    entry["layout"]["tile_size"][0] = width
    # When real persistence completes, do not let host scheduling preempt the oracle.
    key, result = s.run([entry])
    assert fired == ["association"]
    assert len(s.proofs) == 1 and all(p.invalid for p in s.proofs)
    if width == 900.0:
        assert result["status"] == "reopened", result
        assert s.desktop.widths[12000] == 900.0
        assert s.store.pointer("last-reopened") == key
    else:
        assert result["status"] == "interrupted", result
        assert "fixed integer" in result["error"], result
        assert not s.desktop.actions and result["effects"] == []
        assert s.store.pointer("last-reopened") is None
        with pytest.raises(ValueError, match="unresolved restore"):
            history.require_clear(s.identity)


@pytest.mark.parametrize("checkpoint", ["query", "association"])
def test_given_fixture_clock_expiry_when_associating_then_no_layout(
    integrated, monkeypatch, checkpoint
):
    s = integrated
    fired = []
    append, windows = Attempt.append, s.desktop.windows

    def expire():
        fired.append(checkpoint)
        s.desktop.sleep(0.2)  # Deliberately exceed the unchanged 0.1s budget, no wall sleep.

    def query(*, deadline=None):
        result = windows(deadline=deadline)
        if checkpoint == "query" and deadline is not None and not fired:
            expire()
        return result

    def appended(attempt, kind, payload):
        result = append(attempt, kind, payload)
        if checkpoint == "association" and kind == "association":
            expire()
        return result

    monkeypatch.setattr(s.desktop, "windows", query)
    monkeypatch.setattr(Attempt, "append", appended)
    _, result = s.run([s.entry(1, 1), s.entry(2, 2)])
    assert fired == [checkpoint]
    assert result["status"] == "interrupted"
    assert result["error_type"] == "TimeoutError"
    assert result["error"] == "bootstrap absolute deadline exceeded or invalid"
    assert len(s.proofs) == 1 and s.proofs[0].invalid
    assert not s.desktop.actions and result["effects"] == []
    assert s.store.pointer("last-reopened") is None
    records = [history.read(p) for p in sorted(history.fence_path(s.identity).glob("*.json"))]
    assert sum(r["type"] == "association" for r in records) == (checkpoint == "association")
    with pytest.raises(ValueError, match="unresolved restore"):
        history.require_clear(s.identity)


def test_given_fixture_clock_when_checking_deadlines_then_native_clock_is_untouched(integrated):
    # The fake Layout interval must not leak into real producer/process/native checks.
    native_clock = restore_wire.time
    assert native_clock is time and restore_layout.time is not time
    assert restore_layout.remaining(0.1) == 0.1
    assert restore_wire.time is native_clock
    with pytest.raises(TimeoutError, match="absolute deadline"):
        restore_layout.remaining(0.0)
    assert restore_wire.time is native_clock  # also restored on the refusing path
    with pytest.raises(TimeoutError, match="absolute deadline"):
        restore_wire.remaining(time.monotonic() - 1)
