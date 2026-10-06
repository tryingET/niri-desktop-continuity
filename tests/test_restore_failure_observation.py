"""Fabricated temporal schedule, not a reconstruction of unretained native samples.

Handwritten oracle: workspace-transfer and focus are acknowledged; a later height
change must stop before the next column intent. Diagnostics may be a DIFFERENT read.
No real native IDs, metadata, processes or applications are test inputs.
"""

import json
import socket
import subprocess
from copy import deepcopy

import pytest
from test_restore_integration import integrated as integrated  # noqa: F401

from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.restore_attempt import Attempt

MOVE = ("move-window-to-workspace", "--window-id", "12000", "--focus", "false", "1")
FOCUS = ("focus-window", "--id", "12000")


@pytest.fixture(autouse=True)
def no_native_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic test attempted socket or process creation")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def setup(s):
    d = s.desktop
    d.columns = {1: [[70], [71]], 2: [[80]]}
    d.focus = 80
    for ws in d.ws:
        ws["is_focused"] = ws["id"] == 2
    d.initialize()
    entry = s.entry(1, 1)
    entry["layout"]["tile_size"][0] = 800.0  # Same as fake new host: no resize needed.
    return entry


@pytest.mark.parametrize("fallback_delta", [92.0, 0.0, 184.0])
def test_given_acknowledged_focus_when_height_changes_then_stop_before_next_intent(
    integrated, monkeypatch, fallback_delta
):
    s = integrated
    entry = setup(s)
    baseline = deepcopy(s.desktop.windows())
    original_read = s.desktop.windows
    original_observed = Attempt.observed
    armed = False
    reads = []
    accepted_focus = []

    def observed(attempt, details):
        nonlocal armed
        original_observed(attempt, details)
        if s.desktop.actions and s.desktop.actions[-1] == FOCUS and "layout" in details:
            accepted_focus.append(deepcopy(details["layout"]))
            armed = True  # The complete stable focus observation is already durable.

    def sample(*, deadline=None):
        windows = original_read(deadline=deadline)
        if armed:
            delta = 92.0 if not reads else (fallback_delta if len(reads) == 1 else 0.0)
            for w in windows:
                for field in ("tile_size", "window_size"):
                    w["layout"][field][1] += delta
            reads.append(deepcopy(windows))
        return windows

    monkeypatch.setattr(Attempt, "observed", observed)
    monkeypatch.setattr(s.desktop, "windows", sample)
    _, result = s.run([entry])

    # Handwritten action oracle; no predictor determines these expected actions.
    assert result["status"] == "interrupted"
    assert result["error_type"] == "ValueError"
    assert result["error"] == "protected dimensions changed"
    assert s.desktop.actions == [MOVE, FOCUS]
    assert result["effects"] == [list(MOVE), list(FOCUS)]
    assert len(accepted_focus) == 1
    assert len(reads) == 2  # One rejected sample, one separate diagnostic re-read.
    assert s.store.pointer("last-reopened") is None
    assert len(s.proofs) == 1 and s.proofs[0].invalid  # FD-style teardown only.
    row = result["windows"][0]
    assert row["status"] == "owned-not-placed"
    assert row["geometry_coverage"]["width"] == "requested-observed"
    assert result["native_session"] == "not-proved"
    failure = result["first_rejected_observation"]
    assert failure["schema"] == "restore-protected-dimensions.v1"
    assert failure["phase"] == "fresh"
    assert failure["unobserved"] == ["fullscreen", "work_area", "layers"]
    rejected_sizes = {w["id"]: w for w in failure["sample"]}
    assert set(rejected_sizes) == {70, 71, 80, 12000}
    assert rejected_sizes[70] == {
        "id": 70,
        "protected": True,
        "tile_size": [640.0, 1292.0],
        "window_size": [628.0, 1280.0],
    }
    assert rejected_sizes[12000]["protected"] is False
    assert failure["changes"] == [
        {
            "id": wid,
            "field": field,
            "before": pair,
            "rejected": [pair[0], pair[1] + 92],
            "delta": [0.0, 92.0],
        }
        for wid, width in ((70, 640.0), (71, 640.0), (80, 720.0))
        for field, pair in (("tile_size", [width, 1200.0]), ("window_size", [width - 12, 1188.0]))
    ]
    clock = 0
    for query in ("windows", "workspaces", "outputs"):
        start, end = failure["queries_ns"][query]
        assert clock <= start <= end <= failure["refusal_check_ns"]
        clock = end
    receipt = s.store.get("receipts", result["receipt_digest"])
    assert receipt["first_rejected_observation"] == failure
    assert not any(a[0] == "set-column-width" for a in s.desktop.actions)

    before = {w["id"]: w for w in baseline}
    stable = {w["id"]: w for w in accepted_focus[0]["windows"]}
    rejected = {w["id"]: w for w in reads[0]}
    diagnostic = {w["id"]: w for w in result["final_observation"]["windows"]}
    for wid in (70, 71, 80):
        for field in ("tile_size", "window_size"):
            assert stable[wid]["layout"][field] == before[wid]["layout"][field]
            assert rejected[wid]["layout"][field][1] == before[wid]["layout"][field][1] + 92
            assert (
                diagnostic[wid]["layout"][field][1]
                == before[wid]["layout"][field][1] + fallback_delta
            )
            assert diagnostic[wid]["layout"][field][0] == before[wid]["layout"][field][0]

    records = [
        json.loads(p.read_text()) for p in sorted(history.fence_path(s.identity).glob("*.json"))
    ]
    assert len(records) == 10
    assert [v["type"] for v in records] == [
        "prepared",
        "intent",
        "observed",
        "intent",
        "observed",
        "association",
        "intent",
        "observed",
        "intent",
        "observed",
    ]
    # These last two writes precede the rejected sample. There is no column intent.
    assert records[-1]["type"] == "observed"
    assert not any(v["type"] in {"terminal", "final-observed"} for v in records)
    assert not list(history.fence_path(s.identity).glob("*.pending"))
    assert s.desktop.columns == {1: [[70], [12000], [71]], 2: [[80]], 508: []}
    assert s.desktop.focus == 12000  # No automatic restoration of focus after refusal.
    recovered = {w["id"]: w for w in s.desktop.windows()}
    assert all(
        recovered[i]["layout"]["tile_size"] == before[i]["layout"]["tile_size"] for i in before
    )
    assert result["status"] == "interrupted"  # Recovery cannot upgrade original outcome.


