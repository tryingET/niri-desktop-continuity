"""Pure Niri cohort/activation transitions, shared by execution and retained validation."""

from copy import deepcopy

from . import restore_dimensions as dimensions
from . import restore_state as state


def groups(windows, workspace):
    columns = {}
    for w in windows.values():
        if w["workspace_id"] == workspace and not w["is_floating"]:
            c, t = w["layout"]["pos_in_scrolling_layout"]
            columns.setdefault(c, []).append((t, w["id"]))
    return [[wid for _, wid in sorted(columns[c])] for c in sorted(columns)]


def reindex(windows, workspace, columns):
    for c, tiles in enumerate(columns, 1):
        for t, wid in enumerate(tiles, 1):
            windows[wid]["workspace_id"] = workspace
            windows[wid]["layout"]["pos_in_scrolling_layout"] = [c, t]


def workspace(value, wid):
    return next(w for w in value[1] if w["id"] == wid)


def focus(value, wid):
    target = value[0][wid]["workspace_id"]
    output = workspace(value, target)["output"]
    for w in value[0].values():
        w["is_focused"] = w["id"] == wid
    for ws in value[1]:
        ws["is_focused"] = ws["id"] == target
        if ws["output"] == output:
            ws["is_active"] = ws["id"] == target
        if ws["id"] == target:
            ws["active_window_id"] = wid


def insertion(value, ws):
    columns = groups(value[0], ws)
    if not columns:
        return 0
    active = workspace(value, ws)["active_window_id"]
    for n, col in enumerate(columns):
        if active in col:
            return n + 1
    raise ValueError("scrolling active column is unavailable")


def associate(before, after, pid):
    matches = [w for w in after[0].values() if w["pid"] == pid]
    if len(matches) != 1 or any(w["pid"] == pid for w in before[0].values()):
        raise ValueError("missing, shared or surplus owned host")
    new = matches[0]
    wid, ws = new["id"], new["workspace_id"]
    if wid in before[0] or set(after[0]) != set(before[0]) | {wid} or new["is_floating"]:
        raise ValueError("unowned arrival, overlap or unsupported initial floating host")
    expected = deepcopy(before)
    target = workspace(expected, ws)
    if not target["is_focused"]:
        raise ValueError("launch mapped outside the admitted focused workspace")
    previous = target["active_window_id"]
    columns = groups(expected[0], ws)
    index = insertion(expected, ws)
    columns.insert(index, [wid])
    expected[0][wid] = deepcopy(new)
    reindex(expected[0], ws, columns)
    if new["is_focused"]:
        focus(expected, wid)
    elif previous is None:
        target["active_window_id"] = wid
    if not state.compatible(expected, after):
        raise ValueError("launch changed protected topology or foreign focus")
    state.protected(before, after, set())
    return wid, previous


def move(before, wid, target, previous):
    expected = deepcopy(before)
    w = expected[0][wid]
    source = w["workspace_id"]
    columns = groups(expected[0], source)
    if [wid] not in columns:
        raise ValueError("workspace donor must be a singleton")
    dest = groups(expected[0], target)
    dest.insert(insertion(expected, target), [wid])
    columns.remove([wid])
    source_ws, target_ws = workspace(expected, source), workspace(expected, target)
    if source_ws["active_window_id"] == wid:
        if previous is not None and (
            previous not in expected[0] or expected[0][previous]["workspace_id"] != source
        ):
            raise ValueError("source activation pin unavailable")
        if previous is None and columns:
            raise ValueError("source removal activation is not observed")
        source_ws["active_window_id"] = previous
    if w["is_focused"]:
        w["is_focused"] = False
        if previous is not None:
            expected[0][previous]["is_focused"] = True
    if target_ws["active_window_id"] is None:
        target_ws["active_window_id"] = wid
    reindex(expected[0], source, columns)
    reindex(expected[0], target, dest)
    return expected


def target(value, idx, bindings, output, anchor=None):
    if idx in bindings:
        if any(w["id"] == bindings[idx] for w in value[1]):
            return bindings[idx]
        raise ValueError("bound logical workspace disappeared")
    ordered = sorted((w for w in value[1] if w["output"] == output), key=lambda w: w["idx"])
    anchors = dict(bindings)
    if 1 not in anchors and any(w["id"] == anchor for w in ordered):
        anchors[1] = anchor  # original first workspace survives optional empty-above insertion
    if idx in anchors:
        bindings[idx] = anchors[idx]
        return bindings[idx]
    previous = max((i for i in anchors if i < idx), default=None)
    rank = (
        idx - 1
        if previous is None
        else next(n for n, w in enumerate(ordered) if w["id"] == anchors[previous]) + idx - previous
    )
    if rank >= len(ordered):
        raise ValueError("next logical workspace has not materialized")
    bindings[idx] = ordered[rank]["id"]
    return bindings[idx]


