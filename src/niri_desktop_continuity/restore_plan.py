"""Offline validation of frozen admission, independent of later host/cwd availability."""

from copy import deepcopy
from pathlib import PurePosixPath

from . import restore_dimensions as dimensions
from . import restore_state as states
from .restore_host import FLAGS, KINDS


def controlled(recipe, spec):
    states.fields(spec, "argv cwd")
    argv, cwd = recipe.get("argv"), recipe.get("cwd")
    if (
        recipe.get("kind") not in KINDS
        or not isinstance(argv, list)
        or not argv
        or not all(isinstance(a, str) and "\0" not in a for a in argv)
    ):
        raise ValueError("invalid frozen host recipe")
    if not isinstance(cwd, str) or not PurePosixPath(cwd).is_absolute() or "\0" in cwd:
        raise ValueError("invalid frozen directory")
    host = spec["argv"][0]
    if (
        not isinstance(host, str)
        or not PurePosixPath(host).is_absolute()
        or PurePosixPath(host).name != "ghostty"
        or PurePosixPath(argv[0]).name != "ghostty"
    ):
        raise ValueError("invalid frozen host executable")
    boundary = argv.index("-e") if "-e" in argv else len(argv)
    if any(a not in FLAGS and a != f"--working-directory={cwd}" for a in argv[1:boundary]):
        raise ValueError("conflicting frozen host options")
    tail = argv[boundary:]
    if (recipe["kind"] == "shell" and tail) or (
        recipe["kind"] != "shell" and (len(tail) < 2 or not tail[1])
    ):
        raise ValueError("invalid frozen command tail")
    if spec != {"argv": [host, *FLAGS, f"--working-directory={cwd}", *tail], "cwd": cwd}:
        raise ValueError("frozen spec changes literal command")


def prepared(plan, snapshot, identity):
    mode = plan.get("mode")
    if mode == "process-probe":
        states.fields(plan, "mode entries")
        if not isinstance(plan["entries"], list) or len(plan["entries"]) != 1:
            raise ValueError("invalid standalone probe plan")
        recipe = plan["entries"][0]["recipe"]
        controlled(recipe, {"argv": recipe["argv"], "cwd": recipe["cwd"]})
        baseline = None
    elif mode == "restore":
        states.fields(
            plan,
            "mode entries workspace_names protected_window_ids unknown_workspace_idx source_plan baseline baseline_recipes initial_accounting",
        )
        baseline = states.decode(plan["baseline"])
        recipes = plan["baseline_recipes"]
        if not isinstance(recipes, list) or len(recipes) != len(baseline[0]):
            raise ValueError("incomplete baseline recipe evidence")
        ids = []
        current = deepcopy(list(baseline[0].values()))
        for row in recipes:
            states.fields(row, "id recipe")
            if row["id"] not in baseline[0]:
                raise ValueError("foreign baseline recipe")
            ids.append(row["id"])
            next(w for w in current if w["id"] == row["id"])["reopen"] = row["recipe"]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate baseline recipe")
        from .restore import plan_restore

        source = plan_restore(snapshot, current, baseline[1])
        if plan["source_plan"] != source or len(plan["entries"]) != len(source["entries"]):
            raise ValueError("frozen plan differs from source and coherent baseline")
        for key in ("workspace_names", "protected_window_ids", "unknown_workspace_idx"):
            if plan[key] != source[key]:
                raise ValueError("frozen plan metadata changed")
        rows = plan["initial_accounting"]
        if not isinstance(rows, list) or len(rows) != len(source["entries"]):
            raise ValueError("incomplete initial accounting")
        for row, entry, original in zip(rows, plan["entries"], source["entries"], strict=True):
            status = row.get("status")
            states.fields(
                row,
                "entry window_id status reason"
                if status == "unsupported"
                else "entry window_id status",
            )
            if row["entry"] != entry or row["window_id"] != entry["window_id"]:
                raise ValueError("initial accounting differs from frozen entry")
            if original.get("status") == "already-open":
                if status != "already-open" or entry != original:
                    raise ValueError("baseline already-open classification changed")
            elif status == "unsupported":
                if entry != original or not isinstance(row["reason"], str) or not row["reason"]:
                    raise ValueError("unsupported classification not frozen before effects")
            elif status == "unprocessed":
                spec = {k: entry["recipe"][k] for k in ("argv", "cwd")}
                controlled(original["recipe"], spec)
                expected = deepcopy(original)
                expected["recipe"].update(spec)
                if entry != expected:
                    raise ValueError("unbound controlled recipe")
            else:
                raise ValueError("unknown initial classification")
        dimensions.policies(plan)
    else:
        raise ValueError("unknown or legacy prepared restore mode")
    return {
        "state": baseline,
        "baseline": baseline,
        "launches": {},
        "owned": set(),
        "births": {},
        "effects": [],
        "initial_focus": next((w["id"] for w in baseline[0].values() if w["is_focused"]), None)
        if baseline
        else None,
        "boot_id": identity["boot_id"],
        "associations": {},
        "targets": {},
        "final": None,
    }


