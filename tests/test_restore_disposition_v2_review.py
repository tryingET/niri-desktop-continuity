"""Reviewer contract oracles, independent of the v2 model's wire constructors."""

import json
from copy import deepcopy

import pytest
from restore_v2_fixtures import next_attempt
from test_restore_disposition_handwritten import handwritten as handwritten
from test_restore_disposition_handwritten import sha
from test_restore_disposition_v2 import approve, propose
from test_restore_disposition_v2 import unassociated as unassociated
from test_restore_disposition_v2_chain import finish

from niri_desktop_continuity import operation_lock
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_disposition_v2 as v2
from niri_desktop_continuity import restore_disposition_v2_model as model
from niri_desktop_continuity import restore_host as host
from niri_desktop_continuity import restore_reader as readers


def literal_original(s):
    """Only synthetic files owned by this fixture; never convert a real retained witness."""
    for seq in range(5, 9):
        (s.directory / f"{seq:08d}.json").unlink()
    records = [json.loads((s.directory / f"{i:08d}.json").read_text()) for i in range(5)]
    prepared = s.store.get("receipts", records[0]["receipt"])
    observed = s.store.get("receipts", records[4]["receipt"])
    entry = prepared["plan"]["entries"][0]
    original = {
        "status": "interrupted",
        "windows": [
            {
                "entry": entry,
                "window_id": 1,
                "status": "launch-indeterminate",
                "geometry_coverage": {"width": "requested-pending", "position": "not-recorded"},
                "process_receipt": sha(observed["evidence"]),
            }
        ],
        "effects": [],
        "final_observation": {"unavailable": True},
        "native_session": "not-proved",
        "error_type": "ValueError",
        "error": "foreign active window",
    }
    s.source = prepared["snapshot_digest"]
    s.interrupted = s.store.put("receipts", original)
    s.result.write_text(
        json.dumps({"snapshot_digest": s.source, "receipt_digest": s.interrupted, **original})
    )
    assert s.exit_file.read_bytes() == b"2\n"
    return s


def test_r1_handwritten_actual_wire_qualifies(handwritten):
    s = literal_original(handwritten)
    original = s.result.read_bytes()
    result = d.apply(s.store, approve(s, propose(s)), observer=s.observe)
    assert result["status"] == "operator-accepted-partial"
    assert result["effects"] == [] and s.result.read_bytes() == original


def test_r1_unreviewed_process_exec_observed_alias_refuses(handwritten):
    s = literal_original(handwritten)
    receipt = s.store.get("receipts", s.interrupted)
    receipt["windows"][0]["status"] = "process-exec-observed"
    s.interrupted = s.store.put("receipts", receipt)
    s.result.write_text(
        json.dumps({"snapshot_digest": s.source, "receipt_digest": s.interrupted, **receipt})
    )
    with pytest.raises(ValueError):
        propose(s)
    assert not list((s.store.root / "plans").iterdir())


@pytest.mark.parametrize("change", ["topology", "process", "expiry"])
def test_r2_live_veto_after_last_capacity_return_before_consume(unassociated, monkeypatch, change):
    s = unassociated
    key = propose(s)
    approval = approve(s, key)
    capacity = readers.DependencyReader.reserve_commit
    changed = []
    observe = s.observe
    Process = host.Process

    class DriftingProcess(Process):
        def live(self):
            super().live()
            if changed:
                raise ValueError("fabricated process exit during capacity check")

    monkeypatch.setattr(host, "Process", DriftingProcess)

    def live():
        value = observe()
        if changed and change == "topology":
            value["coherent"] = False
        return value

    def check(reader, *args, **kwargs):
        result = capacity(reader, *args, **kwargs)
        if (s.directory / "00000005.pending").exists():
            changed.append(True)
            if change == "expiry":
                expires = s.store.get("plans", key)["expires"]
                monkeypatch.setattr(model.time, "time", lambda: expires)
        return result

    # Topology case isolates the IPC veto; process case isolates the retained proof's live veto.
    if change != "process":
        monkeypatch.setattr(host, "Process", Process)
    monkeypatch.setattr(readers.DependencyReader, "reserve_commit", check)
    with pytest.raises(ValueError):
        d.apply(s.store, approval, observer=live)
    assert changed and (s.directory / "00000005.pending").exists()
    assert not s.store.path("used", approval).exists()
    assert not (s.directory / "00000005.json").exists()


