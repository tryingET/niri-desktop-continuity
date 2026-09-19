"""Explicit desktop continuity commands; observation is the default, never restoration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .approval import approve
from .model import readiness
from .planner import build_plan
from .probe import capture
from .store import Store


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument(
        "--version", action="version", version=f"niri-desktop-continuity {__version__}"
    )
    root.add_argument("--state-root", type=Path)
    commands = root.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("capture", help="read Niri and same-user process metadata")
    observe.add_argument(
        "--include-titles", action="store_true", help="private labels; never publish"
    )
    plan = commands.add_parser("plan", help="prepare proposal, never apply it")
    plan.add_argument("snapshot", nargs="?")
    plan.add_argument("--candidate-profile", type=Path)
    plan.add_argument("--observer-config", type=Path)
    plan.add_argument("--source-contract", type=Path)
    plan.add_argument("--attempt")
    plan.add_argument("--candidate")
    plan.add_argument(
        "--intent",
        choices=["inspect", "reconcile", "restart", "migrate", "reconstruct", "profile", "abandon"],
        default="inspect",
    )
    plan.add_argument("--desired", help="desired stored snapshot digest")
    plan.add_argument("--window-id", type=int, action="append", default=[])
    plan.add_argument("--pid", type=int, action="append", default=[])
    plan.add_argument("--app-id")
    plan.add_argument("--version")
    plan.add_argument("--replacement")
    plan.add_argument("--ttl", type=int, default=300)
    plan.add_argument("--adapter-config", type=Path)
    plan.add_argument("--mode", choices=["replacement", "additive"], default="replacement")
    plan.add_argument("--saved-set", help="owner-private saved-set digest; additive mode only")
    plan.add_argument("--omit-association", action="append", default=[])
    preview = commands.add_parser("preview", help="offline HTML/SVG only; no browser launch")
    preview.add_argument("digest", nargs="?", help="default: the latest capture (snapshots only)")
    preview.add_argument(
        "--kind", choices=["snapshots", "plans", "profile", "resolution"], default="snapshots"
    )
    check = commands.add_parser("verify", help="compare with a fresh read-only observation")
    check.add_argument("desired")
    check.add_argument("--kind", choices=["snapshots", "reconstruction"], default="snapshots")
    inspect = commands.add_parser("inspect", help="inspect reconstruction history without effects")
    inspect.add_argument("attempt")
    inspect.add_argument("--kind", choices=["reconstruction", "resolution"], required=True)
    approval = commands.add_parser(
        "approve", help="write exact one-use layout or reconstruction approval"
    )
    approval.add_argument("plan")
    approval.add_argument("--kind", choices=["profile", "resolution"])
    approval.add_argument("--accept-profile-admission", choices=["resolution-observe-only"])
    approval.add_argument("--accept-abandonment", choices=["abandon-without-retry-or-success"])
    approval.add_argument("--confirm", required=True, help="repeat the entire reviewed plan digest")
    approval.add_argument("--accept-losses", choices=["saved-conversations-v1"])
    approval.add_argument("--accept-omission", action="append", default=[])
    approval.add_argument("--accept-utility-limit", action="append", default=[])
    reconstruct = commands.add_parser("reconstruct", help="execute exact approved reconstruction")
    reconstruct.add_argument("approval")
    reconstruct.add_argument("--apply", action="store_true")
    reconstruct.add_argument("--acknowledge-non-atomic-focus", action="store_true")
    apply = commands.add_parser("reconcile", help="explicitly apply approved supported layout only")
    apply.add_argument("approval")
    apply.add_argument("--kind", choices=["resolution"])
    apply.add_argument("--apply", action="store_true")
    apply.add_argument(
        "--acknowledge-non-atomic-focus",
        action="store_true",
        help="operator must remain idle; Niri focus+move cannot be atomic",
    )
    reopen = commands.add_parser("restore", help="reopen every window of a saved desktop")
    reopen.add_argument("snapshot", nargs="?", help="snapshot digest; default latest capture")
    reopen.add_argument("--apply", action="store_true", help="without it: dry-run plan only")
    reopen.add_argument(
        "--at-login",
        action="store_true",
        help="wait for Niri, skip when the capture came from this compositor instance",
    )
    reopen.add_argument("--spawn-timeout", type=float, default=25.0)
    declared = commands.add_parser(
        "declare", help="how to reopen a live terminal process that cannot be resumed"
    )
    declared.add_argument("--pid", type=int, required=True)
    declared.add_argument("--cwd", help="default: the process's working directory")
    declared.add_argument("--label")
    declared.add_argument("--clear", action="store_true", help="remove the declaration")
    declared.add_argument("launch", nargs=argparse.REMAINDER, help="-- COMMAND [ARG...]")
    autostart = commands.add_parser("autostart", help="opt-in systemd user units (capture+reopen)")
    autostart.add_argument("--enable", action="store_true")
    autostart.add_argument("--disable", action="store_true")
    autostart.add_argument("--interval-minutes", type=int, default=15)
    history = commands.add_parser("history", help="private stored artifact identities only")
    history.add_argument("--kind", choices=["snapshots", "plans", "receipts"], default="snapshots")
    history.add_argument("--limit", type=int, default=20)
    return root


def run(args):
    from .resolution_cli import run as run_resolution
    from .resolution_cli import selected

    if args.command == "declare":
        from . import launch

        argv = args.launch[1:] if args.launch[:1] == ["--"] else args.launch
        if args.clear:
            if argv:
                raise ValueError("--clear takes no command")
            return {"cleared": launch.clear_declaration(args.pid), "pid": args.pid}, 0
        return {"declared": launch.declare(args.pid, argv, cwd=args.cwd, label=args.label)}, 0
    if args.command == "preview" and args.digest is None and args.kind != "snapshots":
        raise ValueError(f"--kind {args.kind} preview: digest required")
    if selected(args):
        return run_resolution(args)
    if args.command == "plan" and (
        args.snapshot is None
        or any(
            (
                args.candidate_profile,
                args.observer_config,
                args.source_contract,
                args.attempt,
                args.candidate,
            )
        )
    ):
        raise ValueError("snapshot required; candidate options are resolution-only")
    if args.command == "approve" and (args.accept_profile_admission or args.accept_abandonment):
        raise ValueError("explicit profile or resolution kind required")
    if args.command == "inspect":
        # Inspection identifies its canonical source only through the fixed owner
        # profile. Never create caller-root children, even if it aliases the ledger.
        return run_recovery(args, None)
    store = Store(args.state_root)
    recovery_mode = (
        args.command == "reconstruct"
        or (args.command == "plan" and args.intent == "reconstruct")
        or (args.command == "verify" and args.kind == "reconstruction")
        or (
            args.command == "approve"
            and store.get("plans", args.plan).get("intent") == "reconstruct"
        )
    )
    if recovery_mode:
        return run_recovery(args, store)
    if args.command == "plan" and (
        args.adapter_config or args.omit_association or args.saved_set or args.mode != "replacement"
    ):
        raise ValueError("adapter configuration and association omissions are reconstruction-only")
    if args.command == "approve" and (
        args.accept_losses or args.accept_omission or args.accept_utility_limit
    ):
        raise ValueError("loss and omission decisions are reconstruction-only")
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

        if args.digest is None:
            args.digest = store.pointer("latest-observed")
            if args.digest is None:
                raise ValueError("nothing captured yet; run capture first")
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
    if args.command == "restore":
        return run_restore(args, store)
    if args.command == "autostart":
        from . import autostart as units

        if args.enable and args.disable:
            raise ValueError("choose --enable or --disable")
        if args.enable:
            return units.enable(
                interval_minutes=args.interval_minutes, state_root=args.state_root
            ), 0
        if args.disable:
            return units.disable(), 0
        return units.status(), 0
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


def run_restore(args, store):
    from .probe import compositor_identity
    from .restore import LiveDesktop, restore

    desktop = LiveDesktop()
    key = args.snapshot or store.pointer("latest-observed")
    if key is None:
        raise ValueError("no saved desktop to reopen")
    if args.at_login:
        deadline = desktop.monotonic() + 60
        while not desktop.ready():
            if desktop.monotonic() >= deadline:
                raise ValueError("Niri did not become ready; nothing reopened")
            desktop.sleep(1.0)
        if store.get("snapshots", key)["identity"] == compositor_identity():
            return {
                "status": "same-compositor-instance",
                "snapshot_digest": key,
                "skipped": True,
            }, 0
    if not 1 <= args.spawn_timeout <= 300:
        raise ValueError("spawn timeout must be 1..300 seconds")
    result = restore(store, key, desktop, apply=args.apply, spawn_timeout=args.spawn_timeout)
    return result, 0 if result["status"] in {"dry-run", "reopened"} else 2


def run_recovery(args, store):
    from .resolution_lock import owner_guard

    with owner_guard():
        return _run_recovery(args, store)


def _run_recovery(args, store):
    from . import recovery
    from .recovery_protocol import RecoveryRefusal

    try:
        if args.command == "plan":
            if args.adapter_config is None:
                raise RecoveryRefusal("reconstruction-adapter-config-required")
            if args.desired or args.replacement:
                raise ValueError("unsupported reconstruction selector")
            value = recovery.propose(
                store,
                args.snapshot,
                args.adapter_config,
                capture(),
                omissions=args.omit_association,
                mode=args.mode,
                saved_set=args.saved_set,
                window_ids=args.window_id,
                pids=args.pid,
                app_id=args.app_id,
                version=args.version,
                ttl_seconds=args.ttl,
            )
        elif args.command == "approve":
            value = recovery.approve(
                store,
                args.plan,
                capture,
                confirmation=args.confirm,
                losses=args.accept_losses,
                omissions=args.accept_omission,
                utility_limits_accepted=args.accept_utility_limit,
            )
        elif args.command == "reconstruct":
            if not args.apply or not args.acknowledge_non_atomic_focus:
                raise ValueError("explicit effect acknowledgments required")
            value = recovery.execute(store, args.approval, capture)
        else:
            value = recovery.inspect_or_verify(
                store,
                args.desired if args.command == "verify" else args.attempt,
                verify=args.command == "verify",
            )
    except RecoveryRefusal:
        raise
    except (ValueError, OSError, KeyError, TypeError, StopIteration, subprocess.SubprocessError):
        # Neither adapter diagnostics nor private payload/configuration values are displayable.
        raise ValueError(
            "reconstruction-refused: profile, protocol, state or approval gate failed; no retry authorized"
        ) from None
    return value, 2 if value.get("status") in {"partial", "indeterminate"} else 0


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
