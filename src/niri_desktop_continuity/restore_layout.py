"""Bounded owned-column construction with observed postconditions, never corrective retries.

Niri focus/action is not atomic: an idle desktop and the trusted fresh Ghostty connection
contract remain necessary. PID association alone is not a general Wayland ownership proof.
"""

from __future__ import annotations

import time
from copy import deepcopy

from . import restore_dimensions as dimensions
from . import restore_geometry as geometry
from . import restore_host as host
from . import restore_observation as observation
from . import restore_state as states
from .restore_failure_observation import FailureObservation
from .restore_geometry import groups
from .restore_state import number, projected
from .restore_wire import remaining


class LayoutUnavailable(ValueError):
    """A known pre-effect capability gap, not permission to settle dispatched ambiguity."""


class Layout:
    def __init__(self, attempt, desktop, current, timeout):
        self.attempt, self.desktop, self.timeout = attempt, desktop, timeout
        self.owned = {}
        self.birth_focus = {}
        self.targets = {}
        self.rows = []
        self.failure_observation = FailureObservation()
        self.protected = {w["id"]: deepcopy(w) for w in current["windows"]}
        self.inventory_failed = True  # constructor validation failures also remain latched
        if "outputs" not in current:
            raise ValueError("complete captured output inventory required")
        self.output_inventory = observation.output_inventory(current["outputs"])
        self.inventory_failed = False
        self.state = self.read()
        if projected(self.state) != projected(
            (
                {w["id"]: w for w in current["windows"]},
                current["workspaces"],
                states.output_scales(current.get("outputs", []), current["workspaces"]),
            )
        ):
            raise ValueError("desktop changed after capture")
        focused = [w["id"] for w in self.state[0].values() if w.get("is_focused")]
        if len(focused) > 1:
            raise ValueError("ambiguous initial focus")
        self.original_focus = focused[0] if focused else None
        targets = [w for w in self.state[1] if w.get("is_focused")]
        if len(targets) != 1 or not targets[0].get("output"):
            raise LayoutUnavailable("unambiguous current output required")
        self.output = targets[0]["output"]
        self.anchor = min(
            (w for w in self.state[1] if w["output"] == self.output), key=lambda w: w["idx"]
        )["id"]
        self.effects = []

    def read(self):
        return self.failure_observation.bind(states.decode(self.sample()))

    def sample(self, deadline=None):
        if self.inventory_failed:
            raise ValueError("output inventory previously refused; no further sampling")

        self.failure_observation.start_sample()

        def query(name, method, *args):
            if deadline is None:
                return self.failure_observation.query(name, method, *args)
            remaining(deadline)
            value = self.failure_observation.query(name, method, *args, deadline=deadline)
            remaining(deadline)
            return value

        windows = query("windows", self.desktop.windows)
        workspaces = query("workspaces", self.desktop.workspaces)
        if len(windows) > 512 or len(workspaces) > 512:
            raise ValueError("desktop observation exceeds bound")
        ids = [w["id"] for w in windows]
        if len(ids) != len(set(ids)) or any(type(i) is not int for i in ids):
            raise ValueError("ambiguous window IDs")
        if len({w["id"] for w in workspaces}) != len(workspaces):
            raise ValueError("ambiguous workspace IDs")
        if hasattr(self.desktop, "outputs"):
            outputs = query("outputs", self.desktop.outputs)
        elif hasattr(self.desktop, "_query"):
            outputs = query("outputs", self.desktop._query, "outputs")
        else:
            self.inventory_failed = True
            raise ValueError("complete output inventory transport required")
        try:
            observation.check_outputs(outputs, self.output_inventory)
        except BaseException:
            # Every failed check is sticky, including interruption; propagate it unchanged.
            self.inventory_failed = True
            raise
        return states.record(
            (
                {w["id"]: w for w in windows},
                workspaces,
                states.output_scales(outputs, workspaces),
            )
        )

    def proofs(self, state, deadline=None, *, phase="proofs"):
        deadline = time.monotonic() + self.timeout if deadline is None else deadline
        remaining(deadline)
        self.attempt.check()
        remaining(deadline)
        host.route(self.attempt.identity)
        remaining(deadline)
        for wid, baseline in self.protected.items():
            current = state[0].get(wid)
            if current is None or any(
                current.get(k) != baseline.get(k) for k in ("pid", "workspace_id", "is_floating")
            ):
                raise ValueError("protected window changed or disappeared")
            for field in ("tile_size", "window_size"):
                if current.get("layout", {}).get(field) != baseline.get("layout", {}).get(field):
                    self.failure_observation.reject(state, self.protected, phase)
                    raise ValueError("protected dimensions changed")
        for wid, proof in self.owned.items():
            remaining(deadline)
            proof.validate(deadline=deadline)
            remaining(deadline)
            matches = [
                w["id"] for w in state[0].values() if w.get("pid") == proof.process.pin["pid"]
            ]
            if matches != [wid]:
                raise ValueError("owned output missing, surplus or shared")

    def fresh(self):
        state = self.read()
        self.proofs(state, phase="fresh")
        if not states.compatible(self.state, state):
            raise ValueError("desktop or focus drift; all later effects stopped")
        self.state = state
        self.refresh_coverage()
        return state

    def refresh_coverage(self):
        if self.rows:
            dimensions.observe(self.attempt.plan, self.rows, self.state)

    def associate(self, proof, index):
        deadline = time.monotonic() + self.timeout
        remaining(deadline)
        before = deepcopy(self.state)  # immutable across every observation, never rolling forward
        pid = proof.process.pin["pid"]
        if any(w.get("pid") == pid for w in before[0].values()):
            raise ValueError("host overlaps baseline or protected process")
        remaining(deadline)
        pending, splits = None, 0

        def prove(state, phase="association-baseline"):
            remaining(deadline)
            self.proofs(state, deadline=deadline, phase=phase)
            remaining(deadline)
            proof.validate(deadline=deadline)
            remaining(deadline)

        while True:
            prove(before)
            value = self.sample(deadline)
            reference = observation.pending_reference(value, before)
            remaining(deadline)
            if reference is not None:
                prove(before)  # classifier proved exact canonical baseline windows
                splits += 1
                if splits > 3 or (pending is not None and pending != reference):
                    raise ValueError("split allowance exhausted or pending reference changed")
                pending = reference
            else:
                state = states.decode(value)  # always strict; never erase a foreign reference
                self.failure_observation.bind(state)
                prove(state, phase="association")
                matches = [w for w in state[0].values() if w.get("pid") == pid]
                if len(matches) > 1:
                    raise ValueError("surplus owned outputs")
                arrivals = set(state[0]) - set(before[0])
                if arrivals - {w["id"] for w in matches}:
                    raise ValueError("unowned arrival is protected; stop effects")
                if pending is not None and (
                    len(matches) != 1
                    or (matches[0]["id"], matches[0]["workspace_id"]) != pending
                    or not any(
                        w["id"] == pending[1] and w["active_window_id"] == pending[0]
                        for w in state[1]
                    )
                ):
                    raise ValueError("pending reference disappeared or lacks exact owned proof")
                if matches:
                    wid, previous = geometry.associate(before, state, pid)
                    details = {
                        "entry": index,
                        "before": states.record(before),
                        "after": states.record(state),
                    }
                    remaining(deadline)
                    self.attempt.append("association", details)
                    # A slow durable append may exist. Never claim no write or accept it late.
                    remaining(deadline)
                    self.birth_focus[wid] = previous
                    self.owned[wid] = proof
                    self.state = state
                    return wid
                if states.record(state) != states.record(before):
                    raise ValueError("desktop changed while awaiting owned output")
            self.desktop.sleep(min(0.05, remaining(deadline)))
            remaining(deadline)

    def effect(self, args, *, measured_float=None, target=None):
        self.fresh()
        if geometry.address(self.state, list(args)) != target:
            raise ValueError("workspace reference changed before durable intent; no dispatch")
        expected = geometry.transition(
            self.state, list(args), set(self.owned), self.birth_focus, self.original_focus
        )
        self.attempt.intent(
            "layout",
            {
                "argv": list(args),
                "before": states.record(self.state),
                "expected": states.record(expected),
                "measured_float": measured_float,
                "target": target,
            },
        )
        self.fresh()  # revalidate after durable writes, immediately before dispatch
        if geometry.address(self.state, list(args)) != target:
            raise ValueError("workspace reference changed after durable intent; no dispatch")
        self.desktop.action(*args)
        deadline = self.desktop.monotonic() + self.timeout
        while True:
            actual = self.read()
            self.proofs(actual, phase="postcondition")
            if measured_float is not None and measured_float in actual[0]:
                position = actual[0][measured_float]["layout"].get("tile_pos_in_workspace_view")
                if (
                    isinstance(position, list)
                    and len(position) == 2
                    and all(number(n) for n in position)
                ):
                    expected[0][measured_float]["layout"]["tile_pos_in_workspace_view"] = position
            if states.compatible(expected, actual):
                self.state = actual
                self.attempt.observed({"layout": states.record(actual)})
                self.effects.append(list(args))
                self.refresh_coverage()
                return
            # Observation-only wait; never repeat a dispatched action.
            if self.desktop.monotonic() >= deadline:
                raise ValueError("layout postcondition not observed; no cleanup")
            self.desktop.sleep(0.05)

    def focus(self, wid, *, original=False):
        self.fresh()
        if wid not in self.owned and not (
            original and wid == self.original_focus and wid in self.protected
        ):
            raise ValueError("focus target not admitted")
        if self.state[0][wid].get("is_focused"):
            return
        self.effect(("focus-window", "--id", str(wid)))

    def cohort(self, wid):
        self.fresh()
        w = self.state[0][wid]
        tiles = next((g for g in groups(self.state[0], w["workspace_id"]) if wid in g), None)
        if tiles is None or any(i not in self.owned for i in tiles):
            raise LayoutUnavailable("mixed or unknown owned column")
        return tiles

    def target(self, idx):
        self.fresh()
        return geometry.target(self.state, idx, self.targets, self.output, self.anchor)

    def place(self, wid, workspace):
        self.fresh()
        w = self.state[0][wid]
        if w["workspace_id"] == workspace:
            return
        if w["is_floating"] or self.cohort(wid) != [wid]:
            raise LayoutUnavailable("workspace donor must be an owned tiled singleton")
        target = geometry.workspace(self.state, workspace)
        self.effect(
            (
                "move-window-to-workspace",
                "--window-id",
                str(wid),
                "--focus",
                "false",
                str(target["idx"]),
            ),
            target={"workspace_id": workspace, "output": target["output"], "index": target["idx"]},
        )

    def move_column(self, wid, target):
        tiles = self.cohort(wid)
        self.focus(wid)
        workspace = self.state[0][wid]["workspace_id"]
        if groups(self.state[0], workspace).index(tiles) == target - 1:
            return
        self.effect(("move-column-to-index", str(target)))

    def consume(self, seed, donor):
        tiles = self.cohort(seed)
        if self.cohort(donor) != [donor]:
            raise LayoutUnavailable("consume donor must be an owned singleton")
        workspace = self.state[0][seed]["workspace_id"]
        columns = groups(self.state[0], workspace)
        rank = columns.index(tiles)
        if rank + 1 >= len(columns) or columns[rank + 1] != [donor]:
            raise LayoutUnavailable("immediate right top tile is not exact owned donor")
        self.focus(seed)
        self.effect(("consume-window-into-column",))

    def preflight_width(self, wid, desired):
        layout = self.state[0][wid]["layout"]
        tile, window = (
            (layout.get("tile_size") or [None])[0],
            (layout.get("window_size") or [None])[0],
        )
        if desired is None:
            if not number(tile) or tile <= 0:
                raise LayoutUnavailable("fresh width unavailable for a non-recorded dimension")
            return
        if tile == desired:
            return
        try:
            dimensions.width_token(tile, window, desired)
        except ValueError as exc:
            raise LayoutUnavailable(str(exc)) from exc

    def width(self, seed, desired):
        tiles = self.cohort(seed)
        layout = self.state[0][seed]["layout"]
        tile, window = (
            (layout.get("tile_size") or [None])[0],
            (layout.get("window_size") or [None])[0],
        )
        if desired is None or tile == desired:
            return  # no saved width: preserve observation, never invent a requested dimension
        try:
            token = dimensions.width_token(tile, window, desired)
        except ValueError as exc:
            raise LayoutUnavailable(str(exc)) from exc
        decoration = tile - window
        for wid in tiles:
            other = self.state[0][wid]["layout"]
            if other["tile_size"][0] - other["window_size"][0] != decoration:
                raise LayoutUnavailable("inconsistent column decorations")
        self.focus(seed)
        self.effect(("set-column-width", token))

    def floating(self, wid, position):
        if position is not None and (
            not isinstance(position, list)
            or len(position) != 2
            or not all(number(n) for n in position)
        ):
            raise LayoutUnavailable("unknown floating geometry")
        self.fresh()
        target = (
            None
            if position is None
            else dimensions.quantize(position, dimensions.output_scale(self.state, wid))
        )
        if not self.state[0][wid]["is_floating"]:
            if self.cohort(wid) != [wid]:
                raise LayoutUnavailable("floating donor must be an owned singleton")
            self.effect(("move-window-to-floating", "--id", str(wid)), measured_float=wid)
        if position is None:
            return  # no saved position: retain measured native conversion geometry
        old = self.state[0][wid]["layout"].get("tile_pos_in_workspace_view")
        if not isinstance(old, list) or len(old) != 2 or not all(number(n) for n in old):
            raise LayoutUnavailable("unknown floating position")
        if old == target:
            return  # comparison above is an observation, not a fabricated effect
        delta = [f"{a - b:+.17g}" for a, b in zip(target, old, strict=True)]
        if (
            dimensions.quantize(
                [v + float(d) for v, d in zip(old, delta, strict=True)],
                dimensions.output_scale(self.state, wid),
            )
            != target
        ):
            raise LayoutUnavailable(
                "relative delta cannot encode the requested observable position"
            )
        self.effect(("move-floating-window", "--id", str(wid), "-x", delta[0], "-y", delta[1]))

    def names(self, names, entries):
        used = {r["entry"]["target_workspace_idx"] for r in entries}
        for idx, name in names.items():
            if int(idx) not in used:
                continue
            workspace = self.target(int(idx))
            target = next(w for w in self.state[1] if w["id"] == workspace)
            if target.get("name") == name:
                continue
            if (
                target.get("name")
                or any(w.get("name") == name for w in self.state[1])
                or any(
                    w["workspace_id"] == workspace and w["id"] not in self.owned
                    for w in self.state[0].values()
                )
            ):
                raise LayoutUnavailable(
                    "workspace naming would affect protected or conflicting metadata"
                )
            focused = [w for w in self.state[1] if w.get("is_focused")]
            if len(focused) != 1 or focused[0].get("output") != self.output:
                raise LayoutUnavailable("workspace name index has foreign output")
            self.effect(
                ("set-workspace-name", "--workspace", str(target["idx"]), name),
                target={
                    "workspace_id": workspace,
                    "output": target["output"],
                    "index": target["idx"],
                },
            )

    def arrange(self, entries):
        # First isolate every owned donor in an ordered suffix, regardless of protected interleaving.
        by_workspace = {}
        for row in entries:
            entry, wid = row["entry"], row["restored_window_id"]
            workspace = self.target(entry["target_workspace_idx"])
            self.place(wid, workspace)
            by_workspace.setdefault(workspace, []).append(row)
        for workspace, rows in by_workspace.items():
            tiled = [r for r in rows if not r["entry"]["floating"]]
            for row in tiled:
                wid = row["restored_window_id"]
                if self.cohort(wid) != [wid]:
                    raise LayoutUnavailable("initial donor is not singleton")
                self.move_column(wid, len(groups(self.state[0], workspace)))
            columns = {}
            for row in tiled:
                entry = row["entry"]
                key = (
                    entry["column"]
                    if entry["column"] is not None
                    else ("extra", row["restored_window_id"])
                )
                columns.setdefault(key, []).append(row)
            for tiles in columns.values():
                seed = tiles[0]["restored_window_id"]
                for row in tiles[1:]:
                    self.consume(seed, row["restored_window_id"])
                index = self.rows.index(tiles[0])
                initial = {
                    i: r["observed_initial_width"]
                    for i, r in enumerate(self.rows)
                    if "observed_initial_width" in r
                }
                self.width(
                    seed,
                    dimensions.width_target(dimensions.policies(self.attempt.plan)[index], initial),
                )
            for row in rows:
                if row["entry"]["floating"]:
                    self.width(row["restored_window_id"], row["entry"]["width"])
                    self.floating(row["restored_window_id"], row["entry"]["floating_position"])
        self.fresh()