def test_r3_exact_seven_field_segment(unassociated):
    s = unassociated
    with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
        active, chain, reader = v2.source(s.store, s.identity, s.attempt)
        try:
            assert model.eligible(active, chain) == {
                "start": 0,
                "count": 5,
                "previous": None,
                "exec_intent": chain[3][0]["receipt"],
                "exec_observed": chain[4][0]["receipt"],
                "process_receipt": sha(chain[4][1]["evidence"]),
                "baseline_digest": sha(chain[0][1]["plan"]["baseline"]),
            }
        finally:
            reader.close()


@pytest.mark.parametrize("surface", ["limits", "receipt"])
def test_r3_exact_approved_partial_literals(unassociated, surface):
    s = unassociated
    key = propose(s)
    if surface == "limits":
        value = s.store.get("plans", key)["limits"]
    else:
        result = d.apply(s.store, approve(s, key), observer=s.observe)
        value = s.store.get("receipts", result["receipt_digest"])
    assert value["historical_association"] == "not-recorded"
    assert value["outcome"] == "unresolved"


def test_r4_same_identity_incidental_metadata_cannot_evade_eligibility(unassociated):
    s = unassociated
    with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
        active, chain, reader = v2.source(s.store, s.identity, s.attempt)
        try:
            original = active["_launches"]["launches"][0]["process"]
            # Exercise comparison projection; NOT a claim that extra fields are valid wire pins.
            active["_prior_processes"] = [{**original, "comm": "changed", "cgroup": "changed"}]
            with pytest.raises(ValueError):
                model.eligible(active, chain)
        finally:
            reader.close()


def test_r4_different_start_same_pid_is_not_permanently_banned(unassociated, tmp_path, monkeypatch):
    s = unassociated
    finish(s)
    baseline = s.observe()
    baseline["state"]["windows"] = [w for w in baseline["state"]["windows"] if w["id"] != 12000]
    s.observe = lambda: deepcopy(baseline)  # Prior host exited before this fresh preparation.
    following = next_attempt(s, tmp_path / "following", 1, pid=2000, start_ticks=2)
    Process = host.Process

    class FreshProcess(Process):
        def __init__(self, pid):
            super().__init__(pid)
            if pid == 2000:
                self.pin["start_ticks"] = 2

    monkeypatch.setattr(host, "Process", FreshProcess)
    key, approval, result = finish(following)
    assert result["status"] == "operator-accepted-partial"
    assert d.apply(following.store, approval, observer=lambda: pytest.fail("historical only"))[
        "historical"
    ]
    plan = following.store.get("plans", key)
    assert plan["segment"]["start"] == 6
    assert next(p for p in plan["current"]["processes"] if p["pid"] == 2000)["start_ticks"] == 2


@pytest.mark.parametrize("surface", ["eligibility", "partition"])
@pytest.mark.parametrize("incidental", [{"comm": "different"}, {"cgroup": "different"}])
def test_r4_same_tuple_ignores_incidental_metadata(unassociated, surface, incidental):
    s = unassociated
    current = s.store.get("plans", propose(s))["current"]
    with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
        active, chain, reader = v2.source(s.store, s.identity, s.attempt)
        try:
            process = active["_launches"]["launches"][0]["process"]
            # Internal predicate projection only; closed persisted pins still reject extra fields.
            active["_prior_processes"] = [{**process, **incidental}]
            with pytest.raises(ValueError):
                if surface == "eligibility":
                    model.eligible(active, chain)
                else:
                    model.partition(current, active, chain)
        finally:
            reader.close()


