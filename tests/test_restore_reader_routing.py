"""Routing/scheduling oracles only; synthetic v2 callbacks do not establish history authority."""

import json

import pytest
from test_restore_reader import ledger as ledger  # noqa: F401
from test_restore_reader import private_file

from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_reader_io as bounded
from niri_desktop_continuity import restore_retained as retained
from niri_desktop_continuity import restore_routing as routing
from niri_desktop_continuity.restore_reader import Counters, Limits
from niri_desktop_continuity.store import Store


def trace(monkeypatch):
    reads, decoded = [], []
    raw, reserved_raw, decode = retained.raw, bounded.raw, retained.json_bytes

    def read(path):
        reads.append(str(path))
        return raw(path)

    def bound_read(path, reservation, counters):
        reads.append(str(path))
        return reserved_raw(path, reservation, counters)

    def parse(data):
        decoded.append(data)
        return decode(data)

    monkeypatch.setattr(retained, "raw", read)
    monkeypatch.setattr(bounded, "raw", bound_read)
    monkeypatch.setattr(retained, "json_bytes", parse)
    return reads, decoded


@pytest.mark.parametrize("padding,reverse", [(0, False), (10000, True)])
def test_envelope_only_routing_never_reads_or_decodes_ordinary_dependencies(
    ledger, monkeypatch, padding, reverse
):
    for _ in range(4):
        ledger.append(padding=padding, reverse=reverse)
    # Their very existence is NOT required during routing, let alone opening/parsing them.
    for path in ledger.payloads:
        path.unlink()
    reads, decoded = trace(monkeypatch)
    counters = Counters()
    router = routing.RoutingPass(ledger.identity, counters=counters)
    batch, boundary = router.advance()
    assert not boundary and len(batch) == 4
    assert reads == [str(p) for p in ledger.paths]
    assert len(decoded) == counters.routing_parses == counters.routing_reads == 4
    assert counters.routing_bytes == sum(p.stat().st_size for p in ledger.paths)
    assert counters.validation_reads == counters.legacy_reads == counters.discriminator_reads == 0
    assert all(e.pin["sha256"] and not hasattr(e, "payload") for e in batch)


@pytest.mark.parametrize("seq", [0, 5, 8, 9, 10, 15])
@pytest.mark.parametrize("schema", [routing.V1, routing.V2, "unknown"])
def test_only_seq9_discriminator_can_consume_one_payload_in_routing(
    ledger, monkeypatch, seq, schema
):
    for _ in range(seq):
        ledger.append()
    ledger.boundary(schema)
    reads, _ = trace(monkeypatch)
    counters = Counters()
    router = routing.RoutingPass(ledger.identity, counters=counters)
    if seq == 9 and schema == "unknown":
        with pytest.raises(ValueError, match="unknown"):
            router.advance()
    else:
        batch, boundary = router.advance()
        assert len(batch) == seq + 1
        assert boundary is not (seq == 9 and schema == routing.V1)
    assert counters.routing_reads == seq + 1
    assert counters.discriminator_reads == (1 if seq == 9 else 0)
    assert reads == [str(p) for p in ledger.paths] + (
        [str(ledger.payloads[-1])] if seq == 9 else []
    )


def test_discriminator_is_json_not_text_or_member_order_heuristic(ledger):
    for _ in range(9):
        ledger.append()
    ledger.boundary(routing.V1)
    path = ledger.payloads[-1]
    value = json.loads(path.read_bytes())
    path.write_text(" " * 4096 + json.dumps(dict(reversed(list(value.items())))) + "\n")
    router = routing.RoutingPass(ledger.identity)
    _, boundary = router.advance()
    assert not boundary
    path.write_text('{"schema":"' + routing.V1 + '","schema":"' + routing.V2 + '"}')
    with pytest.raises(ValueError):
        routing.RoutingPass(ledger.identity).advance()


@pytest.mark.parametrize(
    "change",
    [
        "extra-field",
        "seq-bool",
        "seq-float",
        "previous",
        "receipt",
        "schema",
        "origin",
        "gap",
        "pending",
        "permit",
    ],
)
def test_malformed_routing_never_enters_payload_processing(ledger, monkeypatch, change):
    ledger.append()
    record = dict(ledger.records[0])
    if change == "extra-field":
        record["extra"] = True
    elif change == "seq-bool":
        record["seq"] = False
    elif change == "seq-float":
        record["seq"] = 0.0
    elif change == "previous":
        record["previous"] = "a" * 64
    elif change == "receipt":
        record["receipt"] = "bad"
    elif change == "schema":
        record["schema"] = "unknown"
    elif change == "origin":
        record["origin"] = {**record["origin"], "surplus": 1}
    elif change == "gap":
        ledger.paths[0].rename(ledger.directory / "00000001.json")
    elif change == "pending":
        private_file(ledger.directory, "00000001.pending", b"{}")
    else:
        private_file(ledger.directory.parent, ledger.directory.with_suffix(".permit").name, b"{}")
    if change not in {"gap", "pending", "permit"}:
        ledger.paths[0].write_text(json.dumps(record))
    reads, _ = trace(monkeypatch)
    with pytest.raises((ValueError, TypeError)):
        retained.structural(ledger.identity)
    assert not set(reads) & {str(p) for p in ledger.payloads}


