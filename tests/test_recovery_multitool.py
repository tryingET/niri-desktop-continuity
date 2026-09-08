"""Opaque multi-conversation oracles, not Pi/Claude/Codex native integration proof."""

from copy import deepcopy

import pytest
from test_recovery_orchestration import approve, command, execute, plan
from test_recovery_orchestration import fixture as fixture
from test_recovery_review_regressions import repin
from test_recovery_utilities import ref, settings

from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.recovery_protocol import (
    VERSION,
    VERSION2,
    coverage,
    observation,
    proof,
)
from niri_desktop_continuity.store import Store

# Handwritten independent identities; no app names or native-ID hashing recipe in public IPC.
REFS = ("1" * 64, "2" * 64, "3" * 64)
RENAMED = ("e" * 64, "a" * 64, "7" * 64)
PREDICATES = ("file", "cwd", "runtime", "bootstrap", "surface", "causal_window")


def counts(unique=3, *, missing=False, utility=None):
    return {
        "owned_native_processes": 4 if missing else 3,
        "associated_processes": 3,
        "omitted_associations": 1 if missing else 0,
        "unique_saved_conversations": unique,
        "unresolved_associations": 1 if missing else 0,
        **(
            {
                "owned_utilities": 1,
                "image_unobservable_utilities": int(utility == "capability-btop"),
            }
            if utility
            else {}
        ),
    }


@pytest.mark.parametrize(
    "saved_refs,unique", [(REFS, 3), (RENAMED, 3), ((REFS[0], REFS[0], REFS[2]), 2)]
)
@pytest.mark.parametrize("utility", [None, "observed-image", "capability-btop"])
def test_three_processes_distinct_refs_or_same_ref_dedup(fixture, saved_refs, unique, utility):
    data = fixture(saved_refs=saved_refs, utility=utility)
    value = settings(data)
    processes = value["observation"]["processes"]
    assert sorted((p["pin"]["pid"], p["pin"]["start_ticks"]) for p in processes) == [
        (102, 43),
        (105, 46),
        (106, 47),
    ]
    pins = [digest(p["pin"]) for p in processes]
    assert pins == sorted(set(pins))
    expected_refs = sorted(set(saved_refs))
    key = plan(data)
    planned = Store(data["root"] / "state").get("plans", key)["recovery"]
    assert planned["observation"]["session_refs"] == expected_refs
    assert planned["coverage"] == counts(unique, utility=utility)
    args = ["--accept-utility-limit", ref(data)] if utility == "capability-btop" else []
    approval = approve(data, key, *args)
    assert approval == approve(data, key, *args)
    assert not (data["root"] / "effects.jsonl").exists()
    report, code = execute(data, approval)
    expected = "verified-with-accepted-limitations" if args else "verified"
    assert code == 0 and report["status"] == expected
    assert report["coverage"] == counts(unique, utility=utility)
    assert [p["session_ref"] for p in report["proof"]["native"]] == expected_refs
    assert report["overall_native_coverage_complete"] is (not args)
    if utility:
        assert report["saved_conversations_recovered"] == unique
        assert report["accepted_utility_limits"] == ([ref(data)] if args else [])
        assert report["overall_image_coverage_complete"] is (not args)
    else:
        assert "saved_conversations_recovered" not in report  # Frozen v1 shape.
    terminal = data["root"] / "ledger/recovery-terminal" / f"{approval}.json"
    before = terminal.read_bytes()
    fresh, code = command(data, "verify", approval, "--kind", "reconstruction")
    assert code == 0 and fresh["status"] == fresh["historical_status"] == expected
    inspected, code = command(data, "inspect", approval, "--kind", "reconstruction")
    assert code == 0 and inspected["status"] == expected
    assert inspected["retry_authorized"] is False
    with pytest.raises(ValueError):
        execute(data, approval)
    assert terminal.read_bytes() == before


@pytest.mark.parametrize("utility", [None, "observed-image"])
def test_consistent_opaque_renaming_preserves_success_and_failure(fixture, utility):
    data = fixture(saved_refs=REFS, utility=utility)
    original = settings(data)
    renamed = deepcopy(original)
    mapping = dict(zip(REFS, RENAMED, strict=True))
    for item in renamed["observation"]["processes"]:
        item["session_ref"] = mapping[item["session_ref"]]
    renamed["observation"]["session_refs"] = sorted(RENAMED)
    for item in renamed["proof"]["native"]:
        item["session_ref"] = mapping[item["session_ref"]]
    renamed["proof"]["native"].sort(key=lambda item: item["session_ref"])
    schema = VERSION2 if utility else VERSION
    for value in (original, renamed):
        observed = observation(value["observation"], digest([]), schema)
        assert coverage(observed, [], schema) == (counts(utility=utility), [], [])
        for failing in (False, True):
            candidate = deepcopy(value["proof"])
            if failing:
                target = REFS[1] if value is original else mapping[REFS[1]]
                next(p for p in candidate["native"] if p["session_ref"] == target)["cwd"] = False
            assert (
                proof(candidate, observed["session_refs"], schema, observed.get("utilities", ()))
                is not failing
            )


