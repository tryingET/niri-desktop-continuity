"""Exact ten-record historical shell segment and immutable seven-field witness."""

from pathlib import Path

from . import restore_exited_values as v
from . import restore_geometry as geometry
from . import restore_history as history
from . import restore_state as states
from .model import digest
from .restore_disposition_dependencies import artifact, file
from .restore_disposition_evidence import TRUST
from .restore_reader import same

ERROR = {"error_type": "ValueError", "error": "protected dimensions changed"}
REFS = "bootstrap_intent bootstrap_observed exec_intent exec_observed association transfer_intent transfer_observed focus_intent focus_observed".split()


def eligible(active, chain, pending=None):
    start = active["_start"]
    suffix, tracker, plan = chain[start:], active["_launches"], active["plan"]
    if (
        len(suffix) != 10
        or start + 10 >= history.LIMIT
        or pending is not None
        or active.get("_pending") is not None
        or active.get("retained_pending") is not None
        or [r[0]["type"] for r in suffix]
        != [
            "prepared",
            "intent",
            "observed",
            "intent",
            "observed",
            "association",
            "intent",
            "observed",
            "intent",
            "observed",
        ]
        or plan["mode"] != "restore"
        or len(plan["entries"]) != 1
        or set(tracker["launches"]) != {0}
        or set(tracker["associations"]) != {0}
        or tracker["launches"][0]["phase"] != "process-observed"
        or tracker["final"] is not None
        or active["attempt"] in active["_prior_attempts"]
        or active["snapshot_digest"] in active["_prior_sources"]
    ):
        raise ValueError("exact fresh ten-record associated shell segment required")
    entry = plan["entries"][0]
    if (
        entry["recipe"]["kind"] != "shell"
        or entry["floating"] is not False
        or entry["recipe"].get("extra")
        or not same(
            plan["initial_accounting"],
            [{"entry": entry, "window_id": entry["window_id"], "status": "unprocessed"}],
        )
    ):
        raise ValueError("single initially unprocessed tiled shell required")
    v.metadata(plan)
    for name in ("window_id", "saved_workspace_idx", "target_workspace_idx", "column", "tile"):
        if entry[name] is not None:
            v.integer(entry[name])
    launched = tracker["launches"][0]["process"]
    v.process(launched, active["identity"]["boot_id"])
    for prior in active["_prior_processes"]:
        if same({k: prior[k] for k in ("boot_id", "pid", "start_ticks")}, launched):
            raise ValueError("original launch tuple reused")
    v.identity(active["identity"])
    v.key(active["attempt"])
    v.state(plan["baseline"])
    expected_previous = None if start == 0 else digest(chain[start - 1][0])
    for offset, (record, payload, _, _) in enumerate(suffix):
        # ubs:ignore[python.ctcompare.secret_eq] -- History content link, not auth.
        if (
            not same(record["origin"], active["origin"])
            or record["attempt"] != active["attempt"]
            or type(record["seq"]) is not int
            or record["seq"] != start + offset
            or record["previous"] != expected_previous
            or record["receipt"] != digest(payload)
        ):
            raise ValueError("segment envelope binding differs")
        expected_previous = digest(record)
    if suffix[1][1]["action"] != "bootstrap" or suffix[3][1]["action"] != "exec":
        raise ValueError("launch order differs")
    bootstrap = suffix[1][1]["details"]
    v.image(bootstrap["image"])
    v.inode(bootstrap["directory"])
    v.path(bootstrap["spec"]["cwd"])
    v.path(bootstrap["spec"]["argv"][0])
    for p in (
        suffix[2][1]["evidence"]["bootstrap"],
        suffix[3][1]["details"]["process"],
        suffix[4][1]["evidence"]["process"],
    ):
        if not same(p, launched):
            raise ValueError("bootstrap/exec generation mismatch")
    assoc = tracker["associations"][0]
    wid, target = assoc["id"], assoc["target"]
    v.integer(wid)
    v.integer(target)
    for name in ("before", "after"):
        v.state(suffix[5][1][name])
    if type(suffix[5][1]["entry"]) is not int or suffix[5][1]["entry"] != 0:
        raise ValueError("invalid association entry")
    width = entry["width"]
    if type(width) not in (int, float) or not 0 < width <= v.MAX or not same(width, assoc["width"]):
        raise ValueError("positive requested and observed width must agree")
    transfer, focus = suffix[6][1], suffix[8][1]
    before = v.state(transfer["details"]["before"])
    address = next(w for w in before[1] if w["id"] == target)
    commands = [
        [
            "move-window-to-workspace",
            "--window-id",
            str(wid),
            "--focus",
            "false",
            str(address["idx"]),
        ],
        ["focus-window", "--id", str(wid)],
    ]
    if (
        before[0][wid]["is_floating"]
        or before[0][wid]["workspace_id"] == target
        or [wid] not in geometry.groups(before[0], before[0][wid]["workspace_id"])
    ):
        raise ValueError("actual tiled singleton workspace transfer required")
    for offset, intent, command, expected_target in (
        (
            6,
            transfer,
            commands[0],
            {"workspace_id": target, "output": address["output"], "index": address["idx"]},
        ),
        (8, focus, commands[1], None),
    ):
        details = intent["details"]
        if (
            intent["action"] != "layout"
            or not same(details["argv"], command)
            or not same(details["target"], expected_target)
            or details["measured_float"] is not None
        ):
            raise ValueError("only exact workspace-transfer then owned-focus admitted")
        v.state(details["before"])
        v.state(details["expected"])
        observed = v.state(suffix[offset + 1][1]["evidence"]["layout"])
        owned = observed[0][wid]
        if (
            owned["workspace_id"] != target
            or owned["is_floating"]
            or not same(owned["layout"]["tile_size"][0], width)
            or (offset == 8 and owned["is_focused"] is not True)
        ):
            raise ValueError("observed target/focus/requested width differs")
    if not same(tracker["effects"], commands):
        raise ValueError("two exact observed effects required")
    return {
        "start": start,
        "count": 10,
        "previous": suffix[0][0]["previous"],
        **{name: suffix[i][0]["receipt"] for i, name in enumerate(REFS, 1)},
        "process_receipt": digest(suffix[4][1]["evidence"]),
        "baseline_digest": digest(plan["baseline"]),
    }