def test_routing_counter_and_limit_span_multiple_boundaries(ledger, monkeypatch):
    ledger.boundary()
    ledger.append()
    ledger.boundary()
    counters = Counters()
    router = routing.RoutingPass(ledger.identity, counters=counters)
    assert router.advance()[1] is True
    assert counters.routing_reads == 1
    assert router.advance()[1] is True
    assert counters.routing_reads == 3
    assert router.advance() == ([], False)
    assert counters.routing_reads == 3
    monkeypatch.setattr(history, "LIMIT", 2)
    with pytest.raises(ValueError):
        routing.RoutingPass(ledger.identity)


@pytest.mark.parametrize("change", ["file", "parent", "name", "content"])
def test_routed_canonical_substitution_refuses_before_materialization(ledger, monkeypatch, change):
    ledger.append()
    ledger.boundary()
    original = routing.RoutingPass.advance

    def changed(router):
        result = original(router)
        path = ledger.paths[0]
        if change == "file":
            path.rename(path.with_suffix(".displaced"))
            private_file(ledger.directory, path.name, b"{}")
        elif change == "parent":
            ledger.directory.rename(ledger.directory.with_suffix(".old"))
            ledger.directory.mkdir(mode=0o700)
        elif change == "name":
            path.rename(path.with_name("00000008.json"))
        else:
            path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(routing.RoutingPass, "advance", changed)
    reads, _ = trace(monkeypatch)
    with pytest.raises((ValueError, OSError)):
        retained.structural(ledger.identity)
    assert not set(reads) & {str(p) for p in ledger.payloads}


def test_v2_cumulative_budget_is_reserved_before_any_prefix_payload_decode(ledger, monkeypatch):
    ledger.append(payload={"ordinary": "x" * 3000})
    ledger.boundary()
    reads, decoded = trace(monkeypatch)
    canonical_size = sum(p.stat().st_size for p in ledger.paths)
    with pytest.raises(ValueError, match="budget"):
        retained.structural(ledger.identity, limits=Limits(raw_bytes=canonical_size + 10))
    assert reads == [str(p) for p in ledger.paths]
    assert len(decoded) == 2  # Envelopes only, no ordinary payload or fallback.


def test_legacy_large_valid_structural_inputs_ignore_new_aggregate_cap(ledger):
    ledger.append(payload={"large": "x" * 3000})
    counters = Counters()
    chain = retained.structural(
        ledger.identity, limits=Limits(files=0, raw_bytes=0), counters=counters
    )
    assert chain[0][1] == {"large": "x" * 3000}
    assert counters.validation_reads == counters.validation_reserved_bytes == 0
    assert counters.legacy_reads == 1 and counters.legacy_bytes > 3000


def test_strict_mode_reserves_before_even_first_envelope_decode(ledger, monkeypatch):
    ledger.append()
    reads, decoded = trace(monkeypatch)
    with pytest.raises(ValueError, match="budget"):
        retained.structural(ledger.identity, strict=True, limits=Limits(raw_bytes=1))
    assert reads == decoded == []


def test_strict_mode_canonical_and_payload_are_charged_once_and_rebound(ledger):
    ledger.append()
    size = ledger.paths[0].stat().st_size + ledger.payloads[0].stat().st_size
    counters = Counters()
    chain = retained.structural(
        ledger.identity, strict=True, limits=Limits(files=2, raw_bytes=size), counters=counters
    )
    assert chain[0][1] == {"fabricated_payload": 0}
    assert counters.validation_reserved_bytes == counters.validation_bytes == size
    assert counters.validation_reads == counters.validation_parses == 2
    assert counters.routing_reads == counters.legacy_reads == 0


def scheduling_oracle(monkeypatch, calls, *, extra=None):
    """Replace ONLY the always-refusing prerequisite stub. Never call history.load/admit here."""

    def validate(identity, chain, reader):
        calls.append(len(chain))
        assert chain[-1][1]["schema"] == routing.V2
        if extra is not None:
            reader.evidence(extra)

    monkeypatch.setattr(routing, "_validate_v2_prefix", validate)