def test_given_stable_dimensions_when_same_restore_runs_then_completion_is_possible(integrated):
    s = integrated
    entry = setup(s)
    key, result = s.run([entry])
    assert result["status"] == "reopened"
    assert "first_rejected_observation" not in result
    assert s.desktop.actions == [
        MOVE,
        FOCUS,
        ("move-column-to-index", "3"),
        ("focus-window", "--id", "80"),
    ]
    assert s.desktop.columns == {1: [[70], [71], [12000]], 2: [[80]], 508: []}
    assert s.desktop.focus == 80
    assert s.store.pointer("last-reopened") == key
    assert result["windows"][0]["geometry_coverage"]["width"] == "requested-observed"
    assert not any(a[0] == "set-column-width" for a in s.desktop.actions)


def test_given_timed_queries_when_size_refuses_then_exact_intervals_not_fallback(monkeypatch):
    from test_restore_observation_coherence import sample
    from test_restore_observation_coherence import setup as scheduled

    from niri_desktop_continuity import restore_failure_observation as diagnostic

    bad = sample()
    bad["windows"][0]["layout"]["tile_size"][1] += 92
    layout, desktop, _, _, _, _ = scheduled(monkeypatch, [bad, sample()])
    ticks = iter([100, 110, 120, 130, 140, 150, 160, 200, 210, 220, 230, 240, 250])
    monkeypatch.setattr(diagnostic.time, "monotonic_ns", lambda: next(ticks))
    with pytest.raises(ValueError, match="^protected dimensions changed$"):
        layout.fresh()
    first = layout.failure_observation.export()
    assert first["queries_ns"] == {
        "windows": [100, 110],
        "workspaces": [120, 130],
        "outputs": [140, 150],
    }
    assert first["refusal_check_ns"] == 160
    layout.read()  # existing fallback; later timing must never be substituted
    assert desktop.count == 3
    assert layout.failure_observation.export() == first
    first["sample"][0]["tile_size"][1] = 999
    assert layout.failure_observation.export()["sample"][0]["tile_size"][1] == 692


