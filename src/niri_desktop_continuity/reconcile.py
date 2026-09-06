"""Bounded effect-checked layout operations; never restart or replay ambiguous effects."""

from __future__ import annotations

import subprocess
from copy import deepcopy
from datetime import datetime, timezone

from .approval import validate_plan
from .model import fingerprint, focus_pin, now, readiness, verify
from .operation_lock import operation_lock
from .probe import capture


class LiveTransport:
    def observe(self):
        return capture()

    def apply(self, action: dict):
        kind = action["kind"]
        if kind == "focus-window":
            args = ["focus-window", "--id", str(action["window_id"])]
        elif kind == "place-column":
            args = ["move-column-to-index", str(action["column_index"])]
        else:
            raise ValueError("unsupported live layout action")
        subprocess.run(
            ["niri", "msg", "action", *args], capture_output=True, text=True, timeout=10, check=True
        )


def expected_after(snapshot: dict, action: dict) -> dict:
    """Supported subset: same-workspace single-tile column reordering only."""
    result = deepcopy(snapshot)
    if action["kind"] != "place-column":
        raise ValueError("cross-workspace placement is not effect-modelled")
    window = next(item for item in result["windows"] if item["id"] == action["window_id"])
    columns = sorted(
        (
            item
            for item in result["windows"]
            if item["workspace_id"] == window["workspace_id"] and not item["is_floating"]
        ),
        key=lambda item: item["layout"]["pos_in_scrolling_layout"][0],
    )
    index = action["column_index"]
    if not 1 <= index <= len(columns):
        raise ValueError("invalid column index")
    columns.remove(window)
    columns.insert(index - 1, window)
    for index, item in enumerate(columns, 1):
        item["layout"]["pos_in_scrolling_layout"] = [index, 1]
    return result


def reconcile(store, approval_key: str, transport, *, clock=None, budget=128) -> dict:
    approval = store.get("approvals", approval_key)
    plan = store.get("plans", approval["plan_digest"])
    with operation_lock(plan["source_identity"]):
        return _reconcile_locked(store, approval_key, transport, clock=clock, budget=budget)


def _reconcile_locked(store, approval_key: str, transport, *, clock=None, budget=128) -> dict:
    approval = store.get("approvals", approval_key)
    if approval.get("schema") != "desktop-continuity.approval.v1":
        raise ValueError("invalid approval schema")
    current = transport.observe()
    plan = validate_plan(store, approval["plan_digest"], current, clock=clock)
    if (
        approval.get("expires_at") != plan["expires_at"]
        or approval.get("scope") != "same-instance-layout-only"
    ):
        raise ValueError("approval scope mismatch")
    actions = plan["actions"]
    if len(actions) * 2 + 1 > budget:
        raise ValueError("mutation budget exceeded")
    # Prove the entire action sequence's model before consuming approval or any IPC mutation.
    predicted = current
    for action in actions:
        predicted = expected_after(predicted, action)
    if not verify(plan["desired"], predicted)["layout_verified"]:
        raise ValueError("action sequence does not converge to the desired topology")
    store.consume(approval_key, {"started_at": now(), "plan_digest": approval["plan_digest"]})
    receipt: dict = {
        "schema": "desktop-continuity.reconcile-receipt.v1",
        "approval": approval_key,
        "started_at": now(),
        "status": "failed",
        "effects": [],
        "native_state": "unverified",
        "automatic_retry": False,
    }
    expected = current
    original_focus = next(
        (item["id"] for item in current["windows"] if item.get("is_focused")), None
    )
    expected_focus = focus_pin(current)

    def focus_target(window_id):
        nonlocal expected_focus
        workspace_id = next(w["workspace_id"] for w in expected["windows"] if w["id"] == window_id)
        expected_focus = {"windows": [window_id], "workspaces": [workspace_id]}

    def observe_expected():
        fresh = transport.observe()
        if (
            not readiness(fresh)["ready"]
            or fingerprint(fresh) != fingerprint(expected)
            or focus_pin(fresh) != expected_focus
        ):
            raise ValueError("unexpected desktop change: stop without replay or rollback")
        return fresh

    def effect(action):
        if (clock or datetime.now(timezone.utc)) >= datetime.fromisoformat(plan["expires_at"]):
            raise ValueError("approval expired during operation; no further actions")
        # Persist intent BEFORE dispatch. A crash leaves explicit effect-indeterminate history.
        record = {
            "approval": approval_key,
            "step": len(receipt["effects"]),
            "action": action,
            "status": "effect-indeterminate",
            "at": now(),
        }
        intent = store.put("receipts", record)
        receipt["effects"].append({"intent_receipt": intent, **record})
        transport.apply(action)
        receipt["effects"][-1]["status"] = "acknowledged-not-yet-verified"

    try:
        for action in actions:
            observe_expected()
            next_state = expected_after(expected, action)
            if fingerprint(next_state) == fingerprint(expected):
                continue
            effect({"kind": "focus-window", "window_id": action["window_id"]})
            focus_target(action["window_id"])
            focused = observe_expected()
            if not any(
                item["id"] == action["window_id"] and item.get("is_focused")
                for item in focused["windows"]
            ):
                raise ValueError("focus acknowledgement had no matching effect")
            receipt["effects"][-1]["status"] = "verified"
            # Niri has no atomic focus+move/CAS transaction. Requires an idle operator;
            # a concurrent action in this final IPC gap cannot be prevented by this client.
            effect(action)
            expected = next_state
            observe_expected()
            receipt["effects"][-1]["status"] = "verified"
        if receipt["effects"] and original_focus is not None:
            observe_expected()
            effect({"kind": "focus-window", "window_id": original_focus})
            focus_target(original_focus)
            focused = observe_expected()
            if not any(
                item["id"] == original_focus and item.get("is_focused")
                for item in focused["windows"]
            ):
                raise ValueError("original focus was not restored")
            receipt["effects"][-1]["status"] = "verified"
        final = observe_expected()
        verification_key, report = store.save_verification(plan["desired"], final)
        receipt.update(
            status=report["status"],
            verification_receipt=verification_key,
            layout_verified=report["layout_verified"],
            original_focus_verified=focus_pin(current) == focus_pin(final),
        )
    except Exception as exc:
        receipt.update(
            status="effect-indeterminate" if receipt["effects"] else "failed-before-effect",
            error_type=type(exc).__name__,
            error=str(exc),
            layout_verified=False,
        )
    receipt["finished_at"] = now()
    key = store.put("receipts", receipt)
    return {"receipt_digest": key, **receipt}