def test_r4_identity_includes_boot_but_history_still_rejects_foreign_boot(unassociated):
    s = unassociated
    assert model.process_identity(
        {"boot_id": "one", "pid": 2000, "start_ticks": 2}
    ) != model.process_identity({"boot_id": "two", "pid": 2000, "start_ticks": 2})
    rows = []
    for seq in range(5):
        record = json.loads((s.directory / f"{seq:08d}.json").read_text())
        payload = s.store.get("receipts", record["receipt"])
        rows.append((record["type"], payload))
        (s.directory / f"{seq:08d}.json").unlink()
    for pin in (
        rows[2][1]["evidence"]["bootstrap"],
        rows[3][1]["details"]["process"],
        rows[4][1]["evidence"]["process"],
    ):
        pin["boot_id"] = "different-boot"
    rows[4][1]["intent"] = sha(rows[3][1])
    from restore_v2_fixtures import append

    append(s, s.store, s.attempt, rows)
    with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
        with pytest.raises(ValueError, match="foreign bootstrap binding"):
            v2.source(s.store, s.identity, s.attempt)


def test_r3_seven_fields_bound_to_actual_nonzero_suffix(unassociated, tmp_path):
    s = unassociated
    finish(s)
    following = next_attempt(s, tmp_path / "following", 1)
    key = propose(following)
    records = [json.loads((s.directory / f"{i:08d}.json").read_text()) for i in range(6, 11)]
    prepared = following.store.get("receipts", records[0]["receipt"])
    observed = following.store.get("receipts", records[4]["receipt"])
    assert following.store.get("plans", key)["segment"] == {
        "start": 6,
        "count": 5,
        "previous": records[0]["previous"],
        "exec_intent": records[3]["receipt"],
        "exec_observed": records[4]["receipt"],
        "process_receipt": sha(observed["evidence"]),
        "baseline_digest": sha(prepared["plan"]["baseline"]),
    }


@pytest.mark.parametrize(
    "change",
    [
        "old-four-fields",
        "extra",
        "alias",
        "start",
        "count",
        "previous",
        "exec_intent",
        "exec_observed",
        "process_receipt",
        "baseline_digest",
        "intent-envelope",
        "observed-envelope",
    ],
)
def test_r3_nonzero_segment_every_reference_is_authoritative(unassociated, tmp_path, change):
    s = unassociated
    finish(s)
    following = next_attempt(s, tmp_path / "following", 1)
    plan = following.store.get("plans", propose(following))
    segment = plan["segment"]
    if change == "old-four-fields":
        for field in ("exec_intent", "exec_observed", "process_receipt"):
            del segment[field]
    elif change == "extra":
        segment["extra"] = True
    elif change == "alias":
        segment["exec_observation"] = segment.pop("exec_observed")
    elif change in {"start", "count"}:
        segment[change] += 1
    elif change.endswith("-envelope"):
        seq = 9 if change == "intent-envelope" else 10
        field = "exec_intent" if seq == 9 else "exec_observed"
        segment[field] = sha(json.loads((s.directory / f"{seq:08d}.json").read_text()))
    else:
        segment[change] = "f" * 64
    key = following.store.put("plans", plan)
    with pytest.raises(ValueError):
        approve(following, key)


@pytest.mark.parametrize("change", ["old-association", "old-outcome", "mixed-limits"])
def test_r3_old_unreviewed_limit_literals_are_not_aliases(unassociated, change):
    s = unassociated
    plan = s.store.get("plans", propose(s))
    if change != "old-outcome":
        plan["limits"]["historical_association"] = "unrecorded"
    if change != "old-association":
        plan["limits"]["outcome"] = "process-exec-observed-window-association-unresolved"
    with pytest.raises(ValueError):
        approve(s, s.store.put("plans", plan))


@pytest.mark.parametrize(
    "field,value",
    [
        ("historical_association", "unrecorded"),
        ("outcome", "process-exec-observed-window-association-unresolved"),
    ],
)
def test_r3_old_receipt_literals_fence_every_consumer(
    unassociated, tmp_path, monkeypatch, field, value
):
    from test_restore_disposition_v2_adversarial import all_refuse, rewrite_latest

    s = unassociated
    key, approval, result = finish(s)

    def mutate(plan, receipt):
        receipt[field] = value

    changed = rewrite_latest(s, key, approval, result, mutate)
    all_refuse(s, changed, monkeypatch, tmp_path)
