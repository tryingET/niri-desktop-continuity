"""Existing CLI resolution routes. Offline previews return text/JSON, never write a map."""

from . import recovery_profile, recovery_resolution, recovery_transition, resolution_candidate
from .recovery_protocol import hexkey, require
from .resolution_io import Objects


def selected(args):
    return getattr(args, "kind", None) in ("profile", "resolution") or (
        args.command == "plan" and args.intent in ("profile", "abandon")
    )


def run(args):
    # No Store, native observation, lock or output-file creation on these offline paths.
    if args.command == "inspect":
        require(args.kind == "resolution")
        return recovery_resolution.inspect(recovery_profile.identify_profile(), args.attempt), 0
    if args.command == "preview":
        profile = recovery_profile.identify_profile()
        value = Objects(profile["ledger_root"]).get(hexkey(args.digest))
        require(
            value["schema"]
            == (
                resolution_candidate.CANDIDATE
                if args.kind == "profile"
                else recovery_resolution.PLAN
            )
        )
        return {
            "digest": args.digest,
            "kind": args.kind,
            "proposal": value,
            "approval": "not-granted",
            "native_effects": [],
            "accounting_mutations": [],
            "warning": "Abandonment is not recovery success or permission to replay. Profile activation requires separate exact resolution approval.",
        }, 0
    if args.command == "plan":
        require(
            not any(
                (
                    args.snapshot,
                    args.desired,
                    args.window_id,
                    args.pid,
                    args.app_id,
                    args.version,
                    args.replacement,
                    args.adapter_config,
                    args.saved_set,
                    args.omit_association,
                )
            )
            and args.mode == "replacement"
        )
        require(args.attempt is not None)
        if args.intent == "profile":
            require(
                args.candidate is None
                and all((args.candidate_profile, args.observer_config, args.source_contract))
            )
            return resolution_candidate.plan(
                args.candidate_profile,
                args.observer_config,
                args.source_contract,
                args.attempt,
                args.ttl,
            ), 0
        require(
            args.candidate is not None
            and not any((args.candidate_profile, args.observer_config, args.source_contract))
        )
        return recovery_transition.plan(args.candidate, args.attempt, args.ttl), 0
    if args.command == "approve":
        require(not any((args.accept_losses, args.accept_omission, args.accept_utility_limit)))
        if args.kind == "profile":
            require(args.accept_abandonment is None)
            return resolution_candidate.approve(
                args.plan, args.confirm, args.accept_profile_admission
            ), 0
        require(args.accept_profile_admission is None)
        return recovery_transition.approve(args.plan, args.confirm, args.accept_abandonment), 0
    require(
        args.command == "reconcile"
        and args.kind == "resolution"
        and args.apply
        and not args.acknowledge_non_atomic_focus
    )
    return recovery_transition.apply(args.approval), 0
