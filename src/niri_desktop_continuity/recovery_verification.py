"""Separate native and layout evidence; fresh observation never rewrites effect history."""

from . import recovery_additive as additive
from .recovery_protocol import ADDITIVE, VERSION2, proof, version
from .recovery_utilities import utility_limits


def receipt(plan, attempt, evidence, *, history_complete, events):
    recovery = plan["recovery"]
    schema = version(recovery["schema"])
    observation = recovery["observation"]
    complete = evidence is not None and proof(
        evidence, observation["session_refs"], schema, observation.get("utilities", ())
    )
    omissions = recovery["omissions"]
    limits = utility_limits(observation) if schema == VERSION2 else []
    if evidence is None or not history_complete or evidence["interrupted"]:
        status = "indeterminate"
    elif not complete:
        status = "partial"
    elif limits:
        status = "verified-with-accepted-limitations"
    else:
        status = "verified-with-accepted-omissions" if omissions else "verified"
    return {
        "schema": schema,
        "kind": "reconstruction",
        "attempt_digest": attempt,
        "status": status,
        "proof": evidence,
        "events": events,
        "coverage": recovery["coverage"],
        "overall_native_coverage_complete": status == "verified" and not omissions,
        "accepted_omissions": omissions,
        **(
            additive.receipt_fields(recovery, complete and history_complete)
            if schema == ADDITIVE
            else {}
        ),
        **(
            {
                "accepted_utility_limits": limits,
                "overall_image_coverage_complete": bool(
                    complete and history_complete and not limits
                ),
                "image_coverage": "observable-subset-only" if limits else "complete",
                "saved_conversations_recovered": len(observation["session_refs"])
                if complete and history_complete
                else 0,
            }
            if schema == VERSION2
            else {}
        ),
        "process_memory": "unsupported",
        "provider_usability": "unverified",
        "human_acceptance": "unverified",
    }