def terminal(receipt, plan, evidence):
    if plan["mode"] != "restore":
        raise ValueError("standalone process probe cannot settle")
    final = states.decode(receipt["final_observation"])
    if evidence["final"] is None or receipt["final_observation"] != evidence["final"]:
        raise ValueError("terminal differs from durable full final observation")
    if not states.compatible(evidence["state"], final):
        raise ValueError("terminal geometry differs from last recorded observation")
    states.protected(evidence["baseline"], final, set())
    if not isinstance(receipt["effects"], list) or receipt["effects"] != evidence["effects"]:
        raise ValueError("terminal effect ledger differs from observed journal")
    from .restore_geometry import groups

    desired = {}
    claimed = set()
    policies = dimensions.policies(plan)
    initial_widths = {i: a["width"] for i, a in evidence["associations"].items()}
    for index, (row, initial) in enumerate(
        zip(receipt["windows"], plan["initial_accounting"], strict=True)
    ):
        if initial["status"] != "unprocessed":
            if row != initial or index in evidence["launches"]:
                raise ValueError("no-effect classification changed or launched")
            continue
        states.fields(
            row,
            "entry window_id status process_receipt restored_window_id observed_initial_width geometry_coverage target_workspace_id",
        )
        if (
            row["status"] != "placed"
            or row["entry"] != initial["entry"]
            or row["window_id"] != initial["window_id"]
        ):
            raise ValueError("unprocessed entry lacks full placement accounting")
        assoc = evidence["associations"].get(index)
        if (
            assoc is None
            or row["restored_window_id"] != assoc["id"]
            or row["observed_initial_width"] != assoc["width"]
            or row["target_workspace_id"] != assoc["target"]
        ):
            raise ValueError("placement lacks exact recorded association")
        wid = row["restored_window_id"]
        if wid in claimed:
            raise ValueError("duplicate claimed output")
        claimed.add(wid)
        launch = evidence["launches"][index]
        matches = [w["id"] for w in final[0].values() if w["pid"] == launch["process"]["pid"]]
        if matches != [wid] or row["process_receipt"] != launch["receipt"]:
            raise ValueError("missing/surplus process association")
        w, entry = final[0][wid], row["entry"]
        if w["workspace_id"] != row["target_workspace_id"] or w["is_floating"] != entry["floating"]:
            raise ValueError("incorrect final placement")
        desired.setdefault(entry["target_workspace_idx"], []).append(row)
        width = dimensions.width_target(policies[index], initial_widths)
        if (
            not states.number(width)
            or width <= 0
            or (w["layout"].get("tile_size") or [None])[0] != width
        ):
            raise ValueError("final width differs from requested or preserved dimension")
        coverage = {
            "width": dimensions.width_coverage(policies[index], True),
            "position": dimensions.position_coverage(entry, final, wid),
        }
        if row["geometry_coverage"] != coverage:
            raise ValueError("incorrect dimension coverage")
        if coverage["position"] == "requested-pending":
            raise ValueError("incorrect final floating position or unknown scale")
    targets = []
    output = next(w["output"] for w in evidence["baseline"][1] if w["is_focused"])
    for idx, rows in sorted(desired.items()):
        wsids = {r["target_workspace_id"] for r in rows}
        if len(wsids) != 1:
            raise ValueError("logical destination split")
        wsid = wsids.pop()
        ws = next(w for w in final[1] if w["id"] == wsid)
        if ws["output"] != output or wsid in targets:
            raise ValueError("foreign/duplicate logical destination")
        targets.append(wsid)
        name = plan["workspace_names"].get(str(idx))
        if name and ws["name"] != name:
            raise ValueError("requested workspace name absent")
        columns = {}
        for r in rows:
            e = r["entry"]
            if not e["floating"]:
                columns.setdefault(
                    e["column"] if e["column"] is not None else ("extra", r["restored_window_id"]),
                    [],
                ).append(r["restored_window_id"])
        protected_columns = groups(evidence["baseline"][0], wsid)
        if groups(final[0], wsid) != protected_columns + list(columns.values()):
            raise ValueError("final protected/owned topology differs from plan")
    actual_order = [w["id"] for w in sorted(final[1], key=lambda w: w["idx"]) if w["id"] in targets]
    if actual_order != targets:
        raise ValueError("logical workspace order changed")
    initial_focus = evidence["initial_focus"]
    if claimed and initial_focus is not None and not final[0][initial_focus]["is_focused"]:
        raise ValueError("initial focus not restored")
