"""Ordinary multi-host restore orchestration. Uncertainty stops the whole attempt."""

from copy import deepcopy

from . import restore_dimensions as dimensions
from . import restore_state as states
from .restore_attempt import Attempt
from .restore_host import Image, admit
from .restore_layout import Layout
from .restore_producer import launch


def execute(store, key, identity, desktop, observe, snapshot, planner, timeout):
    with Attempt(store, key, identity) as attempt:
        if attempt.historical is not None:
            historical = attempt.historical
            return {
                "snapshot_digest": key,
                "receipt_digest": historical["receipt_digest"],
                **historical["result"],
                "historical": True,
                "fresh_native_verification": False,
                **(
                    {"effects": [], "retry_authorized": False}
                    if historical["result"]["status"] == "operator-accepted-partial"
                    else {}
                ),
            }
        current = observe()
        if current["identity"] != identity or not current.get("coherent"):
            raise ValueError("fresh coherent compositor baseline required")
        plan = planner(snapshot, current["windows"], current["workspaces"])
        plan["source_plan"] = deepcopy(plan)
        plan["mode"] = "restore"
        plan["baseline"] = states.record(
            (
                {w["id"]: w for w in current["windows"]},
                current["workspaces"],
                states.output_scales(current.get("outputs", []), current["workspaces"]),
            )
        )
        plan["baseline_recipes"] = [
            {"id": w["id"], "recipe": w.get("reopen")} for w in current["windows"]
        ]
        rows = []
        for entry in plan["entries"]:
            status = "already-open" if entry.get("status") == "already-open" else "unprocessed"
            row = {"entry": deepcopy(entry), "window_id": entry["window_id"], "status": status}
            if status == "unprocessed":
                try:
                    spec = admit(entry["recipe"])
                    with Image(spec["argv"][0]):
                        pass
                    # Freeze the exact controlled host path/argv before any dispatch.
                    entry["recipe"] = {**entry["recipe"], **spec}
                    row["entry"] = deepcopy(entry)
                except (OSError, ValueError) as exc:
                    row.update(status="unsupported", reason=str(exc))
            rows.append(row)
        # Complete accounting, including unsupported and unprocessed entries, precedes effects.
        plan["initial_accounting"] = deepcopy(rows)
        policies = dimensions.policies(plan)  # refuse impossible shared widths before any launch
        attempt.prepare(plan)
        result = {
            "status": "interrupted",
            "windows": rows,
            "effects": [],
            "final_observation": {},
            "native_session": "not-proved",
        }
        for index, policy in policies.items():
            rows[index]["geometry_coverage"] = dimensions.pending(rows[index]["entry"], policy)
        layout = None
        try:
            layout = Layout(attempt, desktop, current, timeout)
            layout.rows = rows
            for index, row in enumerate(rows):
                if row["status"] != "unprocessed":
                    continue
                layout.fresh()
                row["status"] = "launch-indeterminate"
                proof = launch(attempt, attempt.ticket(index), timeout=timeout)
                row["process_receipt"] = proof.receipt
                row["restored_window_id"] = layout.associate(proof, index)
                wid = row["restored_window_id"]
                row["observed_initial_width"] = (
                    layout.state[0][wid]["layout"].get("tile_size") or [None]
                )[0]
                layout.refresh_coverage()
                row["target_workspace_id"] = layout.target(row["entry"]["target_workspace_idx"])
                initial = {
                    i: r["observed_initial_width"]
                    for i, r in enumerate(rows)
                    if "observed_initial_width" in r
                }
                # Only the seed is resized. Donors inherit its geometry on consumption;
                # requiring a separately representable donor resize would reject no-resize columns.
                desired = (
                    dimensions.width_target(policies[index], initial)
                    if policies[index]["seed"] == index
                    else None
                )
                layout.preflight_width(wid, desired)
                layout.place(wid, row["target_workspace_id"])
                row["status"] = "owned-not-placed"
            owned = [r for r in rows if r["status"] == "owned-not-placed"]
            layout.arrange(owned)
            layout.names(plan["workspace_names"], owned)
            if layout.original_focus is not None and owned:
                layout.focus(layout.original_focus, original=True)
            layout.fresh()
            for row in owned:
                row["status"] = "placed"
            result["effects"] = layout.effects
            result["final_observation"] = states.record(layout.state)
            attempt.append("final-observed", {"state": result["final_observation"]})
            result["status"] = (
                "partial" if any(r["status"] == "unsupported" for r in rows) else "reopened"
            )
            receipt = attempt.finish(result)
            return {
                "snapshot_digest": key,
                "receipt_digest": receipt,
                **result,
                "pointer_projected": attempt.pointer_projected,
            }
        except Exception as exc:  # noqa: BLE001 - retain full accounting, never effect cleanup
            result["status"] = "interrupted"
            result["error_type"], result["error"] = type(exc).__name__, str(exc)
            if layout is not None:
                result["effects"] = layout.effects
                rejected = layout.failure_observation.export()
                if rejected is not None:
                    result["first_rejected_observation"] = rejected
                # Bounded geometry only, never raw titles or an ownership/success upgrade.
                try:
                    result["final_observation"] = states.record(layout.read())
                except Exception:  # noqa: BLE001
                    result["final_observation"] = {"unavailable": True}
            receipt = store.put("receipts", result)
        return {"snapshot_digest": key, "receipt_digest": receipt, **result}