@pytest.mark.parametrize("phase", ["association", "postcondition", "proofs"])
def test_given_phase_when_proof_rejects_then_label_exact_checked_state(monkeypatch, phase):
    from test_restore_observation_coherence import sample
    from test_restore_observation_coherence import setup as scheduled

    bad = sample(mapped=phase == "association")
    bad["windows"][0]["layout"]["window_size"][1] += 92
    layout, desktop, proof, records, _, _ = scheduled(monkeypatch, [bad])
    with pytest.raises(ValueError, match="^protected dimensions changed$"):
        if phase == "association":
            layout.associate(proof, 0)
        elif phase == "postcondition":
            # Dispatch/intent mechanics have independent integration coverage; this test
            # supplies stable prechecks and an explicit expected state, not a real action.
            monkeypatch.setattr(layout, "fresh", lambda: layout.state)
            layout.attempt.intent = lambda *args: records.append(args)
            desktop.action = lambda *args: records.append(args)
            layout.effect(("focus-window", "--id", "10"))
        else:
            layout.proofs(layout.read())
    evidence = layout.failure_observation.export()
    assert evidence["phase"] == phase
    assert all(evidence["queries_ns"].values())
    assert evidence["sample"][0]["window_size"] == [788, 680]
    if phase == "association":
        assert records == [] and layout.owned == {}
    if phase == "postcondition":
        assert len(records) == 2 and layout.effects == []  # dispatched but not observed


def test_given_reused_baseline_when_proofs_refuse_then_query_times_unavailable(monkeypatch):
    from test_restore_observation_coherence import sample
    from test_restore_observation_coherence import setup as scheduled

    layout, desktop, proof, records, _, _ = scheduled(monkeypatch, [sample(True)])
    # Reused earlier state, not a sample from the pending query: no invented timing.
    layout.state[0][10]["layout"]["tile_size"][1] += 92
    with pytest.raises(ValueError, match="^protected dimensions changed$"):
        layout.associate(proof, 0)
    evidence = layout.failure_observation.export()
    assert evidence["phase"] == "association-baseline"
    assert evidence["queries_ns"] == {"windows": None, "workspaces": None, "outputs": None}
    assert desktop.count == 1 and records == []


def test_given_invalid_split_when_classifier_refuses_then_no_dimension_diagnostic(monkeypatch):
    from test_restore_observation_coherence import sample, split
    from test_restore_observation_coherence import setup as scheduled

    bad = split()
    bad["windows"][0]["layout"]["tile_size"][1] += 92
    layout, desktop, proof, records, _, _ = scheduled(monkeypatch, [bad, sample(True)])
    with pytest.raises(ValueError, match="split observation changed windows or outputs"):
        layout.associate(proof, 0)
    assert layout.failure_observation.export() is None  # classification precedes size guard
    assert desktop.count == 2 and records == []


@pytest.mark.parametrize("fault", [ValueError, MemoryError, KeyboardInterrupt, SystemExit])
def test_given_diagnostic_fault_when_size_refuses_then_original_error_survives(
    integrated, monkeypatch, fault
):
    from niri_desktop_continuity import restore_failure_observation as diagnostic

    s = integrated
    entry = setup(s)
    original = s.desktop.windows

    def sample(*, deadline=None):
        value = original(deadline=deadline)
        if s.proofs:
            value[0]["layout"]["tile_size"][1] += 92
        return value

    def fail(*args):
        raise fault("FABRICATED-PRIVATE-DIAGNOSTIC-FAULT")

    monkeypatch.setattr(s.desktop, "windows", sample)
    monkeypatch.setattr(diagnostic, "project", fail)
    _, result = s.run([entry])
    assert result["error_type"] == "ValueError"
    assert result["error"] == "protected dimensions changed"
    assert result["first_rejected_observation"] == {
        "schema": "restore-protected-dimensions.v1",
        "unavailable": True,
    }
    assert result["status"] == "interrupted" and not s.desktop.actions
    assert len(s.proofs) == 1 and s.proofs[0].invalid
    assert "PRIVATE" not in json.dumps(result)
    assert s.store.pointer("last-reopened") is None
    with pytest.raises(ValueError, match="unresolved"):
        history.require_clear(s.identity)


