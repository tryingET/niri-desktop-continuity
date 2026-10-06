"""Requested dimensions, shared-column policy and observable physical-pixel targets."""

import math
import re

from . import restore_state as states


def fixed_width(token):
    """Admitted SetFixed(i32), not signed AdjustFixed or percentage SizeChange.

    Pinned niri-ipc/src/lib.rs (62c230a): SizeChange / FromStr, 948–960 / 1784–1822.
    Zero parses natively but is not an admitted positive window-width request.
    """
    if not isinstance(token, str) or not re.fullmatch(r"[0-9]+", token):
        raise ValueError("positive fixed integer width token required")
    width = int(token)
    if not 1 <= width <= 2**31 - 1:
        raise ValueError("fixed integer width outside positive i32 range")
    return width


def resized_tile(width, decoration):
    # scrolling.rs 4999–5013 clamps the reconstructed tile, not just the window.
    tile = width + decoration
    if not states.number(decoration) or decoration < 0 or not 1 <= tile <= 100000:
        raise ValueError("fixed integer width would exceed native tile range")
    # tile.rs 938–958 subtracts the border then floors the Wayland size request.
    # Exact addition alone is insufficient if that inverse falls just below the integer.
    if math.floor(max(1.0, tile - decoration)) != width:
        raise ValueError("fixed integer width cannot survive native window-size floor")
    return tile


def width_token(tile, window, desired):
    """Find an integer candidate, then prove exact observable reconstruction.

    Subtraction can lose an ulp even when integer + measured decoration exactly
    reconstructs the saved float. Rounding selects a candidate ONLY: equality below,
    never a tolerance or rounded requested tile, supplies the admission proof.
    Native constraints/hidden decoration can still fail the strict postcondition.
    """
    if not all(states.number(n) and n > 0 for n in (tile, window, desired)) or tile < window:
        raise ValueError("unknown tile/window decorations or width")
    decoration = tile - window
    token = str(round(desired - decoration))
    candidate = fixed_width(token)
    if resized_tile(candidate, decoration) != desired:
        raise ValueError("fixed integer width cannot reconstruct requested tile exactly")
    return token


def policies(plan):
    groups = {}
    for i, (entry, row) in enumerate(zip(plan["entries"], plan["initial_accounting"], strict=True)):
        if row["status"] != "unprocessed":
            continue
        key = (
            (entry["target_workspace_idx"], entry["column"])
            if not entry["floating"] and entry["column"] is not None
            else ("single", i)
        )
        groups.setdefault(key, []).append(i)
    result = {}
    for members in groups.values():
        widths = {
            plan["entries"][i]["width"] for i in members if plan["entries"][i]["width"] is not None
        }
        if len(widths) > 1:
            raise ValueError("conflicting recorded widths in one saved column")
        explicit = next(iter(widths), None)
        for i in members:
            origin = (
                "requested"
                if plan["entries"][i]["width"] is not None
                else ("inherited" if explicit is not None or i != members[0] else "preserved")
            )
            result[i] = {"seed": members[0], "explicit": explicit, "origin": origin}
    return result


def width_target(policy, initial):
    return policy["explicit"] if policy["explicit"] is not None else initial[policy["seed"]]


def width_coverage(policy, observed):
    return {
        "requested": "requested-observed" if observed else "requested-pending",
        "inherited": "inherited-column" if observed else "inherited-pending",
        "preserved": "not-recorded-preserved" if observed else "not-recorded",
    }[policy["origin"]]


def output_scale(value, wid):
    wsid = value[0][wid]["workspace_id"]
    output = next(w["output"] for w in value[1] if w["id"] == wsid)
    scale = next((o["scale"] for o in value[2] if o["name"] == output), None)
    if not states.number(scale) or scale <= 0:
        raise ValueError("known current output scale required for floating position proof")
    return scale


def quantize(position, scale):
    if (
        not states.number(scale)
        or scale <= 0
        or not isinstance(position, list)
        or len(position) != 2
    ):
        raise ValueError("invalid floating pixel grid")
    result = []
    for coordinate in position:
        if not states.number(coordinate) or not states.number(coordinate * scale):
            raise ValueError("invalid floating coordinate")
        physical = coordinate * scale
        whole = math.floor(abs(physical))
        # Rust f64::round: ties away from zero, not Python's ties-to-even. Do not add .5:
        # that addition can itself round a just-below-half value up to an integer.
        rounded = math.copysign(whole + (abs(physical) - whole >= 0.5), physical)
        result.append(rounded / scale)
    return result


def position_target(entry, value, wid):
    requested = entry["floating_position"]
    return quantize(requested, output_scale(value, wid))


def position_coverage(entry, value, wid):
    if not entry["floating"] or entry["floating_position"] is None:
        return "not-recorded"
    window = value[0][wid]
    if not window["is_floating"]:
        return "requested-pending"
    try:
        target = position_target(entry, value, wid)
    except ValueError:
        return "requested-pending"
    if window["layout"]["tile_pos_in_workspace_view"] != target:
        return "requested-pending"
    return (
        "requested-observed"
        if target == entry["floating_position"]
        else "requested-quantized-observed"
    )


def pending(entry, policy):
    return {
        "width": width_coverage(policy, False),
        "position": "requested-pending"
        if entry["floating"] and entry["floating_position"] is not None
        else "not-recorded",
    }


def observe(plan, rows, value):
    policy = policies(plan)
    initial = {
        i: r["observed_initial_width"] for i, r in enumerate(rows) if "observed_initial_width" in r
    }
    for i, row in enumerate(rows):
        wid = row.get("restored_window_id")
        if wid is None or wid not in value[0] or i not in initial:
            continue
        width = width_target(policy[i], initial)
        actual = (value[0][wid]["layout"].get("tile_size") or [None])[0]
        row["geometry_coverage"] = {
            "width": width_coverage(policy[i], width is not None and width == actual),
            "position": position_coverage(row["entry"], value, wid),
        }