@pytest.mark.parametrize("utility", [None, "observed-image"])
@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("predicate", PREDICATES)
def test_each_native_predicate_is_independently_mandatory(fixture, utility, index, predicate):
    data = fixture(saved_refs=REFS, utility=utility)
    value = settings(data)
    value["proof"]["native"][index][predicate] = False
    assert (
        proof(
            value["proof"],
            list(REFS),
            data["profile"]["schema"],
            value["observation"].get("utilities", ()),
        )
        is False
    )


@pytest.mark.parametrize("utility", [None, "observed-image"])
@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("damage", ["missing", "extra", "duplicate"])
def test_native_proof_set_never_succeeds_with_missing_extra_or_duplicate(
    fixture, utility, index, damage
):
    data = fixture(saved_refs=REFS, utility=utility)
    value = settings(data)
    native = value["proof"]["native"]
    if damage == "missing":
        native.pop(index)
    else:
        added = deepcopy(native[index])
        if damage == "extra":
            added["session_ref"] = "f" * 64
        native.append(added)
        native.sort(key=lambda item: item["session_ref"])
    args = (
        value["proof"],
        list(REFS),
        data["profile"]["schema"],
        value["observation"].get("utilities", ()),
    )
    if damage == "missing":
        assert proof(*args) is False  # Valid incomplete proof, not a transport refusal.
    else:
        with pytest.raises(ValueError):
            proof(*args)


def test_three_native_omission_and_utility_limit_require_separate_exact_approval(fixture):
    data = fixture(saved_refs=REFS, missing=True, utility="capability-btop")
    with pytest.raises(ValueError):
        approve(data, plan(data), "--accept-utility-limit", ref(data))
    key = plan(data, "--omit-association", data["omission"])
    omission = ["--accept-omission", data["omission"]]
    limit = ["--accept-utility-limit", ref(data)]
    for args in (
        [],
        omission,
        limit,
        omission + ["--accept-utility-limit", "0" * 64],
        omission + limit * 2,
    ):
        with pytest.raises(ValueError):
            approve(data, key, *args)
    assert not (data["root"] / "effects.jsonl").exists()
    approval = approve(data, key, *omission, *limit)
    report, code = execute(data, approval)
    assert code == 0 and report["status"] == "verified-with-accepted-limitations"
    assert report["coverage"] == counts(missing=True, utility="capability-btop")
    assert report["saved_conversations_recovered"] == 3
    assert report["accepted_omissions"][0]["process_pin_digest"] == data["omission"]
    assert report["accepted_utility_limits"] == [ref(data)]
    assert report["overall_native_coverage_complete"] is False
    assert report["overall_image_coverage_complete"] is False


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("missing-native", "partial"),
        ("missing-utility", "indeterminate"),
        ("extra-native", "indeterminate"),
        ("duplicate-native", "indeterminate"),
    ],
)
def test_incomplete_execution_retains_decisions_and_never_upgrades(
    fixture, monkeypatch, damage, expected
):
    data = fixture(saved_refs=REFS, utility="capability-btop", missing=True)
    value = settings(data)
    good = deepcopy(value["proof"])
    if damage == "missing-native":
        value["proof"]["native"].pop(1)
    elif damage == "missing-utility":
        value["proof"]["utilities"] = []
    elif damage == "extra-native":
        value["proof"]["native"].append({**good["native"][0], "session_ref": "f" * 64})
    else:
        value["proof"]["native"].insert(1, deepcopy(good["native"][0]))
    repin(data, value)  # Fabricated pinned settings only, before planning; no authority upgrade.
    key = plan(data, "--omit-association", data["omission"])
    approval = approve(
        data, key, "--accept-omission", data["omission"], "--accept-utility-limit", ref(data)
    )
    report, code = execute(data, approval)
    assert code == 2 and report["status"] == expected
    assert (report["proof"] is not None) is (expected == "partial")
    assert report["coverage"] == counts(missing=True, utility="capability-btop")
    assert report["saved_conversations_recovered"] == 0  # Aggregate, not a per-ref salvage count.
    assert report["accepted_omissions"][0]["process_pin_digest"] == data["omission"]
    assert report["accepted_utility_limits"] == [ref(data)]
    assert report["overall_native_coverage_complete"] is False
    terminal = data["root"] / "ledger/recovery-terminal" / f"{approval}.json"
    before = terminal.read_bytes()
    effects = (data["root"] / "effects.jsonl").read_bytes()
    inspected, code = command(data, "inspect", approval, "--kind", "reconstruction")
    assert code == 2 and inspected["status"] == expected
    assert inspected["retry_authorized"] is False
    with pytest.raises(ValueError):
        execute(data, approval)
    # Stronger fresh observations are explicitly synthetic; history must still not improve.
    monkeypatch.setattr(Adapter, "call", lambda *a, **kw: deepcopy(good))
    fresh, code = command(data, "verify", approval, "--kind", "reconstruction")
    assert code == 2 and fresh["status"] == "indeterminate"
    assert fresh["historical_status"] == expected
    assert fresh["saved_conversations_recovered"] == 0
    assert fresh["accepted_omissions"] == report["accepted_omissions"]
    assert fresh["accepted_utility_limits"] == report["accepted_utility_limits"]
    assert terminal.read_bytes() == before
    assert (data["root"] / "effects.jsonl").read_bytes() == effects
