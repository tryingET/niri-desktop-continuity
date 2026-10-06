"""Handwritten pinned-Niri workspace lifecycle and active-column oracle, no native IPC."""

import json
from copy import deepcopy

import pytest
from test_reopen import saved
from test_restore_integration import Topology
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.store import Store


class Niri(Topology):
    def initialize(self):
        self.active = {
            ws["id"]: next((i for col in self.columns[ws["id"]] for i in col), None)
            for ws in self.ws
        }
        self.previous = {}
        self.next_workspace = 501
        if self.focus is not None:
            self.active[
                next(w["workspace_id"] for w in self.windows() if w["id"] == self.focus)
            ] = self.focus

    def workspaces(self, *, deadline=None):
        return [
            {
                **w,
                "active_window_id": self.active[w["id"]],
                "is_active": w["is_focused"]
                or (
                    w["idx"] == 1
                    and not any(v["is_focused"] for v in self.ws if v["output"] == w["output"])
                ),
            }
            for w in deepcopy(self.ws)
        ]

    def lifecycle(self, cleanup=False):
        for output in {w["output"] for w in self.ws}:
            workspaces = [w for w in self.ws if w["output"] == output]
            last = workspaces[-1]
            if (
                self.columns[last["id"]]
                or any(ws == last["id"] for ws, _ in self.floats.values())
                or last.get("name")
            ):
                self.next_workspace += 7  # IDs are not indices and need not be consecutive.
                new = {
                    "id": self.next_workspace,
                    "idx": len(workspaces) + 1,
                    "output": output,
                    "is_focused": False,
                }
                self.ws.append(new)
                self.columns[new["id"]] = []
                self.active[new["id"]] = None
                workspaces.append(new)
            above = getattr(self, "empty_above", False)
            if above and (self.columns[workspaces[0]["id"]] or workspaces[0].get("name")):
                self.next_workspace += 7
                new = {"id": self.next_workspace, "idx": 1, "output": output, "is_focused": False}
                self.ws.insert(self.ws.index(workspaces[0]), new)
                self.columns[new["id"]], self.active[new["id"]] = [], None
                workspaces.insert(0, new)
            if cleanup:
                for ws in workspaces[1 if above else 0 : -1]:
                    if (
                        not ws.get("name")
                        and not ws["is_focused"]
                        and not self.columns[ws["id"]]
                        and not any(i == ws["id"] for i, _ in self.floats.values())
                    ):
                        self.ws.remove(ws)
                        del self.columns[ws["id"]], self.active[ws["id"]]
            for idx, ws in enumerate([w for w in self.ws if w["output"] == output], 1):
                ws["idx"] = idx

    def add(self, pid):
        workspace = next(w["id"] for w in self.ws if w["is_focused"])
        active = self.active[workspace]
        columns = self.columns[workspace]
        index = next((n + 1 for n, col in enumerate(columns) if active in col), 0)
        wid = pid + 10000
        self.windows_by_id[wid] = {"id": wid, "pid": pid, "is_floating": False}
        self.widths[wid] = 800.0
        columns.insert(index, [wid])
        self.previous[wid] = active
        self.active[workspace] = self.focus = wid
        self.lifecycle()
        return wid

    def action(self, *args):
        if args[0] == "move-window-to-workspace":
            self.actions.append(args)
            wid = int(args[2])
            source, column = self.location(wid)
            output = next(w["output"] for w in self.ws if w["id"] == source)
            target = next(
                w["id"] for w in self.ws if w["idx"] == int(args[-1]) and w["output"] == output
            )
            columns = self.columns[source]
            assert columns.pop(column) == [wid]
            if self.active[source] == wid:
                self.active[source] = self.previous.get(wid)
                if self.active[source] is None and columns:
                    self.active[source] = columns[min(column, len(columns) - 1)][0]
            if self.focus == wid:
                self.focus = self.active[source]  # focus=false never follows the moved donor
            dest = self.columns[target]
            index = next((n + 1 for n, col in enumerate(dest) if self.active[target] in col), 0)
            dest.insert(index, [wid])
            if self.active[target] is None:
                self.active[target] = wid
        else:
            super().action(*args)
            if args[0] == "focus-window":
                ws = next(w["workspace_id"] for w in self.windows() if w["id"] == self.focus)
                self.active[ws] = self.focus
        self.lifecycle(cleanup=True)