def witness(store, active, interrupted, result_path, exit_path):
    receipt, rp = artifact(store, "receipts", interrupted)
    states.fields(
        receipt, "status windows effects final_observation native_session error_type error"
    )
    rows = receipt["windows"]
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("exact one-row original witness required")
    states.fields(
        rows[0],
        "entry window_id status geometry_coverage process_receipt restored_window_id observed_initial_width target_workspace_id",
    )
    entry, tracker = active["plan"]["entries"][0], active["_launches"]
    assoc = tracker["associations"][0]
    expected = {
        "entry": entry,
        "window_id": entry["window_id"],
        "status": "owned-not-placed",
        "geometry_coverage": {"width": "requested-observed", "position": "not-recorded"},
        "process_receipt": tracker["launches"][0]["receipt"],
        "restored_window_id": assoc["id"],
        "observed_initial_width": assoc["width"],
        "target_workspace_id": assoc["target"],
    }
    if (
        not same(rows[0], expected)
        or receipt["status"] != "interrupted"
        or receipt["native_session"] != "not-proved"
        or any(receipt[k] != val for k, val in ERROR.items())
        or not same(receipt["effects"], tracker["effects"])
    ):
        raise ValueError("exact original legacy protected-dimension witness required")
    if not same(receipt["final_observation"], {"unavailable": True}):
        v.state(receipt["final_observation"])
    result_path, exit_path = Path(v.path(str(result_path))), Path(v.path(str(exit_path)))
    if result_path == exit_path or result_path.parent != exit_path.parent:
        raise ValueError("distinct original files must share original private directory")
    result, result_pin = file(store, result_path)
    exit_bytes, exit_pin = file(store, exit_path, raw=True)
    if (
        not same(
            result,
            {
                "snapshot_digest": active["snapshot_digest"],
                "receipt_digest": interrupted,
                **receipt,
            },
        )
        or exit_bytes != b"2\n"
    ):
        raise ValueError("original client result/exit mismatch")
    return {
        "interrupted": rp,
        "client_result": result_pin,
        "client_exit": exit_pin,
        "error_signature": ERROR,
        "trust": TRUST,
    }


def binding(store, active, chain, interrupted, result_path, exit_path):
    segment = eligible(active, chain)
    if not same(
        active["origin"], {"root": str(store.root), "pin": history.directory_pin(store.root)}
    ):
        raise ValueError("original Store required")
    source = store.get("snapshots", active["snapshot_digest"])
    v.source_valid(source, active["identity"])
    return {
        "family": v.FAMILY,
        "branch": v.BRANCH,
        "attempt": active["attempt"],
        "identity": active["identity"],
        "origin": active["origin"],
        "history_count": len(chain),
        "history_tail": digest(chain[-1][0]),
        "manifest": active["_prefix_pins"],
        "prepared": chain[segment["start"]][0]["receipt"],
        "snapshot": active["snapshot_digest"],
        "segment": segment,
        "witness": witness(store, active, interrupted, result_path, exit_path),
    }
