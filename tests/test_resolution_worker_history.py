"""Handwritten owner-shape graph and settlement oracles (fabricated private roots)."""

import json
from copy import deepcopy

import pytest
from test_recovery_backend import private_json
from test_resolution_direct import direct_packet
from test_resolution_fixtures import BOOT, NEW_BOOT, candidate
from test_resolution_fixtures import resolution as resolution_fixture  # noqa: F401
from test_resolution_history_fixtures import canonical, put
from test_resolution_history_fixtures import real_history as real_history_fixture  # noqa: F401

from niri_desktop_continuity import resolution_evidence, resolution_graph
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_verification import receipt
from niri_desktop_continuity.resolution_io import Objects, retained, sha


def evidence(data, value, graph, boot):
    ticket = {
        "request_ref": digest(data["request"]),
        "request_sha256": sha(data["request_path"].read_bytes()),
        "claim_ref": digest(data["claim"]),
        "claim_sha256": sha(data["claim_path"].read_bytes()),
        "boot_id": BOOT,
        "pid": 41,
        "start_ticks": 43,
        "expires_at": data["original_plan"]["expires_at"],
        "disposition": "old-boot",
    }
    packet = direct_packet(value, digest(graph), ticket, boot)
    packet["evidence"]["saved_files"] = [
        {
            "session_ref": ref,
            "device": 1,
            "inode": row["metadata"]["inode"],
            "bytes": 30,
            "sha256": "a" * 64,
            "original_prefix_bytes": 20,
            "original_prefix_sha256": "d" * 64,
            "metadata_ref": digest(row["metadata"]),
            "prefix_preserved": True,
        }
        for ref, row in sorted(data["manifest"]["items"].items())
    ]
    return packet


def test_original_graph_handwritten_golden(real_history):
    data = real_history
    _, value = candidate(data)
    graph = resolution_graph.initial(value)
    history = resolution_graph.worker_history(value)
    assert set(history) == {"manifest", "saved_files", "tickets", "old_boot"}
    assert history["manifest"] == data["manifest"]
    assert history["old_boot"] == BOOT
    assert history["tickets"] == [
        {
            k: v
            for k, v in evidence(data, value, graph, NEW_BOOT)["evidence"]["tickets"][0].items()
            if k != "disposition"
        }
    ]
    assert history["saved_files"] == [
        {
            "session_ref": ref,
            "device": 1,
            "inode": row["metadata"]["inode"],
            "prefix_bytes": 20,
            "prefix_sha256": "d" * 64,
            "metadata_ref": digest(row["metadata"]),
        }
        for ref, row in sorted(data["manifest"]["items"].items())
    ]
    dispatch_key = digest({"attempt": data["attempt"], "session_ref": data["refs"][0]})
    expected = {
        "catalog.json",
        f"attempts/{data['attempt']}.json",
        f"events/{digest({'attempt': data['attempt'], 'sequence': 0})}.json",
        f"children/{dispatch_key}.json",
        f"bootstraps/{dispatch_key}.json",
        f"bootstraps/{dispatch_key}.started.json",
    }
    expected |= {
        f"objects/{digest(data[k])}.json"
        for k in ("manifest", "intent", "measurement", "outcome", "ack")
    }
    actual = {f["relative_path"] for f in graph["files"] if f["root"] == "worker"}
    assert actual == expected
    assert len(actual) == 11
    # Filenames are dispatch-keyed, not request/claim semantic digests.
    assert dispatch_key not in (digest(data["request"]), digest(data["claim"]))
    for f in graph["files"]:
        if f["root"] == "worker":
            raw = (data["worker"] / f["relative_path"]).read_bytes()
            assert f["object_digest"] == digest(json.loads(raw))
            assert f["raw_sha256"] == sha(raw)
    assert len(graph["absences"]) == 511
    assert {"root": "worker", "relative_path": f"finished/{data['attempt']}.json"} in graph[
        "absences"
    ]


@pytest.mark.parametrize("boot", [BOOT, NEW_BOOT])
def test_actual_ticket_same_boot_blocks_new_boot_eligible(real_history, boot):
    _, value = candidate(real_history)
    graph = resolution_graph.initial(value)
    packet = evidence(real_history, value, graph, boot)
    objects = Objects(value["ledger"]["path"])
    key = resolution_evidence.persist_packet(packet, value, graph, objects)
    assert objects.get(key)["verdict"] == ("blocked" if boot == BOOT else "settled")