@pytest.fixture
def faithful(integrated):
    s = integrated
    s.desktop.__class__ = Niri
    s.desktop.initialize()
    return s


def clean(s):
    d = s.desktop
    d.columns, d.windows_by_id, d.widths, d.focus = {41: []}, {}, {}, None
    d.ws = [{"id": 41, "idx": 1, "output": "DP-1", "is_focused": True}]
    d.initialize()


@pytest.mark.parametrize("count", [1, 3])
def test_clean_login_materializes_saved_workspaces(faithful, count):
    s = faithful
    clean(s)
    entries = [s.entry(i, 1) for i in range(1, count + 1)]
    for entry, workspace in zip(entries, (1, 2, 5)):
        entry["workspace_id"] = workspace
    _, result = s.run(entries)
    assert result["status"] == "reopened", result
    by_index = {w["idx"]: s.desktop.columns[w["id"]] for w in s.desktop.ws}
    assert by_index == {i: [[12000 + i - 1]] for i in range(1, count + 1)} | {count + 1: []}
    assert all(s.desktop.widths[12000 + i] == 900.0 for i in range(count))
    if count == 3:
        assert next(w for w in s.desktop.ws if w["idx"] == 3)["name"] == "lab"


@pytest.mark.parametrize("active", [80, 90])
def test_move_into_active_first_column_and_source_focus(faithful, monkeypatch, active):
    s = faithful
    d = s.desktop
    d.columns[1], d.columns[2] = [[70, 71]], [[80], [90], [91]]
    for wid in (90, 91):
        d.windows_by_id[wid] = {"id": wid, "pid": wid + 100}
        d.widths[wid] = 720.0
    d.initialize()
    d.active[2] = active
    moves = []
    original = d.action

    def observed(*args):
        original(*args)
        if args[0] == "move-window-to-workspace":
            moves.append((deepcopy(d.columns[2]), d.focus))

    monkeypatch.setattr(d, "action", observed)
    a, b = s.entry(1, 1), s.entry(2, 1)
    b["workspace_id"] = 2
    _, result = s.run([a, b])
    assert result["status"] == "reopened", result
    assert d.columns[1] == [[70, 71], [12000]]
    assert d.columns[2] == [[80], [90], [91], [12001]]
    assert d.focus == 70
    assert moves == [
        ([[80], [12001], [90], [91]] if active == 80 else [[80], [90], [12001], [91]], 12000)
    ]


def test_optional_empty_above_first_reindex_keeps_logical_destinations(faithful):
    s = faithful
    clean(s)
    s.desktop.empty_above = True
    a, b = s.entry(1, 1), s.entry(2, 1)
    b["workspace_id"] = 2
    _, result = s.run([a, b])
    assert result["status"] == "reopened", result
    assert {w["idx"]: s.desktop.columns[w["id"]] for w in s.desktop.ws} == {
        1: [],
        2: [[12000]],
        3: [[12001]],
        4: [],
    }
    assert result["windows"][0]["target_workspace_id"] == 41


@pytest.mark.parametrize("change", ["named", "middle", "output", "protected-name"])
def test_nontransient_workspace_changes_never_gain_lifecycle_exemption(
    faithful, monkeypatch, change
):
    s = faithful
    add = s.desktop.add

    def changed(pid):
        wid = add(pid)
        if change == "protected-name":
            s.desktop.ws[0]["name"] = "unapproved"
        else:
            new = {"id": 999, "idx": 3, "output": "DP-1", "is_focused": False}
            if change == "named":
                new["name"] = "unapproved"
            if change == "output":
                new.update(idx=1, output="DP-3")
            s.desktop.ws.insert(1, new) if change == "middle" else s.desktop.ws.append(new)
            s.desktop.columns[999] = []
            s.desktop.active[999] = None
            for idx, ws in enumerate([w for w in s.desktop.ws if w["output"] == "DP-1"], 1):
                ws["idx"] = idx
        return wid

    monkeypatch.setattr(s.desktop, "add", changed)
    _, result = s.run([s.entry(1, 1)])
    assert result["status"] == "interrupted"
    assert not s.desktop.actions


