"""Bounded recorded geometry and compositor-owned empty-workspace lifecycle.

Niri's stable workspace IDs are distinct from per-output mutable indices. Only unnamed,
empty, inactive transients may disappear; new empty workspaces occur at occupied edges.
"""

import math
from copy import deepcopy


def number(n):
    return type(n) in (int, float) and math.isfinite(n)


def fields(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError("unknown restore state fields")


def output_scales(outputs, workspaces):
    if isinstance(outputs, dict):
        outputs = list(outputs.values())
    if not isinstance(outputs, list):
        raise ValueError("invalid output observation")
    names = [o["name"] for o in outputs]
    if len(set(names)) != len(names):
        raise ValueError("duplicate output observation")
    observed = {o["name"]: (o.get("logical") or {}).get("scale") for o in outputs}
    return [
        {"name": name, "scale": observed.get(name)}
        for name in sorted({w["output"] for w in workspaces})
    ]


def record(state):
    windows, workspaces = state[:2]
    outputs = state[2] if len(state) == 3 else output_scales([], workspaces)
    return {
        "outputs": deepcopy(outputs),
        "windows": [
            {
                "id": w["id"],
                "pid": w.get("pid"),
                "workspace_id": w.get("workspace_id"),
                "is_focused": w.get("is_focused", False),
                "is_floating": w.get("is_floating", False),
                "layout": {
                    k: deepcopy((w.get("layout") or {}).get(k))
                    for k in (
                        "pos_in_scrolling_layout",
                        "tile_size",
                        "window_size",
                        "tile_pos_in_workspace_view",
                    )
                },
            }
            for w in sorted(windows.values(), key=lambda w: w["id"])
        ],
        "workspaces": [
            {
                "id": w["id"],
                "idx": w["idx"],
                "output": w.get("output"),
                "name": w.get("name"),
                "is_focused": w.get("is_focused", False),
                "is_active": w.get("is_active", w.get("is_focused", False)),
                "active_window_id": w.get("active_window_id"),
            }
            for w in sorted(workspaces, key=lambda w: (w.get("output") or "", w["idx"]))
        ],
    }


def validate(value):
    """Validate ALL independent structure; enumerate, never repair, relational defects."""
    defects = []
    fields(value, "windows workspaces outputs")
    for key in ("windows", "workspaces"):
        seq = value[key]
        if not isinstance(seq, list) or len(seq) > 512:
            raise ValueError("invalid bounded restore state")
        if any(not isinstance(w, dict) for w in seq):
            raise ValueError("invalid restore entry")
        ids = [w.get("id") for w in seq]
        if any(type(i) is not int or i < 0 for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("duplicate or invalid restore IDs")
    ws = {w["id"]: w for w in value["workspaces"]}
    windows = {w["id"]: w for w in value["windows"]}
    for w in windows.values():
        fields(w, "id pid workspace_id is_focused is_floating layout")
        if (
            type(w["workspace_id"]) is not int
            or w["workspace_id"] not in ws
            or type(w["pid"]) is not int
            or w["pid"] <= 0
        ):
            raise ValueError("unbound window workspace/process")
        if any(type(w[k]) is not bool for k in ("is_focused", "is_floating")):
            raise ValueError("invalid window booleans")
        layout = w["layout"]
        fields(layout, "pos_in_scrolling_layout tile_size window_size tile_pos_in_workspace_view")
        pos = layout["pos_in_scrolling_layout"]
        if pos is not None and (
            not isinstance(pos, list)
            or len(pos) != 2
            or any(type(n) is not int or n < 1 for n in pos)
        ):
            raise ValueError("invalid tile position")
        if not w["is_floating"] and pos is None:
            raise ValueError("tiled window without position")
        for key in ("tile_size", "window_size", "tile_pos_in_workspace_view"):
            pair = layout[key]
            if pair is not None and (
                not isinstance(pair, list) or len(pair) != 2 or not all(number(n) for n in pair)
            ):
                raise ValueError("invalid recorded geometry")
            if key != "tile_pos_in_workspace_view" and pair is not None and min(pair) <= 0:
                raise ValueError("invalid recorded size")
    for workspace_id in ws:
        columns = {}
        for w in windows.values():
            if w["workspace_id"] == workspace_id and not w["is_floating"]:
                c, t = w["layout"]["pos_in_scrolling_layout"]
                columns.setdefault(c, []).append(t)
        if sorted(columns) != list(range(1, len(columns) + 1)) or any(
            sorted(ts) != list(range(1, len(ts) + 1)) for ts in columns.values()
        ):
            raise ValueError("noncontiguous or duplicate tile positions")
    for w in ws.values():
        fields(w, "id idx output name is_focused is_active active_window_id")
        if (
            type(w["idx"]) is not int
            or not 1 <= w["idx"] <= 255
            or not isinstance(w["output"], str)
            or not w["output"]
        ):
            raise ValueError("invalid workspace output/index")
        if w["name"] is not None and (
            not isinstance(w["name"], str) or not w["name"] or "\0" in w["name"]
        ):
            raise ValueError("invalid workspace name")
        if any(type(w[k]) is not bool for k in ("is_focused", "is_active")) or (
            w["is_focused"] and not w["is_active"]
        ):
            raise ValueError("invalid workspace focus")
        active = w["active_window_id"]
        if active is not None:
            if type(active) is not int or active < 0:
                raise ValueError("invalid active window ID")
            if active not in windows:
                defects.append(("missing-active", w["id"], active))
            elif windows[active]["workspace_id"] != w["id"]:
                defects.append(("foreign-active", w["id"], active))
    for output in {w["output"] for w in ws.values()}:
        indices = sorted(w["idx"] for w in ws.values() if w["output"] == output)
        if indices != list(range(1, len(indices) + 1)):
            raise ValueError("noncontiguous per-output workspace indices")
        if sum(w["is_active"] for w in ws.values() if w["output"] == output) != 1:
            raise ValueError("ambiguous active workspace on output")
    focused_ws = [w for w in ws.values() if w["is_focused"]]
    focused = [w for w in windows.values() if w["is_focused"]]
    if len(focused_ws) != 1 or len(focused) > 1:
        raise ValueError("ambiguous restore focus")
    if focused and (
        focused[0]["workspace_id"] != focused_ws[0]["id"]
        or focused_ws[0]["active_window_id"] != focused[0]["id"]
    ):
        defects.append(("focused-mismatch", focused_ws[0]["id"], focused[0]["id"]))
    outputs = value["outputs"]
    if not isinstance(outputs, list) or len(outputs) > 512:
        raise ValueError("invalid recorded output scales")
    names = []
    for output in outputs:
        fields(output, "name scale")
        if not isinstance(output["name"], str) or (
            output["scale"] is not None and (not number(output["scale"]) or output["scale"] <= 0)
        ):
            raise ValueError("invalid output scale")
        names.append(output["name"])
    if len(set(names)) != len(names) or set(names) != {w["output"] for w in ws.values()}:
        raise ValueError("unbound or duplicate output scales")
    return tuple(defects)


def decode(value):
    defects = validate(value)
    if defects:
        raise ValueError("foreign active window or inconsistent active/focused window")
    return deepcopy(({w["id"]: w for w in value["windows"]}, value["workspaces"], value["outputs"]))


def projected(state):
    value = record(state)
    # Owned tile heights can redistribute during consume; widths are the requested dimension.
    for w in value["windows"]:
        for key in ("tile_size", "window_size"):
            if w["layout"][key] is not None:
                w["layout"][key][1] = 1
        if not w["is_floating"]:
            w["layout"]["tile_pos_in_workspace_view"] = None
    return value


def compatible(expected, actual):
    """Exact windows/focus/metadata except legal empty lifecycle and owned height redistribution."""
    e, a = projected(expected), projected(actual)
    if e["windows"] != a["windows"] or e["outputs"] != a["outputs"]:
        return False
    old, new = {w["id"]: w for w in e["workspaces"]}, {w["id"]: w for w in a["workspaces"]}
    occupied = {w["workspace_id"] for w in a["windows"]}

    def transient(w):
        return (
            w["id"] not in occupied
            and w["name"] is None
            and not w["is_active"]
            and not w["is_focused"]
            and w["active_window_id"] is None
        )

    for wid, w in old.items():
        if wid not in new:
            if not transient(w):
                return False
            peers = sorted(
                (v for v in old.values() if v["output"] == w["output"]), key=lambda v: v["idx"]
            )
            if w == peers[-1] and not (
                len(peers) == 2
                and peers[0]["is_active"]
                and all(v["id"] not in occupied and v["name"] is None for v in peers)
            ):
                return (
                    False  # Niri retains the trailing empty, except all-empty above-first collapse
                )
        elif {k: v for k, v in w.items() if k != "idx"} != {
            k: v for k, v in new[wid].items() if k != "idx"
        }:
            return False
    if {w["output"] for w in old.values()} != {w["output"] for w in new.values()}:
        return False
    for output in {w["output"] for w in old.values()}:
        before = sorted((w for w in old.values() if w["output"] == output), key=lambda w: w["idx"])
        after = sorted((w for w in new.values() if w["output"] == output), key=lambda w: w["idx"])
        if [w["id"] for w in before if w["id"] in new] != [
            w["id"] for w in after if w["id"] in old
        ]:
            return False
        for w in after:
            if w["id"] not in old:
                if not transient(w):
                    return False
                if w == after[-1] and before[-1]["id"] in occupied:
                    continue
                if w == after[0] and before[0]["id"] in occupied:
                    continue
                return False
    return True


def protected(baseline, state, owned):
    before, after = baseline[0], state[0]
    for wid, w in before.items():
        if wid in owned:
            continue
        v = after.get(wid)
        if v is None or any(w.get(k) != v.get(k) for k in ("pid", "workspace_id", "is_floating")):
            raise ValueError("protected window identity changed")
        for key in ("tile_size", "window_size"):
            if w["layout"].get(key) != v["layout"].get(key):
                raise ValueError("protected dimensions changed")
