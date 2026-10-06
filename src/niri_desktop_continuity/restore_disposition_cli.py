"""Accounting-only subcommands of the existing binary; never reconstruction authority."""

import os
from pathlib import Path

from . import restore_disposition as disposition
from .probe import compositor_identity
from .restore_disposition_failure import guard, phase
from .store import Store


def add_parser(commands):
    parser = commands.add_parser(
        "restore-disposition", help="explicit retained partial accounting; no desktop effects"
    )
    stages = parser.add_subparsers(dest="disposition_stage", required=True)
    for name in ("inspect", "propose"):
        stage = stages.add_parser(
            name, help="validate original returned-client witness; never approve"
        )
        stage.add_argument("attempt")
        stage.add_argument(
            "--family",
            choices=[
                "exec-observed-unassociated",
                "associated-shell-protected-dimensions-interrupted",
            ],
            default=None,
            help="explicit accounting family; omission retains the absolute-nine v1 family",
        )
        stage.add_argument("--interrupted-receipt", required=True)
        stage.add_argument(
            "--client-result",
            type=Path,
            required=True,
            help="original synchronous CLI JSON body in its original private witness directory",
        )
        stage.add_argument(
            "--client-exit",
            type=Path,
            required=True,
            help="original synchronous exit file containing exactly 2 plus newline",
        )
        if name == "propose":
            stage.add_argument("--ttl", type=int, default=300)
    stage = stages.add_parser(
        "approve", help="attest trusted original invocation provenance; not kernel proof"
    )
    stage.add_argument("plan")
    stage.add_argument("--confirm", required=True)
    stage.add_argument(
        "--ack-platform", help="v3 only: explicit digest of the fixed plan.platform object"
    )
    stage.add_argument("--accept", choices=[disposition.ACCEPT], required=True)
    stage.add_argument(
        "--attest-client-returned",
        action="store_true",
        required=True,
        help="attest these are ORIGINAL synchronously collected invocation files, not reconstructed evidence",
    )
    stage = stages.add_parser("apply", help="consume approval and append partial accounting ONLY")
    stage.add_argument("approval")


def run(args):
    with phase("route"):
        store = Store(args.state_root, create=False)
    with phase("history"):
        result = _run(args, store)
    return result, 2 if result.get("status") == disposition.ACCEPT else 0


def _run(args, store):
    stage = args.disposition_stage
    if stage in {"inspect", "propose"}:
        function = getattr(disposition, stage)
        if (
            args.family != "associated-shell-protected-dimensions-interrupted"
            and not os.environ.get("NIRI_SOCKET")
        ):
            raise guard("ineligible-evidence", "NIRI_SOCKET unavailable")
        return function(
            store,
            None
            if args.family == "associated-shell-protected-dimensions-interrupted"
            else compositor_identity(),
            args.attempt,
            args.interrupted_receipt,
            args.client_result,
            args.client_exit,
            family=args.family,
            **(
                {"ttl": args.ttl, "observer": disposition.proof.observe}
                if stage == "propose"
                else {}
            ),
        )
    if stage == "approve":
        return disposition.approve(
            store,
            args.plan,
            confirmation=args.confirm,
            acceptance=args.accept,
            attest_client_returned=args.attest_client_returned,
            platform_ack=args.ack_platform,
            observer=disposition.proof.observe,
        )
    return disposition.apply(store, args.approval, observer=disposition.proof.observe)
