"""Semantically closed subordinate records; hashes alone do not certify transitions."""

from copy import deepcopy

from . import restore_geometry as geometry
from . import restore_state as states
from .model import digest
from .restore_plan import prepared, terminal  # noqa: F401 - shared history API
from .store import HEX


def fields(value, expected):
    states.fields(value, expected)


def pin(value):
    fields(value, "pid boot_id start_ticks")
    if (
        not isinstance(value["boot_id"], str)
        or not value["boot_id"]
        or any(type(value[k]) is not int or value[k] <= 0 for k in ("pid", "start_ticks"))
    ):
        raise ValueError("invalid process pin")


def intent(payload, plan, tracker):
    if tracker["final"] is not None:
        raise ValueError("effect after final observation")
    fields(payload, "action details")
    action, details = payload["action"], payload["details"]
    launches = tracker["launches"]
    if action == "layout":
        if plan["mode"] != "restore":
            raise ValueError("probe cannot grant layout")
        fields(details, "argv before expected measured_float target")
        argv = details["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise ValueError("invalid effect argv")
        before, expected = states.decode(details["before"]), states.decode(details["expected"])
        if not states.compatible(tracker["state"], before):
            raise ValueError("layout intent differs from last observation")
        predicted = geometry.transition(
            before, argv, tracker["owned"], tracker["births"], tracker["initial_focus"]
        )
        target = details["target"]
        if target is not None:
            fields(target, "workspace_id output index")
            if (
                type(target["workspace_id"]) is not int
                or type(target["index"]) is not int
                or not isinstance(target["output"], str)
            ):
                raise ValueError("invalid workspace reference")
        if target != geometry.address(before, argv):
            raise ValueError("workspace reference differs from recorded command binding")
        if states.projected(predicted) != states.projected(expected):
            raise ValueError("layout prediction inconsistent with action")
        measured = int(argv[2]) if argv[0] == "move-window-to-floating" else None
        if details["measured_float"] != measured:
            raise ValueError("unbound floating measurement")
        states.protected(tracker["baseline"], before, set())
        return
    if action not in {"bootstrap", "exec"}:
        raise ValueError("unknown restore effect")
    fields(
        details,
        "entry nonce spec image directory" if action == "bootstrap" else "entry process binding",
    )
    index = details["entry"]
    if type(index) is not int or not 0 <= index < len(plan["entries"]):
        raise ValueError("unbound launch entry")
    if action == "bootstrap":
        if index in launches:
            raise ValueError("duplicate subordinate launch")
        if (
            plan["mode"] == "restore"
            and plan["initial_accounting"][index]["status"] != "unprocessed"
        ):
            raise ValueError("launch of frozen no-effect entry")
        fields(details["spec"], "argv cwd")
        if details["spec"] != {k: plan["entries"][index]["recipe"][k] for k in ("argv", "cwd")}:
            raise ValueError("bootstrap differs from frozen controlled spec")
        fields(details["image"], "device inode sha256")
        fields(details["directory"], "device inode")
        for obj in (details["image"], details["directory"]):
            if any(type(obj[k]) is not int or obj[k] < 0 for k in ("device", "inode")):
                raise ValueError("invalid executable/directory pin")
        if not HEX.fullmatch(details["nonce"]) or not HEX.fullmatch(details["image"]["sha256"]):
            raise ValueError("invalid launch digest")
        launches[index] = {"phase": "bootstrap-intent"}
    else:
        pin(details["process"])
        if (
            launches.get(index, {}).get("phase") != "bootstrap-observed"
            or details["process"] != launches[index]["process"]
            or details["binding"] != launches[index]["binding"]
        ):
            raise ValueError("exec without exact observed bootstrap")
        launches[index]["phase"] = "exec-intent"


def observed(payload, pending, tracker):
    fields(payload, "intent evidence")
    evidence, action, details = payload["evidence"], pending["action"], pending["details"]
    launches = tracker["launches"]
    if action == "layout":
        fields(evidence, "layout")
        actual, expected = states.decode(evidence["layout"]), states.decode(details["expected"])
        measured = details["measured_float"]
        if measured is not None:
            pos = actual[0][measured]["layout"]["tile_pos_in_workspace_view"]
            if not isinstance(pos, list) or len(pos) != 2 or not all(states.number(n) for n in pos):
                raise ValueError("floating conversion lacks measured position")
            expected[0][measured]["layout"]["tile_pos_in_workspace_view"] = deepcopy(pos)
        if not states.compatible(expected, actual):
            raise ValueError("observed layout differs from intended transition")
        states.protected(tracker["baseline"], actual, set())
        tracker["state"] = actual
        tracker["effects"].append(details["argv"])
    elif action == "bootstrap":
        fields(evidence, "bootstrap binding")
        pin(evidence["bootstrap"])
        if evidence["bootstrap"]["boot_id"] != tracker["boot_id"] or not HEX.fullmatch(
            evidence["binding"]
        ):
            raise ValueError("foreign bootstrap binding")
        launches[details["entry"]] = {
            "phase": "bootstrap-observed",
            "process": evidence["bootstrap"],
            "binding": evidence["binding"],
        }
    else:
        fields(
            evidence,
            "phase ownership process binding window_ownership placement native_session settlement",
        )
        expected = {
            "phase": "process-observed",
            "ownership": "process-only",
            "process": details["process"],
            "binding": details["binding"],
            "window_ownership": "not-proved",
            "placement": "not-attempted",
            "native_session": "not-proved",
            "settlement": "unresolved",
        }
        if evidence != expected:
            raise ValueError("invalid process observation")
        launches[details["entry"]].update(phase="process-observed", receipt=digest(evidence))


def final_observed(payload, plan, tracker):
    fields(payload, "state")
    value = states.decode(payload["state"])
    if (
        plan["mode"] != "restore"
        or tracker["final"] is not None
        or not states.compatible(tracker["state"], value)
    ):
        raise ValueError("invalid final observation")
    states.protected(tracker["baseline"], value, set())
    tracker["final"] = deepcopy(payload["state"])


def association(payload, plan, tracker):
    if tracker["final"] is not None:
        raise ValueError("association after final observation")
    fields(payload, "entry before after")
    index = payload["entry"]
    launch = tracker["launches"].get(index)
    if (
        plan["mode"] != "restore"
        or launch is None
        or launch["phase"] != "process-observed"
        or index in tracker["associations"]
    ):
        raise ValueError("unbound or repeated window association")
    before, after = states.decode(payload["before"]), states.decode(payload["after"])
    if not states.compatible(tracker["state"], before):
        raise ValueError("association baseline differs from recorded observation")
    wid, previous = geometry.associate(before, after, launch["process"]["pid"])
    tracker["owned"].add(wid)
    tracker["births"][wid] = previous
    tracker["state"] = after
    output = next(ws["output"] for ws in tracker["baseline"][1] if ws["is_focused"])
    anchor = min(
        (ws for ws in tracker["baseline"][1] if ws["output"] == output), key=lambda ws: ws["idx"]
    )["id"]
    tracker["associations"][index] = {
        "id": wid,
        "width": (after[0][wid]["layout"].get("tile_size") or [None])[0],
        "target": geometry.target(
            after,
            plan["entries"][index]["target_workspace_idx"],
            tracker["targets"],
            output,
            anchor,
        ),
    }
