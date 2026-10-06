"""One explicit flock owner and one-use subordinate tickets; no ambient lock bypass."""

from __future__ import annotations

import os
import secrets
from copy import deepcopy

from . import restore_history as history
from .model import digest
from .operation_lock import operation_lock
from .store import private_directory


class Ticket:
    def __init__(self, owner, index):
        self.owner, self.index, self.used = owner, index, False


class Attempt:
    def __init__(self, store, key, identity):
        self.store, self.key, self.identity = store, key, deepcopy(identity)
        self.nonce = secrets.token_hex(32)
        self.active = self.poisoned = False
        self.plan = self.pending = self.frozen = None
        self.tickets = {}
        self.proofs = []
        self.pid = os.getpid()
        self.historical = None

    def __enter__(self):
        if self.active or self.poisoned:
            raise ValueError("closed or reused restore attempt")
        self.lock = operation_lock(self.identity)
        self.fd = self.lock.__enter__()
        try:
            completed, _, self.seq, self.previous = history.admit(self.identity)
            self.origin = {
                "root": str(self.store.root),
                "pin": history.directory_pin(self.store.root),
            }
            self.store.get("snapshots", self.key)
            self.historical = next((h for h in completed if h["snapshot_digest"] == self.key), None)
            self.fd_pin = os.fstat(self.fd)
            self.active = True
            return self
        except BaseException:
            self.lock.__exit__(None, None, None)
            raise

    def check(self):
        if not self.active or self.poisoned or os.getpid() != self.pid:
            raise ValueError("closed, foreign or poisoned restore attempt")
        # ubs:ignore[python.ctcompare.secret_eq] -- Frozen plan integrity, not auth.
        if self.frozen is not None and digest(self.plan) != self.frozen:
            self.poisoned = True
            raise ValueError("frozen attempt plan changed")
        info = os.fstat(self.fd)
        if (info.st_dev, info.st_ino) != (self.fd_pin.st_dev, self.fd_pin.st_ino):
            raise ValueError("restore lock identity changed")
        if history.directory_pin(self.store.root) != self.origin["pin"]:
            raise ValueError("original Store changed")
        for kind in ("snapshots", "receipts"):
            private_directory(self.store.root / kind, create=False)

    def append(self, kind, payload):
        self.check()
        if self.historical is not None or self.seq >= history.LIMIT:
            raise ValueError("historical replay or history bound: no new effects")
        try:
            if kind == "intent":
                history.records.intent(payload, self.plan, self.evidence)
                self.intent_payload = deepcopy(payload)
            elif kind == "observed":
                history.records.observed(payload, self.intent_payload, self.evidence)
            elif kind == "association":
                history.records.association(payload, self.plan, self.evidence)
            elif kind == "final-observed":
                history.records.final_observed(payload, self.plan, self.evidence)
            key = self.store.put("receipts", payload)
            record = {
                "schema": history.SCHEMA,
                "seq": self.seq,
                "previous": self.previous,
                "type": kind,
                "attempt": self.nonce,
                "receipt": key,
                "origin": self.origin,
            }
            history.durable_create(
                history.fence_path(self.identity) / f"{self.seq:08d}.json", record
            )
            self.seq += 1
            self.previous = digest(record)
            return key
        except BaseException:
            self.poisoned = True
            raise

    def prepare(self, plan):
        self.check()
        if self.plan is not None:
            raise ValueError("attempt already prepared")
        # Reserve a conservative bound before any canonical admission or effect. Exhaustion is
        # not discovered halfway through a multiwindow attempt; history is never pruned to fit.
        if self.seq + 32 * len(plan["entries"]) + 4 > history.LIMIT:
            raise ValueError("insufficient restore history capacity before dispatch")
        self.evidence = history.records.prepared(
            plan, self.store.get("snapshots", self.key), self.identity
        )
        self.plan = deepcopy(plan)
        self.frozen = digest(self.plan)
        path = history.fence_path(self.identity)
        private_directory(path)
        self.append(
            "prepared", {"identity": self.identity, "snapshot_digest": self.key, "plan": self.plan}
        )

    def ticket(self, index):
        self.check()
        if (
            self.plan is None
            or type(index) is not int
            or not 0 <= index < len(self.plan["entries"])
        ):
            raise ValueError("unbound launch entry")
        if index in self.tickets:
            raise ValueError("launch entry already ticketed")
        if (
            self.plan["mode"] == "restore"
            and self.plan["initial_accounting"][index]["status"] != "unprocessed"
        ):
            raise ValueError("entry was admitted as no-effect")
        result = Ticket(self, index)
        self.tickets[index] = result
        return result

    def consume(self, ticket):
        self.check()
        if (
            type(ticket) is not Ticket
            or ticket.owner is not self
            or ticket.used
            or self.tickets.get(ticket.index) is not ticket
        ):
            raise ValueError("closed, foreign or consumed launch ticket")
        ticket.used = True
        return deepcopy(self.plan["entries"][ticket.index]["recipe"])

    def intent(self, action, details):
        self.check()
        if self.pending is not None or action not in history.ACTIONS:
            raise ValueError("unobserved effect or unknown action")
        self.pending = self.append("intent", {"action": action, "details": details})
        return self.pending

    def observed(self, evidence):
        self.check()
        if self.pending is None:
            raise ValueError("observation without effect intent")
        self.append("observed", {"intent": self.pending, "evidence": evidence})
        self.pending = None

    def finish(self, result):
        self.check()
        if self.pending is not None:
            raise ValueError("unobserved effect cannot terminate")
        history.terminal_valid(result, self.plan)
        _, active, _, _ = history.load(self.identity)
        history.records.terminal(result, self.plan, active["_launches"])
        key = self.append("terminal", result)  # final receipt fsync -> terminal fsync
        self.active = False  # terminal cannot authorize more effects, even if pointer fails
        self.pointer_projected = False
        if result["status"] == "reopened":
            try:
                self.store.pointer("last-reopened", self.key)
                self.pointer_projected = True
            except OSError:
                pass  # committed history remains authoritative; never retry projection/effects
        return key

    def __exit__(self, *args):
        self.active = False
        self.poisoned = True
        failures = []
        try:
            for proof in tuple(self.proofs):
                try:
                    proof.close()
                except BaseException as exc:
                    failures.append(exc)
        finally:
            try:
                self.lock.__exit__(*args)
            except BaseException as exc:
                failures.append(exc)
        if failures:
            if len(args) > 1 and args[1] is not None:
                failures.insert(0, args[1])
            if len(failures) == 1:
                raise failures[0]
            raise BaseExceptionGroup("restore attempt teardown failed", failures)