def diagnostic_fixture():
    # Handwritten closed wire oracle independent of the producer.
    return {
        "schema": "restore-protected-dimensions.v1",
        "phase": "fresh",
        "refusal_check_ns": 70,
        "queries_ns": {"windows": [10, 20], "workspaces": [30, 40], "outputs": [50, 60]},
        "sample": [{"id": 7, "protected": True, "tile_size": [800, 692], "window_size": None}],
        "changes": [
            {
                "id": 7,
                "field": "tile_size",
                "before": [800, 600],
                "rejected": [800, 692],
                "delta": [0, 92],
            }
        ],
        "unobserved": ["fullscreen", "work_area", "layers"],
    }


def test_given_handwritten_wire_when_decoded_then_closed_bounded_evidence_only():
    from niri_desktop_continuity.restore_failure_observation import validate

    value = diagnostic_fixture()
    validate(value)
    validate({"schema": "restore-protected-dimensions.v1", "unavailable": True})
    with pytest.raises(ValueError, match="unknown terminal receipt fields"):
        history.terminal_valid({"first_rejected_observation": value}, {"entries": []})


@pytest.mark.parametrize(
    "damage",
    [
        "extra",
        "schema",
        "phase",
        "unobserved",
        "clock-bool",
        "clock-huge",
        "backward",
        "after-check",
        "query-extra",
        "raw-title",
        "id-bool",
        "id-huge",
        "duplicate-window",
        "too-many-windows",
        "too-many-changes",
        "empty-changes",
        "owned-change",
        "unknown-field",
        "unbound",
        "mismatched-size",
        "wrong-delta",
        "duplicate-change",
        "nonfinite",
        "large-size",
        "alias-size",
        "unavailable-extra",
    ],
)
def test_given_tampered_diagnostic_when_decoded_then_refuse(damage):
    from niri_desktop_continuity.restore_failure_observation import validate

    value = diagnostic_fixture()
    row, change = value["sample"][0], value["changes"][0]
    if damage == "extra":
        value["title"] = "FABRICATED-PRIVATE"
    elif damage == "schema":
        value["schema"] = "unknown"
    elif damage == "phase":
        value["phase"] = "receipt-write"
    elif damage == "unobserved":
        value["unobserved"] = []
    elif damage == "clock-bool":
        value["refusal_check_ns"] = True
    elif damage == "clock-huge":
        value["refusal_check_ns"] = 2**63
    elif damage == "backward":
        value["queries_ns"]["workspaces"] = [19, 40]
    elif damage == "after-check":
        value["queries_ns"]["outputs"] = [50, 80]
    elif damage == "query-extra":
        value["queries_ns"]["layers"] = [60, 65]
    elif damage == "raw-title":
        row["title"] = "FABRICATED-PRIVATE"
    elif damage == "id-bool":
        row["id"] = True
    elif damage == "id-huge":
        row["id"] = 2**63
    elif damage == "duplicate-window":
        value["sample"].append(deepcopy(row))
    elif damage == "too-many-windows":
        value["sample"] *= 513
    elif damage == "too-many-changes":
        value["changes"] *= 1025
    elif damage == "empty-changes":
        value["changes"] = []
    elif damage == "owned-change":
        row["protected"] = False
    elif damage == "unknown-field":
        change["field"] = "fullscreen"
    elif damage == "unbound":
        change["id"] = 8
    elif damage == "mismatched-size":
        change["rejected"][1] = 784
    elif damage == "wrong-delta":
        change["delta"][1] = 184
    elif damage == "duplicate-change":
        value["changes"].append(deepcopy(change))
    elif damage == "nonfinite":
        row["tile_size"][1] = float("inf")
    elif damage == "large-size":
        row["tile_size"][1] = 1e10
    elif damage == "alias-size":
        row["tile_size"][1] = True
    else:
        value["unavailable"] = True
    with pytest.raises(ValueError):
        validate(value)


@pytest.mark.parametrize("bad", [1e10, float("nan"), float("inf"), 10**400, True])
def test_given_unrepresentable_size_when_retaining_then_unavailable_not_unbounded(bad):
    from niri_desktop_continuity.restore_failure_observation import FailureObservation

    evidence = FailureObservation()
    protected = {7: {"layout": {"tile_size": [800, 600]}}}
    state = ({7: {"layout": {"tile_size": [800, bad]}}}, [])
    evidence.reject(state, protected, "proofs")
    assert evidence.export() == {"schema": "restore-protected-dimensions.v1", "unavailable": True}
    state[0][7]["layout"]["tile_size"][1] = 692
    evidence.reject(state, protected, "fresh")
    assert evidence.export()["unavailable"] is True  # cannot overwrite failed first retention