@pytest.mark.parametrize(
    "damage",
    [
        "ack",
        "claim",
        "request",
        "manifest",
        "catalog",
        "metadata",
        "dispatch",
        "orphan-event",
        "orphan-object",
        "unknown-catalog",
        "corrupt",
        "source-pin",
        "argv",
        "request-sha",
        "unknown-object",
        "extra-request",
        "extra-intent",
        "orphan-canonical-receipt",
        "orphan-canonical-marker",
    ],
)
def test_actual_history_fails_closed(real_history, damage):
    data, worker = real_history, real_history["worker"]
    if damage in ("ack", "manifest"):
        (worker / "objects" / f"{digest(data[damage])}.json").unlink()
    elif damage in ("request", "claim"):
        data[f"{damage}_path"].unlink()
    elif damage == "catalog":
        (worker / "catalog.json").unlink()
    elif damage == "metadata":
        value = deepcopy(data["manifest"])
        value["items"][data["refs"][0]]["metadata"]["header"]["cwd"] += "-different"
        put(worker, value)
    elif damage == "dispatch":
        value = {"attempt": data["attempt"], "session_ref": data["refs"][1], "target": {}}
        put(worker, value)
    elif damage == "orphan-event":
        private_json(worker / "events" / f"{'e' * 64}.json", {"intent_ref": digest(data["intent"])})
    elif damage == "orphan-object":
        put(worker, {**data["ack"], "attempt": "f" * 64})
    elif damage == "unknown-catalog":
        v = json.loads((worker / "catalog.json").read_bytes())
        v["directories"].append("pending")
        private_json(worker / "catalog.json", v)
    elif damage == "corrupt":
        data["request_path"].write_bytes(b'{"attempt": 1, "attempt": 2}')
    elif damage == "unknown-object":
        put(worker, {"invented": True})
    elif damage.startswith("orphan-canonical"):
        foreign = "f" * 64
        body = {
            "sequence": 0,
            "kind": "launch",
            "intent_ref": "e" * 64,
            "target_ref": data["refs"][0],
        }
        if damage == "orphan-canonical-marker":
            data["ledger"].event(foreign, "intent", body)
        else:
            data["ledger"].store.put(
                "receipts",
                {
                    "schema": data["old"]["schema"],
                    "attempt_digest": foreign,
                    "event": "intent",
                    "value": body,
                },
            )
    elif damage == "extra-request":
        request = deepcopy(data["request"])
        ref = data["refs"][1]
        request.update(session_ref=ref, **data["manifest"]["items"][ref]["selection"])
        key = digest({"attempt": data["attempt"], "session_ref": ref})
        private_json(worker / "bootstraps" / f"{key}.json", request)
    elif damage == "extra-intent":
        v = {**data["intent"], "sequence": 1, "target_ref": data["refs"][1]}
        key = put(worker, v)
        private_json(
            worker / "events" / f"{digest({'attempt': data['attempt'], 'sequence': 1})}.json",
            {"intent_ref": key},
        )
    else:
        request, claim = deepcopy(data["request"]), deepcopy(data["claim"])
        if damage == "source-pin":
            request["node"]["sha256"] = "f" * 64
            private_json(data["request_path"], request)
            claim["request_sha256"] = sha(data["request_path"].read_bytes())
        elif damage == "argv":
            claim["argv"].append("--unsupported")
        else:
            claim["request_sha256"] = "f" * 64
        private_json(data["claim_path"], claim)
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        candidate(data)


@pytest.mark.parametrize(
    "damage", ["request-ref", "claim-ref", "raw-sha", "metadata-ref", "ticket-missing"]
)
def test_evidence_binds_original_semantic_and_raw_identity(real_history, damage):
    _, value = candidate(real_history)
    graph = resolution_graph.initial(value)
    packet = evidence(real_history, value, graph, NEW_BOOT)
    ev = packet["evidence"]
    if damage == "metadata-ref":
        ev["saved_files"][0]["metadata_ref"] = "e" * 64
    elif damage == "ticket-missing":
        ev["tickets"] = []
    else:
        key = {"request-ref": "request_ref", "claim-ref": "claim_ref", "raw-sha": "request_sha256"}[
            damage
        ]
        ev["tickets"][0][key] = "e" * 64
    with pytest.raises(ValueError):
        resolution_evidence.persist_packet(packet, value, graph, Objects(value["ledger"]["path"]))


def test_unrelated_manifests_and_later_attempt_do_not_expand_original_graph(real_history):
    data = real_history
    _, value = candidate(data)
    graph = resolution_graph.initial(value)
    manifest = deepcopy(data["manifest"])
    manifest["protected"]["windows"] = []  # A later observation, sharing saved refs and hashes.
    key = put(data["worker"], manifest)
    assert key != digest(data["manifest"])
    assert resolution_graph.initial(value) == graph
    later = deepcopy(data["original_plan"])
    later["recovery"]["profile_digest"] = digest(data["new"])
    later["recovery"]["observation"]["private_ref"] = key
    _, attempt = canonical(data, later, data["new"])
    private_json(data["worker"] / "attempts" / f"{attempt}.json", {"request_digest": "e" * 64})
    resolution_graph.unchanged(value, graph, durable=True)
    with pytest.raises(ValueError):
        resolution_graph.unchanged(value, graph)
    # Durable history still depends on every original record, not just current profile.
    data["claim_path"].unlink()
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        resolution_graph.unchanged(value, graph, durable=True)


