"""Durable canonical prepare / CLI consume / canonical ready fence, never reset or repair."""

from __future__ import annotations

from itertools import islice
from pathlib import Path

from . import recovery_additive as additive
from .model import digest
from .recovery_profile import read_private
from .recovery_protocol import ADDITIVE, VERSION, fields, hexkey, require, successes, version
from .store import HEX, Store, private_directory


def bounded_names(path):
    private_directory(path, create=False)
    paths = list(islice(path.iterdir(), 1001))
    require(len(paths) <= 1000)
    require(all(p.suffix == ".json" and HEX.fullmatch(p.stem) for p in paths))
    return {p.stem for p in paths}


class Ledger:
    def __init__(self, profile, *, read_only=False):
        self.store = Store(Path(profile["ledger_root"]), create=not read_only)
        self.profile_digest = digest(profile)
        self.schema = version(profile["schema"])

    def historical(self, key):
        """Non-authorizing historical schema route; never selects executable code."""
        from copy import copy

        record = self.store.recovery_marker("recovery-prepared", key)
        historical = copy(self)
        historical.schema = version(record["schema"])
        historical.profile_digest = hexkey(record["profile_digest"])
        return historical

    def attempt_status(self, key):
        record = self.store.recovery_marker("recovery-prepared", key)
        fields(
            record,
            (
                "schema",
                "profile_digest",
                "approval_digest",
                "plan_digest",
                "cli_used_path",
                "binding",
            ),
        )
        require(
            record["schema"] == self.schema
            and record["profile_digest"] == self.profile_digest
            and record["approval_digest"] == key
        )
        hexkey(record["plan_digest"])
        fields(record["binding"], ("schema", "approval_digest", "plan_digest", "profile_digest"))
        require(
            record["binding"]
            == binding(key, record["plan_digest"], self.profile_digest, self.schema)
        )
        ready = self.store.recovery_marker("recovery-ready", key)
        require(ready == record["binding"] and read_private(record["cli_used_path"]) == ready)
        terminal = self.store.recovery_marker("recovery-terminal", key)
        fields(terminal, ("binding", "receipt_digest", "status"))
        require(terminal["binding"] == ready)
        receipt = self.store.get("receipts", hexkey(terminal["receipt_digest"]))
        require(
            receipt["schema"] == self.schema
            and receipt["attempt_digest"] == key
            and receipt["status"] == terminal["status"]
        )
        require(terminal["status"] in (*successes(self.schema), "partial", "indeterminate"))
        # Canonical version bindings must agree across plan, approval and receipt, not just frames.
        from .recovery import approval_record
        from .recovery_verification import receipt as make_receipt

        plan = self.store.get("plans", record["plan_digest"])
        approval = self.store.get("approvals", key)
        require(plan["recovery"]["schema"] == self.schema)
        require(plan["recovery"]["profile_digest"] == self.profile_digest)
        require(approval == approval_record(plan, record["plan_digest"]))
        expected = make_receipt(
            plan,
            key,
            receipt["proof"],
            history_complete=receipt["status"] != "indeterminate",
            events=receipt["events"],
        )
        if "reason" in receipt:
            require(receipt["status"] == "indeterminate")
            expected["reason"] = "worker-or-proof-failed; no-retry-or-cleanup-authorized"
        require(receipt == expected)
        evidence = self.events(key)
        observed = [
            {k: v for k, v in item["result"].items() if k != "receipt_digest"}
            for item in evidence
            if "result" in item
        ]
        require(observed == receipt["events"])
        if terminal["status"] in successes(self.schema):
            if self.schema == ADDITIVE:
                additive.validate_event_history(plan, evidence)
            else:
                require(bool(evidence) and all(item["outcome"] == "observed" for item in evidence))
        return terminal["status"]

    def disposition(self):
        # Admission/verification remains strict. Only absent completion of a known
        # prepared attempt is classified; malformed/inconsistent accounting raises.
        prepared = bounded_names(self.store.root / "recovery-prepared")
        for kind in ("recovery-ready", "recovery-terminal"):
            require(bounded_names(self.store.root / kind) <= prepared)
        attempts = []
        for key in sorted(prepared):
            try:
                status = self.attempt_status(key)
            except FileNotFoundError:
                status = "indeterminate"
            attempts.append({"attempt_digest": key, "status": status})
        return attempts

    def available(self):
        require(all(item["status"] in successes(self.schema) for item in self.disposition()))

    def prepare(self, cli, approval_key, plan_key):
        self.available()
        pair = binding(approval_key, plan_key, self.profile_digest, self.schema)
        self.store.recovery_marker(
            "recovery-prepared",
            approval_key,
            {
                **{
                    key: pair[key]
                    for key in ("schema", "profile_digest", "approval_digest", "plan_digest")
                },
                "cli_used_path": str(cli.path("used", approval_key)),
                "binding": pair,
            },
        )
        cli.consume(approval_key, pair)
        self.store.recovery_marker("recovery-ready", approval_key, pair)
        return pair

    def event(self, attempt, kind, value):
        key = self.store.put(
            "receipts",
            {
                "schema": self.schema,
                "attempt_digest": attempt,
                "event": kind,
                "value": value,
            },
        )
        index = digest({"attempt_digest": attempt, "sequence": value["sequence"], "event": kind})
        self.store.recovery_marker("recovery-events", index, {"receipt_digest": key})
        return key

    def read_event(self, attempt, sequence, kind):
        index = digest({"attempt_digest": attempt, "sequence": sequence, "event": kind})
        marker = self.store.recovery_marker("recovery-events", index)
        fields(marker, ("receipt_digest",))
        key = hexkey(marker["receipt_digest"])
        record = self.store.get("receipts", key)
        fields(record, ("schema", "attempt_digest", "event", "value"))
        require(
            record["schema"] == self.schema
            and record["attempt_digest"] == attempt
            and record["event"] == kind
        )
        value = record["value"]
        fields(
            value,
            ("sequence", "kind", "intent_ref")
            + (("target_ref",) if self.schema == ADDITIVE else ())
            if kind == "intent"
            else ("sequence", "intent_ref", "outcome", "evidence_ref"),
        )
        require(type(value["sequence"]) is int and value["sequence"] == sequence)
        hexkey(value["intent_ref"])
        if kind == "intent":
            if self.schema == ADDITIVE:
                additive.event_intent(value)
            else:
                require(value["kind"] in ("shutdown", "service", "launch", "layout"))
        else:
            require(value["outcome"] in ("observed", "indeterminate"))
            hexkey(value["evidence_ref"])
        return {"receipt_digest": key, **value}

    def events(self, attempt):
        result = []
        for sequence in range(256):
            pair = {}
            for kind in ("intent", "result"):
                try:
                    pair[kind] = self.read_event(attempt, sequence, kind)
                except FileNotFoundError:
                    continue
            if pair:
                require("intent" in pair)
                if "result" in pair:
                    require(pair["result"]["intent_ref"] == pair["intent"]["intent_ref"])
                result.append(
                    {
                        "sequence": sequence,
                        **pair,
                        "outcome": pair.get("result", {}).get("outcome", "unresolved"),
                    }
                )
        return result

    def finish(self, cli, pair, receipt):
        key = self.store.put("receipts", receipt)
        cli.put("receipts", receipt)
        self.store.recovery_marker(
            "recovery-terminal",
            pair["approval_digest"],
            {
                "binding": pair,
                "receipt_digest": key,
                "status": receipt["status"],
            },
        )
        return key


def binding(approval, plan, profile, schema=VERSION):
    return {
        "schema": version(schema),
        "approval_digest": approval,
        "plan_digest": plan,
        "profile_digest": profile,
    }