def test_given_private_payload_when_retaining_then_only_dimensions_are_copied():
    from niri_desktop_continuity.restore_failure_observation import FailureObservation

    evidence = FailureObservation()
    private = "FABRICATED-PRIVATE-TITLE-ARGV-ENV-PATH"
    protected = {7: {"layout": {"tile_size": [800, 600]}}}
    window = {
        "layout": {"tile_size": [800, 692], "raw": private},
        "title": private,
        "argv": [private],
        "env": {"x": private},
        "cwd": private,
    }
    state = ({7: window}, [{"name": private}], [{"name": private}])
    evidence.reject(state, protected, "proofs")
    original = evidence.export()
    assert private not in json.dumps(original)
    assert original["sample"] == [
        {"id": 7, "protected": True, "tile_size": [800, 692], "window_size": None}
    ]
    assert original["queries_ns"] == dict.fromkeys(("windows", "workspaces", "outputs"))
    window["layout"]["tile_size"][1] = 999
    protected[7]["layout"]["tile_size"][1] = 999
    evidence.reject(state, protected, "fresh")
    assert evidence.export() == original


def test_given_already_refused_when_clock_fails_then_refusal_evidence_remains(monkeypatch):
    from niri_desktop_continuity import restore_failure_observation as diagnostic

    def fail():
        raise KeyboardInterrupt("fabricated clock failure")

    monkeypatch.setattr(diagnostic.time, "monotonic_ns", fail)
    evidence = diagnostic.FailureObservation()
    state = ({7: {"layout": {"tile_size": [800, 692]}}}, [])
    evidence.bind(state)
    evidence.reject(state, {7: {"layout": {"tile_size": [800, 600]}}}, "proofs")
    assert evidence.export()["refusal_check_ns"] is None
    assert evidence.export()["queries_ns"] == dict.fromkeys(("windows", "workspaces", "outputs"))


@pytest.mark.parametrize("count", [512, 513])
def test_given_sample_bound_when_retaining_then_complete_or_explicitly_unavailable(count):
    from niri_desktop_continuity.restore_failure_observation import FailureObservation

    protected = {
        i: {"layout": {"tile_size": [800, 600], "window_size": [788, 588]}} for i in range(count)
    }
    windows = {
        i: {"layout": {"tile_size": [800, 692], "window_size": [788, 680]}} for i in range(count)
    }
    evidence = FailureObservation()
    evidence.reject((windows, []), protected, "proofs")
    result = evidence.export()
    if count == 512:
        assert len(result["sample"]) == 512 and len(result["changes"]) == 1024
        assert len(json.dumps(result)) < 512 * 1024
    else:
        assert result == {"schema": "restore-protected-dimensions.v1", "unavailable": True}


def test_given_missing_size_when_refused_then_no_invented_delta():
    from niri_desktop_continuity.restore_failure_observation import FailureObservation

    evidence = FailureObservation()
    evidence.reject(
        ({7: {"layout": {"tile_size": None}}}, []),
        {7: {"layout": {"tile_size": [800, 600]}}},
        "proofs",
    )
    assert evidence.export()["changes"] == [
        {"id": 7, "field": "tile_size", "before": [800, 600], "rejected": None, "delta": None}
    ]


def test_given_refusal_when_fallback_fails_then_first_evidence_and_teardown_remain(
    integrated, monkeypatch
):
    s = integrated
    entry = setup(s)
    original = s.desktop.windows
    reads = []

    def windows(*, deadline=None):
        value = original(deadline=deadline)
        if s.proofs:
            reads.append(True)
            if len(reads) == 2:
                raise OSError("fabricated unavailable fallback")
            value[0]["layout"]["tile_size"][1] += 92
        return value

    monkeypatch.setattr(s.desktop, "windows", windows)
    _, result = s.run([entry])
    assert len(reads) == 2 and result["final_observation"] == {"unavailable": True}
    assert result["error"] == "protected dimensions changed"
    assert result["first_rejected_observation"]["sample"][0]["tile_size"] == [640, 1292]
    assert result["first_rejected_observation"]["phase"] == "association"
    assert result["effects"] == [] and s.proofs[0].invalid
    assert result["status"] == "interrupted" and s.store.pointer("last-reopened") is None
