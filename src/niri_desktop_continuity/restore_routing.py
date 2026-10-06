"""Envelope-only history routing, then version-specific materialization under caller's flock.

Routing is not authority. Each v2/v3 boundary invokes complete cumulative semantic validation.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from . import restore_retained as retained
from . import restore_state as states
from .model import digest
from .restore_reader import Counters, DependencyReader, ReaderStore, identity, matches
from .store import HEX, Store, private_directory

V1 = "desktop-continuity.restore-disposition.v1"
V2 = "desktop-continuity.restore-disposition.v2"
V3 = "desktop-continuity.restore-disposition.v3"


@dataclass
class Envelope:
    record: dict
    pin: dict
    store: Store
    signature: tuple
    discriminator: dict | None = None


class RoutingPass:
    """At most 4096 * 16 MiB canonical bytes plus ONE sequence-nine discriminator.

    No ordinary payload, snapshot, process receipt, plan, approval or witness is read here.
    Canonical envelopes are decoded individually; only small envelope data/pins are retained.
    Counters and position span every boundary, never reset when routing resumes.
    """

    def __init__(self, identity_value, *, counters=None, reader=None):
        from . import restore_history as history

        self.counters = counters if counters is not None else Counters()
        self.reader = reader
        self.path = history.fence_path(identity_value)
        if os.path.lexists(self.path.with_suffix(".permit")):
            raise ValueError("unresolved restore legacy permit")
        self.envelopes = []
        self.previous = None
        self.position = 0
        self.names = []
        self.directory = None
        if os.path.lexists(self.path):
            private_directory(self.path, create=False)
            self.directory = history.directory_pin(self.path)
            # Do not collect an unbounded list of malicious extra filenames.
            with os.scandir(self.path) as entries:
                for entry in entries:
                    self.names.append(entry.name)
                    if len(self.names) > history.LIMIT:
                        raise ValueError("orphan or incomplete history")
            self.names.sort()
            if not self.names or self.names != [f"{i:08d}.json" for i in range(len(self.names))]:
                raise ValueError("orphan or incomplete history")

    def verify(self):
        from . import restore_history as history

        if os.path.lexists(self.path.with_suffix(".permit")):
            raise ValueError("unresolved restore legacy permit")
        if self.directory is None:
            if os.path.lexists(self.path):
                raise ValueError("history appeared during routing")
            return
        if history.directory_pin(self.path) != self.directory:
            raise ValueError("history directory substituted")
        with os.scandir(self.path) as entries:
            names = set()
            for entry in entries:
                names.add(entry.name)
                if len(names) > len(self.names):
                    raise ValueError("history names changed during routing")
        if names != set(self.names):
            raise ValueError("history names changed during routing")
        for envelope in self.envelopes:
            if history.directory_pin(envelope.store.root) != envelope.record["origin"]["pin"]:
                raise ValueError("original Store changed after routing")
            # ubs:ignore[python.ctcompare.secret_eq] -- Stat tuple, not crypto.
            if identity(envelope.pin["path"]) != envelope.signature:
                raise ValueError("canonical envelope changed after routing")

    def evidence(self, path, *, discriminator=False):
        if self.reader is not None:
            # Explicit strict mode charges before even envelope decode. No unbudgeted
            # routing IO is counted here; these reads belong to validation counters only.
            return self.reader.evidence(path)
        prefix = "discriminator" if discriminator else "routing"
        setattr(self.counters, prefix + "_reads", getattr(self.counters, prefix + "_reads") + 1)
        data, pin = retained.raw(path)
        setattr(
            self.counters, prefix + "_bytes", getattr(self.counters, prefix + "_bytes") + len(data)
        )
        setattr(self.counters, prefix + "_parses", getattr(self.counters, prefix + "_parses") + 1)
        value = retained.json_bytes(data)
        return value, {**pin, "digest": digest(value)}

    def advance(self):
        """Route the next suffix up to its first new-family boundary (inclusive), or EOF."""
        from . import restore_history as history

        self.verify()
        start = self.position
        while self.position < len(self.names):
            seq = self.position
            path = self.path / self.names[seq]
            signature = identity(path)
            # evidence releases the raw buffer after its single bounded JSON decode.
            record, pin = self.evidence(path)
            # ubs:ignore[python.ctcompare.secret_eq] -- Stat tuple, not crypto.
            if identity(path) != signature:
                raise ValueError("canonical envelope changed during routing")
            states.fields(record, "schema seq previous type attempt receipt origin")
            if (
                record["schema"] != history.SCHEMA
                or type(record["seq"]) is not int
                or record["seq"] != seq
                or record["previous"] != self.previous
                or record["type"] not in history.TYPES
                or not HEX.fullmatch(record["attempt"])
            ):
                raise ValueError("invalid history chain")
            origin = record["origin"]
            states.fields(origin, "root pin")
            root = Path(origin["root"])
            if not root.is_absolute() or history.directory_pin(root) != origin["pin"]:
                raise ValueError("original Store replaced")
            store = Store(root, create=False)
            for kind in ("receipts", "snapshots"):
                private_directory(root / kind, create=False)
            payload_path = store.path("receipts", record["receipt"])  # key grammar, no IO
            info, parent = signature
            matches(
                {
                    "device": info[0],
                    "inode": info[1],
                    "length": info[2],
                    "directory": {"device": parent[0], "inode": parent[1]},
                },
                pin,
            )
            envelope = Envelope(record, pin, store, signature)
            self.envelopes.append(envelope)
            self.position += 1
            self.previous = digest(record)
            if record["type"] == "operator-disposition":
                new_family = True
                if seq == 9:
                    payload, ref = self.evidence(payload_path, discriminator=True)
                    if ref["digest"] != record["receipt"]:
                        raise ValueError("discriminator digest mismatch")
                    if not isinstance(payload, dict) or payload.get("schema") not in (V1, V2, V3):
                        raise ValueError("unknown disposition schema discriminator")
                    new_family = payload["schema"] in (V2, V3)
                    envelope.discriminator = ref
                    del payload
                if new_family:
                    self.verify()
                    return self.envelopes[start:], True
        self.verify()
        return self.envelopes[start:], False


def _materialize(envelopes, *, reader, counters):
    if reader is not None:
        # Reserve the whole known prefix BEFORE parsing even its first ordinary payload.
        reader.reserve_pins(e.pin for e in envelopes)
        for e in envelopes:
            reader.reserve(e.store.path("receipts", e.record["receipt"]), expected=e.discriminator)
    result = []
    for e in envelopes:
        record, store = e.record, e.store
        if reader is None:
            counters.legacy_reads += 1
            data, ref = retained.raw(store.path("receipts", record["receipt"]))
            counters.legacy_bytes += len(data)
            counters.legacy_parses += 1
            payload = retained.json_bytes(data)
            ref = {**ref, "digest": digest(payload)}
            if e.discriminator is not None:
                matches(ref, e.discriminator)
        else:
            # Routed canonical bytes are charged AND rebound, not accepted from the routing memo.
            reader.evidence(e.pin["path"], expected=e.pin)
            store = ReaderStore(store, reader)
            payload, ref = reader.artifact(store, "receipts", record["receipt"])
        if ref["digest"] != record["receipt"]:
            raise ValueError("original receipt digest mismatch")
        result.append((record, payload, store, [e.pin, ref]))
    return result


def _validate_v2_prefix(identity_value, chain, reader):
    """Historical helper name; validate either a v2 or v3 cumulative prefix."""
    from .restore_history import validate

    # All dependency discovery/semantics are sequential and mediated by this prefix reader.
    # No load recursion, native observation, manifest-based path traversal or fallback.
    validate(identity_value, chain, reader=reader)


def structural(
    identity_value, *, strict=False, limits=None, counters=None, expected=(), reader=None
):
    readers = [reader] if reader is not None else []
    try:
        return _structural(
            identity_value,
            strict=strict,
            limits=limits,
            counters=counters,
            expected=expected,
            reader=reader,
            readers=readers,
        )
    except BaseException:
        for value in readers:
            value.close()
        raise


def _structural(identity_value, *, strict, limits, counters, expected, reader, readers):
    """Structural compatibility API; NEVER grants admission or proves disposition semantics.

    Strict mode budgets from the outset (for later CLI integration). Default mode budgets
    each cumulative v2/v3 prefix separately, then routes the remaining suffix before deciding
    whether it needs another budgeted pass or legacy-only suffix materialization.
    """
    counters = counters if counters is not None else Counters()

    def fresh_reader():
        value = DependencyReader(limits=limits, counters=counters)
        readers.append(value)
        value.expect(expected)
        return value

    if reader is not None:
        reader.expect(expected)
    router = RoutingPass(
        identity_value,
        counters=counters,
        reader=(reader if reader is not None else fresh_reader()) if strict else None,
    )
    chain, previous_pins = [], []
    while True:
        suffix, boundary = router.advance()
        if boundary or strict:
            reader = router.reader if strict else fresh_reader()
            reader.reserve_pins(previous_pins)
            chain = _materialize(router.envelopes, reader=reader, counters=counters)
            if boundary:
                if not isinstance(chain[-1][1], dict) or chain[-1][1].get("schema") not in (V2, V3):
                    raise ValueError("non-v2 disposition outside its legacy routing location")
                _validate_v2_prefix(identity_value, chain, reader)
            if boundary:
                previous_pins = reader.manifest()
        else:
            chain.extend(_materialize(suffix, reader=None, counters=counters))
        router.verify()
        if not boundary:
            return chain
        if strict:
            router.reader = fresh_reader()
            router.reader.reserve_pins(previous_pins)


def classify_inspection(identity_value, attempt):
    """Find a completed v2/v3 target without materializing an active legacy suffix.

    Even this classification MUST validate each v2/v3 boundary before routing another envelope.
    Carry first-observed pins into the subsequent complete read-only inspection pass.
    """
    from .restore_disposition_dependencies import Bindings

    router = RoutingPass(identity_value)
    pins = []
    while True:
        _, boundary = router.advance()
        if not boundary:
            return False, Bindings([*pins, *(e.pin for e in router.envelopes)]).manifest()
        reader = DependencyReader(counters=router.counters)
        try:
            reader.reserve_pins(pins)
            chain = _materialize(router.envelopes, reader=reader, counters=router.counters)
            _validate_v2_prefix(identity_value, chain, reader)
            pins = reader.manifest()
        finally:
            reader.close()
        if router.envelopes[-1].record["attempt"] == attempt:
            return True, pins