def address(value, argv):
    if argv[0] == "move-window-to-workspace":
        source = workspace(value, value[0][int(argv[2])]["workspace_id"])
        output, index = source["output"], int(argv[-1])
    elif argv[0] == "set-workspace-name":
        focused = [ws for ws in value[1] if ws["is_focused"]]
        if len(focused) != 1:
            raise ValueError("ambiguous addressing output")
        output, index = focused[0]["output"], int(argv[2])
    else:
        return None
    matches = [ws for ws in value[1] if ws["output"] == output and ws["idx"] == index]
    if len(matches) != 1:
        raise ValueError("ambiguous workspace reference")
    return {"workspace_id": matches[0]["id"], "output": output, "index": index}


def transition(before, argv, owned, births, initial_focus):
    """Predict only the admitted closed action set; lifecycle/float measurement is separate."""
    expected = deepcopy(before)
    windows = expected[0]
    focused = next((w["id"] for w in windows.values() if w["is_focused"]), None)
    name = argv[0]

    def cohort(wid):
        col = next(g for g in groups(windows, windows[wid]["workspace_id"]) if wid in g)
        if not set(col) <= owned:
            raise ValueError("unowned action cohort")
        return col

    if name == "focus-window" and len(argv) == 3 and argv[1] == "--id":
        wid = int(argv[2])
        if wid not in owned and wid != initial_focus:
            raise ValueError("unadmitted focus")
        focus(expected, wid)
    elif (
        name == "move-window-to-workspace"
        and len(argv) == 6
        and argv[1] == "--window-id"
        and argv[3:5] == ["--focus", "false"]
    ):
        wid = int(argv[2])
        if wid not in owned:
            raise ValueError("unowned workspace donor")
        target = address(before, argv)["workspace_id"]
        expected = move(before, wid, target, births[wid])
    elif name == "move-column-to-index" and len(argv) == 2:
        if not 1 <= int(argv[1]) <= 512:
            raise ValueError("invalid column index")
        tiles = cohort(focused)
        ws = windows[focused]["workspace_id"]
        columns = groups(windows, ws)
        columns.remove(tiles)
        columns.insert(max(0, min(int(argv[1]) - 1, len(columns))), tiles)
        reindex(windows, ws, columns)
    elif name == "consume-window-into-column" and len(argv) == 1:
        tiles = cohort(focused)
        ws = windows[focused]["workspace_id"]
        columns = groups(windows, ws)
        n = columns.index(tiles)
        donor = columns[n + 1]
        if len(donor) != 1 or donor[0] not in owned:
            raise ValueError("unowned right donor")
        columns[n].extend(columns.pop(n + 1))
        reindex(windows, ws, columns)
        for field in ("tile_size", "window_size"):
            windows[donor[0]]["layout"][field][0] = windows[focused]["layout"][field][0]
    elif name == "set-column-width" and len(argv) == 2:
        width = dimensions.fixed_width(argv[1])
        for wid in cohort(focused):
            layout = windows[wid]["layout"]
            decoration = layout["tile_size"][0] - layout["window_size"][0]
            layout["tile_size"][0] = dimensions.resized_tile(width, decoration)
            layout["window_size"][0] = width
    elif name == "move-window-to-floating" and len(argv) == 3 and argv[1] == "--id":
        wid = int(argv[2])
        if cohort(wid) != [wid]:
            raise ValueError("floating donor not singleton")
        w = windows[wid]
        ws = w["workspace_id"]
        columns = [g for g in groups(windows, ws) if g != [wid]]
        w["is_floating"] = True
        w["layout"]["pos_in_scrolling_layout"] = None
        w["layout"]["tile_pos_in_workspace_view"] = None
        reindex(windows, ws, columns)
    elif (
        name == "move-floating-window"
        and len(argv) == 7
        and argv[1] == "--id"
        and argv[3] == "-x"
        and argv[5] == "-y"
    ):
        wid = int(argv[2])
        if wid not in owned or not windows[wid]["is_floating"]:
            raise ValueError("unowned float")
        pos = windows[wid]["layout"]["tile_pos_in_workspace_view"]
        for i, arg in enumerate((argv[4], argv[6])):
            if not arg.startswith(("+", "-")):
                raise ValueError("relative floating delta required")
            pos[i] += float(arg)
        windows[wid]["layout"]["tile_pos_in_workspace_view"] = dimensions.quantize(
            pos, dimensions.output_scale(before, wid)
        )
    elif name == "set-workspace-name" and len(argv) == 4 and argv[1] == "--workspace":
        output = next(ws["output"] for ws in before[1] if ws["is_focused"])
        ws = next(ws for ws in expected[1] if ws["idx"] == int(argv[2]) and ws["output"] == output)
        if (
            ws["name"]
            or any(w["workspace_id"] == ws["id"] and w["id"] not in owned for w in windows.values())
            or any(w["name"] == argv[3] for w in before[1])
        ):
            raise ValueError("protected or conflicting workspace name")
        ws["name"] = argv[3]
    else:
        raise ValueError("unknown layout transition")
    return expected
