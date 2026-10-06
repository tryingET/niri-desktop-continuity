"""Reader prerequisites: routing is not semantic validation or accounting authority."""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from test_restore_disposition_handwritten import handwritten as handwritten  # noqa: F401

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity import restore_reader_io as bounded
from niri_desktop_continuity import restore_retained as retained
from niri_desktop_continuity import restore_routing as routing
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.restore_reader import Counters, DependencyReader, Limits, ReaderStore
from niri_desktop_continuity.store import Store


def test_given_legacy_prefix_when_routing_then_no_ordinary_payload_is_read(
    handwritten, monkeypatch
):
    """Given nine retained records, when classified, then route all envelopes first."""
    s = handwritten
    original, routed = retained.raw, []

    def traced(path):
        path = Path(path)
        if path.parent == s.directory:
            routed.append(path.name)
        else:
            assert len(routed) == 9, "ordinary payload read before envelope-only routing completed"
        return original(path)

    monkeypatch.setattr(retained, "raw", traced)
    chain = retained.structural(s.identity)
    assert len(chain) == 9
    assert routed == [f"{i:08d}.json" for i in range(9)]


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Structural-only oracle: these arbitrary payloads do NOT assert valid history semantics."""
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: runtime)

    class Ledger:
        identity = {"boot_id": "fabricated", "socket_device": 1, "socket_inode": 2}

        def __init__(self):
            self.store = Store(tmp_path / "store")
            self.records, self.paths, self.payloads = [], [], []
            with operation_lock.operation_lock(self.identity, effectful=False):
                self.directory = history.fence_path(self.identity)
                self.directory.mkdir(mode=0o700)

        def append(self, kind="prepared", payload=None, *, padding=0, reverse=False):
            seq = len(self.records)
            if payload is None:
                payload = {"fabricated_payload": seq}
            key = self.store.put("receipts", payload)
            record = {
                "schema": history.SCHEMA,
                "seq": seq,
                "previous": digest(self.records[-1]) if seq else None,
                "type": kind,
                "attempt": "a" * 64,
                "receipt": key,
                "origin": {
                    "root": str(self.store.root),
                    "pin": history.directory_pin(self.store.root),
                },
            }
            path = self.directory / f"{seq:08d}.json"
            serialized = dict(reversed(list(record.items()))) if reverse else record
            path.write_text(" " * padding + json.dumps(serialized) + "\n")
            path.chmod(0o600)
            self.records.append(record)
            self.paths.append(path)
            self.payloads.append(self.store.path("receipts", key))
            return record

        def boundary(self, schema=routing.V2):
            return self.append(
                "operator-disposition", {"schema": schema, "marker": len(self.records)}
            )

    return Ledger()


def private_file(tmp_path, name="evidence.json", data=b'{"fabricated": 1}\n'):
    tmp_path.chmod(0o700)
    path = tmp_path / name
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def test_given_unseen_file_when_budget_crosses_then_no_read_or_decode(tmp_path, monkeypatch):
    path = private_file(tmp_path)
    monkeypatch.setattr(retained, "raw", lambda *_: pytest.fail("read before capacity reservation"))
    monkeypatch.setattr(retained, "json_bytes", lambda *_: pytest.fail("parse before reservation"))
    for limits in (
        Limits(files=0),
        Limits(raw_bytes=path.stat().st_size - 1),
        Limits(file_bytes=1),
    ):
        reader = DependencyReader(limits=limits)
        with pytest.raises(ValueError, match="budget"):
            reader.evidence(path)
        assert reader.counters.validation_reads == reader.counters.validation_parses == 0


def test_exact_boundary_memo_and_different_paths_are_not_digest_deduplicated(tmp_path):
    first = private_file(tmp_path)
    second = private_file(tmp_path, "other.json", first.read_bytes())
    size = first.stat().st_size
    reader = DependencyReader(limits=Limits(files=1, raw_bytes=size, file_bytes=size))
    value, pin = reader.evidence(first)
    value["fabricated"] = "caller mutation must not poison memo"
    assert reader.evidence(first)[0] == {"fabricated": 1}
    assert reader.evidence(first.parent / "." / first.name)[1] == pin
    assert reader.unique_bytes == size
    assert reader.counters.validation_reads == reader.counters.validation_parses == 1
    assert reader.counters.memo_hits == 2
    with pytest.raises(ValueError, match="budget"):
        reader.evidence(second)
    assert reader.counters.validation_reads == 1
    reader = DependencyReader(limits=Limits(files=2, raw_bytes=2 * size))
    reader.evidence(first)
    reader.evidence(second)
    assert reader.unique_bytes == 2 * size and len(reader.manifest()) == 2


@pytest.mark.parametrize(
    "field", ["sha256", "length", "inode", "device", "directory", "digest", "path"]
)
def test_conflicting_binding_refused_before_memo_path_dedup(tmp_path, field):
    path = private_file(tmp_path)
    reader = DependencyReader()
    _, pin = reader.evidence(path)
    other = deepcopy(pin)
    if field in {"sha256", "digest"}:
        other[field] = "0" * 64
    elif field == "directory":
        other[field]["inode"] += 1
    elif field == "path":
        other[field] += ".different"
    else:
        other[field] += 1
    with pytest.raises(ValueError):
        reader.evidence(path, expected=other)
    assert reader.counters.memo_hits == 0


@pytest.mark.parametrize("change", ["inode", "growth", "same-size", "parent", "mode", "link"])
def test_substitution_after_reservation_refuses_before_decoder(tmp_path, monkeypatch, change):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = private_file(directory)
    reader = DependencyReader()
    reader.reserve(path)
    data = path.read_bytes()
    if change == "parent":
        directory.rename(tmp_path / "displaced")
        directory.mkdir(mode=0o700)
        (tmp_path / "displaced" / path.name).rename(path)
    elif change == "inode":
        path.rename(path.with_suffix(".old"))
        private_file(directory, path.name, data)
    elif change == "growth":
        path.write_bytes(data + b" ")
    elif change == "same-size":
        path.write_bytes(data.replace(b"1", b"2"))
    elif change == "link":
        os.link(path, directory / "extra-link")
    else:
        path.chmod(0o644)
    monkeypatch.setattr(retained, "json_bytes", lambda *_: pytest.fail("changed evidence decoded"))
    with pytest.raises(ValueError):
        reader.evidence(path)


def test_growth_in_raw_read_never_reaches_decode(tmp_path, monkeypatch):
    path = private_file(tmp_path)
    reader = DependencyReader(limits=Limits(raw_bytes=path.stat().st_size))
    raw = bounded.raw

    def grow(p, reservation, counters):
        path.write_bytes(path.read_bytes() + b" ")
        return raw(p, reservation, counters)

    monkeypatch.setattr(bounded, "raw", grow)
    monkeypatch.setattr(retained, "json_bytes", lambda *_: pytest.fail("grown evidence decoded"))
    with pytest.raises(ValueError, match="grew"):
        reader.evidence(path)
    assert reader.counters.validation_reads == 1 and reader.counters.validation_parses == 0
    assert reader.counters.validation_bytes == reader.counters.validation_requested_bytes == 0
    assert reader.closed and not reader.cache


@pytest.mark.parametrize("stage", ["between-barriers", "after-barriers"])
def test_barrier_pass_is_retired_and_new_reader_detects_drift(tmp_path, monkeypatch, stage):
    import niri_desktop_continuity.restore_reader as module

    path = private_file(tmp_path)
    counters = Counters()
    before = DependencyReader(counters=counters)
    _, pin = before.evidence(path)
    sync = module.sync_artifact

    def changed(p):
        sync(p)
        path.write_bytes(path.read_bytes().replace(b"1", b"2"))

    if stage == "between-barriers":
        monkeypatch.setattr(module, "sync_artifact", changed)
    pins = before.barriers()
    if stage == "after-barriers":
        path.write_bytes(path.read_bytes().replace(b"1", b"2"))
    with pytest.raises(ValueError, match="closed"):
        before.evidence(path)
    assert not before.cache and not before.parsed
    after = DependencyReader(counters=counters)
    after.reserve_pins(pins)
    with pytest.raises(ValueError, match="conflicting"):
        after.evidence(path, expected=pin)
    assert counters.validation_passes == 2
    assert counters.validation_reads == 2 and counters.validation_parses == 1
    assert counters.barrier_attempts == 1


def test_successful_fresh_pass_redecodes_instead_of_reusing_prebarrier_memo(tmp_path):
    path = private_file(tmp_path)
    counters = Counters()
    old = DependencyReader(counters=counters)
    old.evidence(path)
    pins = old.barriers()
    new = DependencyReader(counters=counters)
    new.reserve_pins(pins)
    assert new.evidence(path)[0] == {"fabricated": 1}
    assert counters.validation_reads == counters.validation_parses == 2
    assert (
        counters.validation_reserved_bytes == counters.validation_bytes == 2 * path.stat().st_size
    )
    assert counters.barrier_bound_bytes == path.stat().st_size


def test_barrier_failure_also_permanently_retires_memo(tmp_path, monkeypatch):
    import niri_desktop_continuity.restore_reader as module

    reader = DependencyReader()
    path = private_file(tmp_path)
    reader.evidence(path)

    def failure(_):
        raise OSError("fabricated fsync failure")

    monkeypatch.setattr(module, "sync_artifact", failure)
    with pytest.raises(OSError):
        reader.barriers()
    with pytest.raises(ValueError, match="closed"):
        reader.evidence(path)


@pytest.mark.parametrize("kind", ["snapshots", "plans", "approvals", "receipts", "used"])
def test_store_view_always_uses_dependency_reader_never_store_get(tmp_path, monkeypatch, kind):
    store = Store(tmp_path / "store")
    value = {"fabricated": kind}
    key = store.put(kind, value)
    if kind == "used":
        key = "a" * 64
        private_file(store.root / kind, key + ".json", b'{"fabricated": "used"}\n')
    reader = DependencyReader()
    monkeypatch.setattr(Store, "get", lambda *_: pytest.fail("unbudgeted Store.get bypass"))
    assert ReaderStore(store, reader).get(kind, key) == value
    assert reader.counters.validation_reads == reader.counters.validation_parses == 1


def test_prospective_all_five_artifacts_and_record_slot_reserve_without_writes(tmp_path):
    original = private_file(tmp_path)
    size = original.stat().st_size
    artifacts = [
        (tmp_path / name, b"{}\n") for name in ("plan", "approval", "used", "receipt", "canonical")
    ]
    reader = DependencyReader(limits=Limits(files=6, raw_bytes=size + 15))
    reader.evidence(original)
    before = sorted(tmp_path.iterdir())
    assert reader.reserve_commit(artifacts, history_count=4095) == {
        "unique_files": 6,
        "unique_bytes": size + 15,
        "canonical_records": 4096,
    }
    assert sorted(tmp_path.iterdir()) == before
    with pytest.raises(ValueError, match="slot"):
        reader.reserve_commit(artifacts, history_count=4096)
    reader = DependencyReader(limits=Limits(files=6, raw_bytes=size + 15))
    reader.evidence(original)
    with pytest.raises(ValueError, match="budget"):
        reader.reserve_commit(artifacts + [(tmp_path / "extra", b"x")], history_count=5)
    assert sorted(tmp_path.iterdir()) == before


@pytest.mark.parametrize("limits", [Limits(files=4), Limits(raw_bytes=14), Limits(file_bytes=2)])
def test_tiny_prospective_limit_crossings_precede_any_effect(tmp_path, limits):
    tmp_path.chmod(0o700)
    reader = DependencyReader(limits=limits)
    artifacts = [(tmp_path / str(i), b"{}\n") for i in range(5)]
    with pytest.raises(ValueError, match="budget"):
        reader.reserve_commit(artifacts, history_count=5)
    assert not list(tmp_path.iterdir())


def test_prospective_duplicates_conflict_before_dedup_and_count_actual_existing(tmp_path):
    path = private_file(tmp_path)
    data = path.read_bytes()
    reader = DependencyReader(limits=Limits(files=2, raw_bytes=len(data) + 3))
    artifacts = [(path, data), (path, data), (tmp_path / "new", b"{}\n")]
    assert reader.reserve_commit(artifacts, history_count=5)["unique_files"] == 2
    with pytest.raises(ValueError, match="conflicting"):
        reader.reserve_commit([(path, data), (path, b"wrong")], history_count=5)
    assert reader.closed and not reader.cache and not reader.parsed
    reader = DependencyReader(limits=Limits(files=2, raw_bytes=len(data) + 3))
    with pytest.raises(ValueError, match="conflicts"):
        reader.reserve_commit([(path, b"wrong")], history_count=5)
    assert reader.closed and not reader.cache and not reader.parsed


@pytest.mark.parametrize("field", ["device", "inode", "length"])
@pytest.mark.parametrize("alias", [True, 1.0])
def test_identity_binding_rejects_type_aliases(tmp_path, field, alias):
    path = private_file(tmp_path)
    _, pin = retained.evidence(path)
    pin[field] = alias
    with pytest.raises(ValueError):
        DependencyReader().evidence(path, expected=pin)


@pytest.mark.parametrize("change", ["missing", "inode", "parent"])
def test_postbarrier_fresh_pass_refuses_identity_drift_without_decode(
    tmp_path, monkeypatch, change
):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = private_file(directory)
    old = DependencyReader()
    old.evidence(path)
    pins = old.barriers()
    data = path.read_bytes()
    if change == "missing":
        path.unlink()
    elif change == "inode":
        path.rename(path.with_suffix(".old"))
        private_file(directory, path.name, data)
    else:
        directory.rename(tmp_path / "displaced")
        directory.mkdir(mode=0o700)
        (tmp_path / "displaced" / path.name).rename(path)
    monkeypatch.setattr(
        retained, "json_bytes", lambda *_: pytest.fail("substituted evidence parsed")
    )
    fresh = DependencyReader()
    with pytest.raises((ValueError, OSError)):
        fresh.reserve_pins(pins)
    assert fresh.counters.validation_reads == fresh.counters.validation_parses == 0


def test_reservation_is_not_a_manifest_or_durability_claim(tmp_path):
    path = private_file(tmp_path)
    reader = DependencyReader()
    reader.reserve(path)
    with pytest.raises(ValueError, match="unread"):
        reader.manifest()
    assert reader.closed and not reader.cache
    with pytest.raises(ValueError, match="closed"):
        reader.barriers()
    fresh = DependencyReader()
    fresh.reserve(path)
    with pytest.raises(ValueError, match="unread"):
        fresh.barriers()
    assert fresh.closed


def test_same_content_in_different_stores_is_charged_twice(tmp_path):
    one, two = Store(tmp_path / "one"), Store(tmp_path / "two")
    value = {"fabricated": "same-content"}
    key = one.put("plans", value)
    assert two.put("plans", value) == key
    reader = DependencyReader()
    reader.artifact(one, "plans", key)
    reader.artifact(two, "plans", key)
    assert len(reader.manifest()) == 2
    assert reader.unique_bytes == 2 * one.path("plans", key).stat().st_size


def test_external_raw_witness_uses_same_budget_and_single_path_charge(tmp_path):
    path = private_file(tmp_path, "exit.txt", b"2\n")
    reader = DependencyReader(limits=Limits(files=1, raw_bytes=2))
    assert reader.raw(path)[0] == b"2\n"
    assert reader.raw(path)[0] == b"2\n"
    assert reader.counters.validation_parses == 0 and reader.counters.memo_hits == 1
    assert reader.unique_bytes == 2


def test_failed_reservation_latches_pass_against_cached_success_fallback(tmp_path):
    path = private_file(tmp_path)
    extra = private_file(tmp_path, "extra.json")
    reader = DependencyReader(limits=Limits(files=1))
    reader.evidence(path)
    with pytest.raises(ValueError, match="budget"):
        reader.evidence(extra)
    with pytest.raises(ValueError, match="closed"):
        reader.evidence(path)
    with pytest.raises(ValueError, match="closed"):
        reader.manifest()
    assert not reader.cache and not reader.parsed


def test_normalization_never_hides_symlink_parent_traversal(tmp_path):
    directory = tmp_path / "real"
    directory.mkdir(mode=0o700)
    path = private_file(tmp_path)
    (tmp_path / "link").symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        DependencyReader().evidence(tmp_path / "link" / ".." / path.name)


@pytest.mark.parametrize(
    "limits",
    [
        {"files": 32769},
        {"raw_bytes": 512 * 1024 * 1024 + 1},
        {"file_bytes": 16 * 1024 * 1024 + 1},
        {"files": True},
        {"raw_bytes": 1.0},
    ],
)
def test_injected_limits_can_only_reduce_closed_v2_bounds(limits):
    with pytest.raises(ValueError):
        Limits(**limits)