def test_v2_then_oversized_ordinary_prefix_then_v2_stops_before_suffix_payload_parse(
    ledger, monkeypatch
):
    ledger.boundary()
    first_bytes = sum(p.stat().st_size for p in (*ledger.paths, *ledger.payloads))
    ledger.append(payload={"oversized": "x" * 8000})
    ledger.boundary()
    calls = []
    scheduling_oracle(monkeypatch, calls)
    reads, decoded = trace(monkeypatch)
    counters = Counters()
    with pytest.raises(ValueError, match="budget"):
        retained.structural(
            ledger.identity, limits=Limits(raw_bytes=first_bytes + 2000), counters=counters
        )
    assert calls == [1]
    assert str(ledger.payloads[1]) not in reads and str(ledger.payloads[2]) not in reads
    assert all(b'"oversized"' not in data for data in decoded)
    assert counters.routing_reads == 3 and counters.legacy_reads == 0
    assert counters.validation_passes == 2


def test_v2_then_ordinary_terminal_suffix_keeps_legacy_suffix_limits(ledger, monkeypatch):
    ledger.boundary()
    size = sum(p.stat().st_size for p in (*ledger.paths, *ledger.payloads))
    ledger.append("terminal", {"ordinary_terminal_placeholder": "x" * 8000})
    calls = []
    scheduling_oracle(monkeypatch, calls)
    reads, _ = trace(monkeypatch)
    counters = Counters()
    chain = retained.structural(ledger.identity, limits=Limits(raw_bytes=size), counters=counters)
    assert len(chain) == 2 and calls == [1]
    assert counters.validation_reserved_bytes == size
    assert counters.legacy_reads == 1 and counters.legacy_bytes > size
    # Suffix routing happens after first-prefix validation and before suffix payload IO.
    assert reads.index(str(ledger.paths[1])) > reads.index(str(ledger.payloads[0]))
    assert reads.index(str(ledger.paths[1])) < reads.index(str(ledger.payloads[1]))


def test_repeated_boundaries_new_passes_recharge_prior_dependencies(ledger, monkeypatch, tmp_path):
    ledger.boundary()
    ledger.append()
    ledger.boundary()
    witness = private_file(tmp_path, "original-witness.json")
    calls = []
    scheduling_oracle(monkeypatch, calls, extra=witness)
    reads, _ = trace(monkeypatch)
    counters = Counters()
    retained.structural(ledger.identity, counters=counters)
    assert calls == [1, 3]
    assert counters.validation_passes == 2 and counters.routing_reads == 3
    assert reads.count(str(witness)) == reads.count(str(ledger.payloads[0])) == 2
    assert counters.validation_reserved_files == 3 + 7  # prefix1+external, full prefix+external
    assert counters.validation_reads == 10


def test_prior_external_binding_drift_during_suffix_routing_cannot_be_rebased(
    ledger, monkeypatch, tmp_path
):
    ledger.boundary()
    ledger.append()
    ledger.boundary()
    witness = private_file(tmp_path, "witness.json")
    calls = []
    scheduling_oracle(monkeypatch, calls, extra=witness)
    advance = routing.RoutingPass.advance

    def change(router):
        if router.position:
            witness.write_bytes(witness.read_bytes().replace(b"1", b"2"))
        return advance(router)

    monkeypatch.setattr(routing.RoutingPass, "advance", change)
    with pytest.raises(ValueError, match="conflicting"):
        retained.structural(ledger.identity)
    # Test callback started second validation but its dependency reader refused old-byte drift.
    assert calls == [1, 3]


def test_v1_at_non_nine_boundary_is_never_a_legacy_fallback(ledger, monkeypatch):
    ledger.boundary(routing.V1)
    monkeypatch.setattr(
        routing, "_validate_v2_prefix", lambda *_: pytest.fail("wrong family routed")
    )
    with pytest.raises(ValueError, match="non-v2"):
        retained.structural(ledger.identity)


def test_dependency_view_addresses_are_validated_without_store_get(ledger, monkeypatch):
    ledger.boundary()
    key = ledger.store.put("snapshots", {"synthetic": "snapshot"})
    calls = []

    def verify(identity, chain, reader):
        calls.append(reader.counters.validation_reads)
        assert chain[0][2].get("snapshots", key) == {"synthetic": "snapshot"}
        assert reader.counters.validation_reads == calls[-1] + 1

    monkeypatch.setattr(routing, "_validate_v2_prefix", verify)
    monkeypatch.setattr(Store, "get", lambda *_: pytest.fail("unbudgeted dependency bypass"))
    retained.structural(ledger.identity)
    assert calls == [2]


