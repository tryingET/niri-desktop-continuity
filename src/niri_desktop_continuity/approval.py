"""Expiring, digest-bound local operator approval. No restart authority."""

from __future__ import annotations

from datetime import datetime, timezone

from .model import PLAN_SCHEMA, fingerprint, focus_pin, readiness
from .planner import layout_actions


def validate_plan(store, key: str, current: dict, *, clock=None) -> dict:
    plan = store.get("plans", key)
    if plan.get("schema") != PLAN_SCHEMA or plan.get("intent") != "reconcile":
        raise ValueError("only layout reconciliation can be approved; restart is blocked")
    if plan.get("admission", {}).get("status") != "awaiting-approval":
        raise ValueError("plan is not admissible")
    now = clock or datetime.now(timezone.utc)
    created = datetime.fromisoformat(plan["created_at"])
    expires = datetime.fromisoformat(plan["expires_at"])
    if created.tzinfo is None or expires.tzinfo is None:
        raise ValueError("plan requires timezone-aware timestamps")
    if not created <= now < expires or not 0 < (expires - created).total_seconds() <= 900:
        raise ValueError("expired or invalid plan lifetime")
    source = store.get("snapshots", plan["snapshot_digest"])
    if not readiness(current)["ready"] or not readiness(source)["ready"]:
        raise ValueError("display observation is not ready")
    if fingerprint(source) != plan["state_fingerprint"] or fingerprint(current) != fingerprint(
        source
    ):
        raise ValueError("stale plan: desktop identity or topology changed")
    if plan["source_identity"] != current["identity"]:
        raise ValueError("compositor identity changed")
    if focus_pin(source) != plan.get("focus_pin") or focus_pin(current) != plan["focus_pin"]:
        raise ValueError("stale plan: operator focus changed")
    if not readiness(plan["desired"])["ready"]:
        raise ValueError("desired checkpoint is not display-valid")
    actions, blockers = layout_actions(source, plan["desired"])
    if blockers or actions != plan["actions"]:
        raise ValueError("plan actions do not match the supported topology contract")
    return plan


def approve(store, plan_key: str, current: dict, *, confirmation: str, clock=None) -> str:
    if confirmation != plan_key:
        raise ValueError("explicit confirmation must equal the complete plan digest")
    plan = validate_plan(store, plan_key, current, clock=clock)
    # Deterministic approval per plan: re-approval cannot reset its one-use fence.
    return store.put(
        "approvals",
        {
            "schema": "desktop-continuity.approval.v1",
            "plan_digest": plan_key,
            "expires_at": plan["expires_at"],
            "scope": "same-instance-layout-only",
        },
    )