def test_raw_reserialization_cannot_replace_original_graph(real_history):
    _, value = candidate(real_history)
    graph = resolution_graph.initial(value)
    private_json(real_history["claim_path"], real_history["claim"])
    assert resolution_graph.worker_history(value)["tickets"][0]["claim_ref"] == digest(
        real_history["claim"]
    )
    with pytest.raises(ValueError):
        resolution_graph.unchanged(value, graph)


@pytest.mark.parametrize(
    "kind",
    [
        "manifest",
        "intent",
        "measurement",
        "outcome",
        "ack",
        "request",
        "claim",
        "child",
        "attempt",
        "event",
        "catalog",
    ],
)
def test_each_original_worker_record_is_durable_dependency(real_history, kind):
    data = real_history
    _, value = candidate(data)
    graph = resolution_graph.initial(value)
    worker = data["worker"]
    if kind in ("manifest", "intent", "measurement", "outcome", "ack"):
        path = worker / "objects" / f"{digest(data[kind])}.json"
    elif kind in ("request", "claim"):
        path = data[f"{kind}_path"]
    elif kind == "catalog":
        path = worker / "catalog.json"
    elif kind == "attempt":
        path = worker / "attempts" / f"{data['attempt']}.json"
    else:
        path = next((worker / {"child": "children", "event": "events"}[kind]).iterdir())
    path.unlink()
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        resolution_graph.unchanged(value, graph, durable=True)


def test_actual_zero_permit_has_no_ticket_or_absence_only_launch_settlement(real_history):
    data = real_history
    worker, ledger, attempt = data["worker"], data["ledger"], data["attempt"]
    # Fabricate a different zero-permit history; never convert real persisted attempts.
    for kind in ("intent", "measurement", "outcome", "ack"):
        (worker / "objects" / f"{digest(data[kind])}.json").unlink()
    for kind in ("bootstraps", "children", "events"):
        for path in (worker / kind).iterdir():
            path.unlink()
    for path in (ledger.store.root / "recovery-events").iterdir():
        path.unlink()
    for path in (ledger.store.root / "receipts").iterdir():
        path.unlink()
    terminal = ledger.store.recovery_marker("recovery-terminal", attempt)
    terminal["receipt_digest"] = ledger.store.put(
        "receipts", receipt(data["original_plan"], attempt, None, history_complete=False, events=[])
    )
    private_json(ledger.store.path("recovery-terminal", attempt), terminal)
    review_path = data["root"] / "review.json"
    review = json.loads(review_path.read_bytes())
    review["prefix_rule"] = data["source"]["prefix_rule"] = "zero-permit-v1"
    private_json(review_path, review)
    data["source"]["review_artifact"] = retained(review_path)
    private_json(data["root"] / "source.json", data["source"])
    _, value = candidate(data)
    graph = resolution_graph.initial(value)
    assert resolution_graph.worker_history(value)["tickets"] == []
    assert len([f for f in graph["files"] if f["root"] == "worker"]) == 3
    from test_resolution_fixtures import packet as zero_packet

    packet = zero_packet(value, digest(graph))
    packet["evidence"]["saved_files"] = [
        {
            "session_ref": ref,
            "device": 1,
            "inode": row["metadata"]["inode"],
            "bytes": 30,
            "sha256": "a" * 64,
            "original_prefix_bytes": 20,
            "original_prefix_sha256": "d" * 64,
            "metadata_ref": digest(row["metadata"]),
            "prefix_preserved": True,
        }
        for ref, row in sorted(data["manifest"]["items"].items())
    ]
    ev = packet["evidence"]
    ev.update(tickets=[], mode="same-boot-zero-permit", verdict="settled", blockers=[])
    ev["process_scan"]["escaped_cohort"] = "not-created"
    objects = Objects(value["ledger"]["path"])
    resolution_evidence.persist_packet(packet, value, graph, objects)
    ev["process_scan"]["escaped_cohort"] = "unproved"
    ev.update(verdict="blocked", blockers=["capability-unknown"])
    key = resolution_evidence.persist_packet(packet, value, graph, objects)
    assert objects.get(key)["verdict"] == "blocked"


def test_packet_cannot_omit_original_manifest_from_graph(real_history):
    _, value = candidate(real_history)
    graph = resolution_graph.initial(value)
    graph["files"] = [
        f for f in graph["files"] if f["object_digest"] != digest(real_history["manifest"])
    ]
    packet = evidence(real_history, value, graph, NEW_BOOT)
    with pytest.raises(ValueError):
        resolution_evidence.persist_packet(packet, value, graph, Objects(value["ledger"]["path"]))