def test_extra_without_saved_width_preserves_observed_width(faithful):
    s = faithful
    parent = s.entry(1, 1)
    parent["reopen"]["extra"] = [deepcopy(parent["reopen"])]
    _, result = s.run([parent])
    assert result["status"] == "reopened", result
    assert s.desktop.columns[1] == [[70, 71], [80], [12000], [12001]]
    assert s.desktop.widths[12000] == 900.0 and s.desktop.widths[12001] == 800.0
    assert result["windows"][1]["geometry_coverage"]["width"] == "not-recorded-preserved"


@pytest.mark.parametrize("geometry", ["missing", "null", "floating"])
def test_missing_optional_capture_geometry_is_not_an_invented_dimension(faithful, geometry):
    s = faithful
    entry = s.entry(1, 1)
    if geometry == "missing":
        del entry["layout"]["tile_size"]
    else:
        entry["layout"]["tile_size"] = None
    if geometry == "floating":
        entry["is_floating"] = True
        entry["layout"]["pos_in_scrolling_layout"] = None
        entry["layout"]["tile_pos_in_workspace_view"] = None
    _, result = s.run([entry])
    assert result["status"] == "reopened", result
    assert result["windows"][0]["geometry_coverage"] == {
        "width": "not-recorded-preserved",
        "position": "not-recorded",
    }
    assert s.desktop.widths[12000] == 800.0
    if geometry == "floating":
        assert s.desktop.floats == {12000: (1, [123.25, 91.5])}
    assert not any(a[0] in {"set-column-width", "move-floating-window"} for a in s.desktop.actions)


def rewrite_chain(s, mutate):
    previous = None
    references = {}
    for path in sorted(history.fence_path(s.identity).glob("*.json")):
        record = history.read(path)
        payload = s.store.get("receipts", record["receipt"])
        old_receipt = record["receipt"]
        mutate(record, payload)
        if record["type"] == "observed":
            payload["intent"] = references.get(payload["intent"], payload["intent"])
        record["receipt"] = s.store.put("receipts", payload)
        references[old_receipt] = record["receipt"]
        record["previous"] = previous
        path.write_text(json.dumps(record))
        previous = digest(record)


@pytest.mark.parametrize(
    "damage",
    [
        "effects-type",
        "workspace-type",
        "observed-layout-type",
        "final-destination",
        "effects-missing",
        "bootstrap-argv",
        "already-open",
    ],
)
def test_semantic_history_blocks_every_effect_consumer(integrated, tmp_path, damage):
    s = integrated
    key, first = s.run([s.entry(1, 1)])
    assert first["status"] == "reopened", first
    other = Store(tmp_path / "foreign")
    other.put("snapshots", s.store.get("snapshots", key))
    nextkey = other.put("snapshots", saved([s.entry(2, 1)]))

    def mutate(record, payload):
        if record["type"] == "terminal":
            if damage == "effects-type":
                payload["effects"] = "not a ledger"
            elif damage == "workspace-type":
                payload["final_observation"]["workspaces"] = None
            elif damage == "effects-missing":
                payload["effects"] = []
            elif damage == "final-destination":
                next(w for w in payload["final_observation"]["windows"] if w["id"] == 12000)[
                    "workspace_id"
                ] = 999
            elif damage == "already-open":
                payload["windows"][0]["status"] = "already-open"
                payload["final_observation"]["windows"] = []
        elif (
            record["type"] == "observed"
            and damage == "observed-layout-type"
            and "layout" in payload["evidence"]
        ):
            payload["evidence"]["layout"] = "not geometry"
        elif (
            record["type"] == "intent"
            and payload.get("action") == "bootstrap"
            and damage == "bootstrap-argv"
        ):
            payload["details"]["spec"]["argv"] = ["wrong"]

    rewrite_chain(s, mutate)
    with pytest.raises(ValueError, match="unresolved restore"):
        with operation_lock.operation_lock(s.identity):
            pass
    for source in (key, nextkey):
        with pytest.raises(ValueError, match="unresolved restore"):
            restore.restore(
                other,
                source,
                s.desktop,
                apply=True,
                observe=lambda: pytest.fail("must block before observation"),
            )