def test_legacy_seq9_discriminator_then_v2_prefix_charges_discriminator_again(ledger, monkeypatch):
    for _ in range(9):
        ledger.append()
    ledger.boundary(routing.V1)
    ledger.append()
    ledger.boundary()
    calls = []
    scheduling_oracle(monkeypatch, calls)
    counters = Counters()
    reads, _ = trace(monkeypatch)
    retained.structural(ledger.identity, counters=counters)
    assert calls == [12]
    assert counters.routing_reads == 12 and counters.discriminator_reads == 1
    assert reads.count(str(ledger.payloads[9])) == 2
    assert counters.validation_reserved_files == 24
    assert counters.validation_bytes == sum(
        p.stat().st_size for p in (*ledger.paths, *ledger.payloads)
    )


def test_reader_budget_failure_has_no_legacy_fallback_at_later_boundary(ledger, monkeypatch):
    ledger.boundary()
    ledger.append(payload={"oversized": "x" * 3000})
    ledger.boundary()
    first_size = sum(p.stat().st_size for p in (ledger.paths[0], ledger.payloads[0]))
    calls = []
    scheduling_oracle(monkeypatch, calls)
    materialize = routing._materialize

    def forbid_fallback(envelopes, *, reader, counters):
        assert reader is not None, "budget failure fell back to legacy materialization"
        return materialize(envelopes, reader=reader, counters=counters)

    monkeypatch.setattr(routing, "_materialize", forbid_fallback)
    with pytest.raises(ValueError, match="budget"):
        retained.structural(ledger.identity, limits=Limits(raw_bytes=first_size + 1000))
    assert calls == [1]


def test_discriminator_change_after_routing_is_not_rebased(ledger, monkeypatch):
    for _ in range(9):
        ledger.append()
    ledger.boundary(routing.V1)
    advance = routing.RoutingPass.advance

    def change(router):
        result = advance(router)
        path = ledger.payloads[-1]
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(routing.RoutingPass, "advance", change)
    with pytest.raises(ValueError, match="conflicting"):
        retained.structural(ledger.identity)


def test_invalid_json_is_counted_as_attempted_parse_not_zero_io(ledger, monkeypatch):
    ledger.append()
    ledger.paths[0].write_bytes(b"{")
    counters = Counters()
    with pytest.raises(ValueError):
        routing.RoutingPass(ledger.identity, counters=counters).advance()
    assert counters.routing_reads == counters.routing_parses == counters.routing_bytes == 1


def test_unknown_non_nine_schema_cannot_invoke_v2_semantic_stub(ledger, monkeypatch):
    ledger.boundary("unknown")
    monkeypatch.setattr(routing, "_validate_v2_prefix", lambda *_: pytest.fail("schema is not v2"))
    with pytest.raises(ValueError, match="non-v2"):
        retained.structural(ledger.identity)


def test_same_size_mutation_after_raw_read_does_not_rebind_routing_signature(ledger, monkeypatch):
    ledger.append()
    raw = retained.raw

    def replace(path):
        result = raw(path)
        if str(path) == str(ledger.paths[0]):
            ledger.paths[0].write_bytes(
                ledger.paths[0].read_bytes().replace(b"prepared", b"terminal")
            )
        else:
            pytest.fail("changed canonical routed into ordinary payloads")
        return result

    monkeypatch.setattr(retained, "raw", replace)
    with pytest.raises(ValueError, match="during routing"):
        retained.structural(ledger.identity)


@pytest.mark.parametrize("acceptor", ["load", "admit", "default-lock"])
def test_refusing_v2_gate_reads_exact_routing_and_bounded_prefix_files(
    ledger, monkeypatch, acceptor
):
    from niri_desktop_continuity import operation_lock

    ledger.boundary()
    reads, _ = trace(monkeypatch)  # BOTH legacy routing and the new reservation-bound helper.
    with pytest.raises(ValueError) as caught:
        if acceptor == "default-lock":
            with operation_lock.operation_lock(ledger.identity):
                pytest.fail("orphan v2 must refuse")
        else:
            with operation_lock.operation_lock(
                ledger.identity, effectful=False, existing_only=True
            ):
                getattr(history, acceptor)(ledger.identity)
    causes, error = [], caught.value
    while error is not None:
        causes.append(str(error))
        error = error.__cause__
    assert "orphan history record" in " ".join(causes)
    assert reads == [str(ledger.paths[0]), str(ledger.paths[0]), str(ledger.payloads[0])]
