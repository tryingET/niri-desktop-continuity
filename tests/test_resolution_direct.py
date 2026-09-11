"""Finite direct-first-launch new-boot oracle; same-boot absence never settles descendants."""

from datetime import datetime, timedelta, timezone

import pytest
from test_recovery_backend import private_json
from test_resolution_fixtures import BOOT, NEW_BOOT, candidate, packet, worker_record
from test_resolution_fixtures import resolution as resolution_fixture  # noqa: F401

from niri_desktop_continuity import (
    recovery_transition,
    resolution_candidate,
    resolution_evidence,
    resolution_graph,
)
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_verification import receipt
from niri_desktop_continuity.resolution_io import Objects, raw, retained, sha


def direct_history(data):
    """Construct a fabricated historical direct ACK, without invoking any executor."""
    worker, attempt, ledger = data["worker"], data["attempt"], data["ledger"]
    intent_ref, measured = "1" * 64, "2" * 64
    worker_record(
        worker,
        "intent",
        attempt,
        {"intent_ref": intent_ref, "target_ref": "b" * 64},
        directory="events",
    )
    result = worker_record(
        worker,
        "result",
        attempt,
        {"intent_ref": intent_ref, "measurement_ref": measured, "pid": 40},
    )
    child = worker_record(
        worker,
        "child",
        attempt,
        {"boot_id": BOOT, "pid": 40, "start_ticks": 42, "measurement_ref": measured},
        directory="children",
    )
    worker_record(
        worker,
        "ack",
        attempt,
        {"intent_ref": intent_ref, "result_ref": result, "child_ref": child},
        directory="events",
    )
    expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    request = worker_record(
        worker,
        "request",
        attempt,
        {
            "child_ref": child,
            "session_ref": "b" * 64,
            "file_sha256": "d" * 64,
            "expires_at": expires,
            "argv_digest": "3" * 64,
        },
        directory="requests",
    )
    request_sha = sha(raw(worker / "requests" / f"{request}.json"))
    claim = worker_record(
        worker,
        "started",
        attempt,
        {
            "request_ref": request,
            "request_sha256": request_sha,
            "boot_id": BOOT,
            "pid": 41,
            "start_ticks": 43,
            "ppid": 40,
            "argv_digest": "3" * 64,
        },
        directory="started",
    )
    ledger.event(
        attempt,
        "intent",
        {"sequence": 0, "kind": "launch", "intent_ref": intent_ref, "target_ref": "b" * 64},
    )
    event = {"sequence": 0, "intent_ref": intent_ref, "outcome": "observed", "evidence_ref": result}
    ledger.event(attempt, "result", event)
    terminal = ledger.store.recovery_marker("recovery-terminal", attempt)
    ledger.store.path("receipts", terminal["receipt_digest"]).unlink()  # Fixture construction only.
    terminal["receipt_digest"] = ledger.store.put(
        "receipts",
        receipt(data["original_plan"], attempt, None, history_complete=False, events=[event]),
    )
    private_json(ledger.store.path("recovery-terminal", attempt), terminal)
    source = data["source"]
    review_path = data["root"] / "review.json"
    import json

    review = json.loads(review_path.read_text())
    review["prefix_rule"] = source["prefix_rule"] = "direct-first-ack-v1"
    private_json(review_path, review)
    source["review_artifact"] = retained(review_path)
    private_json(data["root"] / "source.json", source)
    return {
        "request_ref": request,
        "request_sha256": request_sha,
        "claim_ref": claim,
        "claim_sha256": sha(raw(worker / "started" / f"{claim}.json")),
        "boot_id": BOOT,
        "pid": 41,
        "start_ticks": 43,
        "expires_at": expires,
        "disposition": "old-boot",
    }


def direct_packet(value, graph_key, ticket, boot):
    result = packet(value, graph_key, boot=boot)
    evidence = result["evidence"]
    same = boot == BOOT
    evidence["tickets"] = [{**ticket, "disposition": "absent" if same else "old-boot"}]
    evidence["mode"] = "historical-same-boot-unproved" if same else "new-boot-direct"
    evidence["process_scan"]["escaped_cohort"] = "unproved" if same else "excluded-by-boot"
    evidence["verdict"] = "blocked" if same else "settled"
    evidence["blockers"] = ["historical-same-boot-unproved"] if same else []
    return result


@pytest.mark.parametrize("boot", [BOOT, NEW_BOOT])
def test_direct_ack_boot_predicate_and_actual_transaction(resolution, monkeypatch, boot):
    ticket = direct_history(resolution)
    key, value = candidate(resolution)
    resolution_candidate.approve(key, key, "resolution-observe-only")
    graph = resolution_graph.initial(value)
    evidence = direct_packet(value, digest(graph), ticket, boot)
    objects = Objects(value["ledger"]["path"])
    evidence_key = resolution_evidence.persist_packet(evidence, value, graph, objects)
    assert objects.get(evidence_key)["verdict"] == ("blocked" if boot == BOOT else "settled")
    monkeypatch.setattr(
        recovery_transition, "observe", lambda c, g: direct_packet(value, g, ticket, boot)
    )
    planned = recovery_transition.plan(key, resolution["attempt"])
    if boot == BOOT:
        assert planned["admission"] == {
            "status": "blocked",
            "blockers": ["historical-same-boot-unproved"],
        }
        with pytest.raises(ValueError):
            recovery_transition.approve(
                planned["plan_digest"], planned["plan_digest"], "abandon-without-retry-or-success"
            )
    else:
        assert planned["admission"] == {"status": "awaiting-approval", "blockers": []}
        key = recovery_transition.approve(
            planned["plan_digest"], planned["plan_digest"], "abandon-without-retry-or-success"
        )["approval_digest"]
        assert recovery_transition.apply(key)["resolution_disposition"] == "abandoned-settled"


@pytest.mark.parametrize(
    "damage", ["ack", "claim", "request", "sequence", "ticket-expiry", "ticket-birth"]
)
def test_direct_history_counterexamples(resolution, damage):
    ticket = direct_history(resolution)
    if damage in ("ack", "claim", "request"):
        directory = {"ack": "events", "claim": "started", "request": "requests"}[damage]
        paths = list((resolution["worker"] / directory).iterdir())
        if damage == "ack":
            import json

            paths = [p for p in paths if json.loads(p.read_text())["kind"] == "ack"]
        paths[0].unlink()
        with pytest.raises(ValueError):
            candidate(resolution)
        return
    if damage == "sequence":
        resolution["ledger"].event(
            resolution["attempt"],
            "intent",
            {"sequence": 1, "kind": "launch", "intent_ref": "4" * 64, "target_ref": "c" * 64},
        )
        with pytest.raises(ValueError):
            candidate(resolution)
        return
    _, value = candidate(resolution)
    graph = resolution_graph.initial(value)
    evidence = direct_packet(value, digest(graph), ticket, NEW_BOOT)
    evidence["evidence"]["tickets"][0]["expires_at" if damage == "ticket-expiry" else "pid"] = (
        (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        if damage == "ticket-expiry"
        else 90
    )
    with pytest.raises(ValueError):
        resolution_evidence.persist_packet(evidence, value, graph, Objects(value["ledger"]["path"]))
