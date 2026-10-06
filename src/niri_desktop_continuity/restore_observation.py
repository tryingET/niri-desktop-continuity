"""Association-only classification of a narrow split read; never a repaired state.

Every sample is whole and independent. Polling cannot detect events entirely between samples.
"""

import sys
from copy import deepcopy

from . import restore_state as states


def pending_reference(value, before):
    """Return the sole eligible (window, workspace) pending ref, or None for strict input.

    All independent validation completes before relational defects can be classified.
    No decoded state is returned for defective input; other callers remain strict.
    """
    defects = states.validate(value)
    if not defects:
        return None
    original = states.record(before)
    if value["windows"] != original["windows"] or value["outputs"] != original["outputs"]:
        raise ValueError("split observation changed windows or outputs")
    focused = next(w for w in original["workspaces"] if w["is_focused"])
    missing = [d for d in defects if d[0] == "missing-active"]
    if len(missing) != 1 or missing[0][1] != focused["id"]:
        raise ValueError("ineligible missing active reference")
    _, workspace, wid = missing[0]
    allowed = {missing[0]}
    old_focus = [w for w in original["windows"] if w["is_focused"]]
    if old_focus:
        allowed.add(("focused-mismatch", workspace, old_focus[0]["id"]))
    if set(defects) != allowed or wid in before[0]:
        raise ValueError("ineligible relational defects")
    expected = [dict(w) for w in original["workspaces"]]
    next(w for w in expected if w["id"] == workspace)["active_window_id"] = wid
    if value["workspaces"] != expected:
        raise ValueError("split workspace metadata changed")
    return wid, workspace


def output_inventory(outputs):
    """Freeze all outputs, including disabled ones, independently of the state schema.

    Outer output order/mapping keys and JSON object key order are not identity. All
    entry metadata is retained conservatively; field presence and ordered arrays matter.
    """
    entries = list(outputs.values()) if isinstance(outputs, dict) else outputs
    if not isinstance(entries, list) or len(entries) > 512:
        raise ValueError("invalid association outputs")
    budget = [65536]

    def bounded(value, depth=0):
        budget[0] -= 1
        if budget[0] < 0 or depth > 8:
            raise ValueError("output inventory exceeds bound")
        if value is None or type(value) is bool:
            return
        if type(value) is int:
            if abs(value) > int(sys.float_info.max):
                raise ValueError("output metadata integer exceeds finite numeric range")
            return
        if type(value) is float and states.number(value):
            return
        if isinstance(value, str) and len(value) <= 4096 and "\0" not in value:
            return
        if isinstance(value, dict) and len(value) <= 512:
            if not all(isinstance(k, str) for k in value):
                raise ValueError("invalid output metadata key")
            for key, item in value.items():
                bounded(key, depth + 1)
                bounded(item, depth + 1)
            return
        if isinstance(value, list) and len(value) <= 512:
            for item in value:
                bounded(item, depth + 1)
            return
        raise ValueError("invalid output metadata")

    names = []
    for output in entries:
        bounded(output)
        if (
            not isinstance(output, dict)
            or not isinstance(output.get("name"), str)
            or not output["name"]
        ):
            raise ValueError("invalid association output")
        logical = output.get("logical")
        if logical is not None and not isinstance(logical, dict):
            raise ValueError("invalid association output geometry")
        scale = (logical or {}).get("scale")
        if scale is not None and (not states.number(scale) or scale <= 0):
            raise ValueError("invalid association output scale")
        for key in ("x", "y", "width", "height"):
            if (
                logical is not None
                and key in logical
                and (
                    type(logical[key]) is not int
                    or (key in {"width", "height"} and logical[key] <= 0)
                )
            ):
                raise ValueError("invalid output logical geometry")
        for key in ("make", "model", "serial"):
            if output.get(key) is not None and not isinstance(output[key], str):
                raise ValueError("invalid output identity metadata")
        for key in ("vrr_supported", "vrr_enabled"):
            if key in output and type(output[key]) is not bool:
                raise ValueError("invalid output VRR flag")
        physical = output.get("physical_size")
        if physical is not None and (
            not isinstance(physical, list)
            or len(physical) != 2
            or any(type(n) is not int or n < 0 for n in physical)
        ):
            raise ValueError("invalid output physical size")
        if (
            logical is not None
            and "transform" in logical
            and (not isinstance(logical["transform"], str) or not logical["transform"])
        ):
            raise ValueError("invalid output transform")
        modes = output.get("modes")
        if modes is not None:
            if not isinstance(modes, list):
                raise ValueError("invalid output modes")
            for entry in modes:
                if (
                    not isinstance(entry, dict)
                    or any(
                        type(entry.get(k)) is not int or entry[k] < 0
                        for k in ("width", "height", "refresh_rate")
                    )
                    or ("is_preferred" in entry and type(entry["is_preferred"]) is not bool)
                ):
                    raise ValueError("invalid output mode")
        mode = output.get("current_mode")
        if mode is not None and (type(mode) is not int or mode < 0):
            raise ValueError("invalid output mode reference")
        if mode is not None and modes is not None and mode >= len(modes):
            raise ValueError("unbound output mode reference")
        names.append(output["name"])
    if len(names) != len(set(names)):
        raise ValueError("duplicate association output")
    return deepcopy(sorted(entries, key=lambda o: o["name"]))


def same_metadata(a, b):
    """JSON numeric equality without Python's bool/int alias; order only within arrays."""
    if type(a) in (int, float) and type(b) in (int, float):
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same_metadata(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same_metadata(x, y) for x, y in zip(a, b, strict=True))
    return a == b


def check_outputs(outputs, original):
    if not same_metadata(output_inventory(outputs), original):
        raise ValueError("association outputs changed")
