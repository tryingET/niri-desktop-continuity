"""Explicit desktop continuity commands; observation is the default, never restoration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .approval import approve
from .model import readiness
from .planner import build_plan
from .probe import capture
from .store import Store


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--state-root", type=Path)
    commands = root.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("capture", help="read Niri and same-user process metadata")
    observe.add_argument(
        "--include-titles", action="store_true", help="private labels; never publish"
    )
    plan = commands.add_parser("plan", help="prepare proposal, never apply it")
    plan.add_argument("snapshot")
    plan.add_argument(
        "--intent", choices=["inspect", "reconcile", "restart", "migrate"], default="inspect"
    )
    plan.add_argument("--desired", help="desired stored snapshot digest")
    plan.add_argument("--window-id", type=int, action="append", default=[])
    plan.add_argument("--pid", type=int, action="append", default=[])
    plan.add_argument("--app-id")
    plan.add_argument("--version")
    plan.add_argument("--replacement")
    plan.add_argument("--ttl", type=int, default=300)
    preview = commands.add_parser("preview", help="offline HTML/SVG only; no browser launch")
    preview.add_argument("digest")
    preview.add_argument("--kind", choices=["snapshots", "plans"], default="snapshots")
    check = commands.add_parser("verify", help="compare with a fresh read-only observation")
    check.add_argument("desired")
    approval = commands.add_parser("approve", help="write one-use layout-only approval")
    approval.add_argument("plan")
    approval.add_argument("--confirm", required=True, help="repeat the entire reviewed plan digest")
    apply = commands.add_parser("reconcile", help="explicitly apply approved supported layout only")
    apply.add_argument("approval")
    apply.add_argument("--apply", action="store_true")
    apply.add_argument(
        "--acknowledge-non-atomic-focus",
        action="store_true",
        help="operator must remain idle; Niri focus+move cannot be atomic",
    )
    history = commands.add_parser("history", help="private stored artifact identities only")
    history.add_argument("--kind", choices=["snapshots", "plans", "receipts"], default="snapshots")
    history.add_argument("--limit", type=int, default=20)
    return root


def run(args):
    store = Store(args.state_root)
    if args.command == "capture":
        value = capture(include_titles=args.include_titles)
        key = store.save_snapshot(value)
        return {
            "snapshot_digest": key,
            "display": readiness(value),
            "windows": len(value["windows"]),
            "warnings": value["warnings"],
        }, 0
    if args.command == "plan":
        value = build_plan(
            store.get("snapshots", args.snapshot),
            intent=args.intent,
            desired=store.get("snapshots", args.desired) if args.desired else None,
            window_ids=args.window_id,
            pids=args.pid,
            app_id=args.app_id,
            version=args.version,
            replacement=args.replacement,
            ttl_seconds=args.ttl,
        )
        key = store.put("plans", value)
        return {
            "plan_digest": key,
            "admission": value["admission"],
            "selection": value["selection"],
            "affected": value["affected"],
        }, 0
    if args.command == "preview":
        from .map_preview import render_html, render_svg

        value = store.get(args.kind, args.digest)
        plan = value if args.kind == "plans" else None
        snapshot = store.get("snapshots", plan["snapshot_digest"]) if plan else value
        html = render_html(snapshot, plan=plan, plan_digest=args.digest if plan else None)
        svg = render_svg(snapshot, plan=plan, plan_digest=args.digest if plan else None)
        return {
            "html": str(store.write_preview(args.digest, "html", html)),
            "svg": str(store.write_preview(args.digest, "svg", svg)),
            "runtime_effects": "none",
            "approval": "not-granted",
        }, 0
    if args.command == "verify":
        key, report = store.save_verification(store.get("snapshots", args.desired), capture())
        return {"receipt_digest": key, **report}, 0 if report["layout_verified"] else 2
    if args.command == "approve":
        key = approve(store, args.plan, capture(), confirmation=args.confirm)
        return {"approval_digest": key, "runtime_effects": "none"}, 0
    if args.command == "reconcile":
        if not args.apply or not args.acknowledge_non_atomic_focus:
            raise ValueError("requires --apply and --acknowledge-non-atomic-focus; no action taken")
        from .reconcile import LiveTransport, reconcile

        result = reconcile(store, args.approval, LiveTransport())
        return result, 0 if result.get("layout_verified") else 2
    if not 1 <= args.limit <= 100:
        raise ValueError("history limit must be 1..100")
    paths = sorted(
        (store.root / args.kind).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return {"kind": args.kind, "digests": [path.stem for path in paths[: args.limit]]}, 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        value, status = run(args)
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        ImportError,
        subprocess.SubprocessError,
    ) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(value, indent=2, sort_keys=True))
    return status
