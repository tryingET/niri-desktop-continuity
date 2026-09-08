"""Read-only, loss-aware accounting projection. Never an admission or repair surface."""

from itertools import islice

from .recovery_protocol import hexkey
from .store import HEX, private_directory

FAULTS = (ValueError, OSError, KeyError, TypeError, RecursionError)


def accounting(ledger, target):
    hexkey(target)
    names, issues = {target}, []
    for kind in ("recovery-prepared", "recovery-ready", "recovery-terminal"):
        try:
            directory = ledger.store.root / kind
            private_directory(directory, create=False)
            paths = list(islice(directory.iterdir(), 1001))
            if len(paths) > 1000:
                issues.append(f"{kind}:count-exceeded")
            for path in paths[:1000]:
                if path.suffix == ".json" and HEX.fullmatch(path.stem):
                    names.add(path.stem)
                else:
                    issues.append(f"{kind}:unknown-entry")
        except FAULTS:
            issues.append(f"{kind}:missing-or-unreadable")
    if len(names) > 1000:
        issues.append("attempt-count-exceeded")
        names = {target, *sorted(names - {target})[:999]}
    attempts = []
    for key in sorted(names):
        identity = {}
        try:
            historical = ledger.historical(key)
            identity = {"schema": historical.schema, "profile_digest": historical.profile_digest}
            status, state = historical.attempt_status(key), "valid"
        except FileNotFoundError:
            status, state = "indeterminate", "missing"
        except FAULTS:
            status, state = "indeterminate", "invalid-or-unreadable"
        attempts.append({"attempt_digest": key, "status": status, "accounting": state, **identity})
    return {
        "attempts": attempts,
        "scan": "unknown" if issues else "bounded",
        "issues": sorted(set(issues)),
        "retry_authorized": False,
    }


def events(ledger, target):
    hexkey(target)
    try:
        ledger = ledger.historical(target)
    except FAULTS:
        pass  # Retain independently readable current-version events if the fence is damaged.
    records, missing = [], {"intent": [], "result": []}
    for sequence in range(256):
        pair, states = {}, {}
        for kind in ("intent", "result"):
            try:
                pair[kind] = ledger.read_event(target, sequence, kind)
                states[kind] = "valid"
            except FileNotFoundError:
                states[kind] = "missing"
                missing[kind].append(sequence)
            except FAULTS:
                states[kind] = "invalid-or-unreadable"
        if pair or "invalid-or-unreadable" in states.values():
            matched = (
                states == {"intent": "valid", "result": "valid"}
                and pair["intent"]["intent_ref"] == pair["result"]["intent_ref"]
            )
            records.append(
                {
                    "sequence": sequence,
                    **pair,
                    "accounting": states,
                    "outcome": pair["result"]["outcome"] if matched else "unresolved",
                }
            )
    return {
        "records": records,
        "missing_indices": missing,
        "absence_is_no_effects_proof": False,
        "retry_authorized": False,
    }
