"""Two actual-shape attempts: retained abandoned A0, then ordinary grouped completion.

Handwritten producer fixture. No owner imports, native processes, or real private data.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from test_recovery_backend import private_json
from test_resolution_fixtures import NEW_BOOT, candidate
from test_resolution_fixtures import resolution as resolution_fixture  # noqa: F401
from test_resolution_history_fixtures import canonical, put
from test_resolution_history_fixtures import real_history as real_history_fixture  # noqa: F401
from test_resolution_worker_history import evidence

from niri_desktop_continuity import (
    recovery,
    recovery_resolution,
    recovery_transition,
    resolution_candidate,
    resolution_graph,
)
from niri_desktop_continuity.model import digest, fingerprint, focus_pin
from niri_desktop_continuity.recovery_additive import DIMENSIONS
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.recovery_protocol import NATIVE
from niri_desktop_continuity.resolution_io import Objects, sha


def completion(data):
    worker = data["worker"]
    plan = deepcopy(data["original_plan"])
    snapshot = deepcopy(data["ledger"].store.get("snapshots", plan["snapshot_digest"]))
    snapshot["identity"]["boot_id"] = NEW_BOOT
    ledger = Ledger(data["new"])
    plan["snapshot_digest"] = ledger.store.put("snapshots", snapshot)
    plan["source_identity"] = snapshot["identity"]
    plan["state_fingerprint"] = fingerprint(snapshot)
    instant = datetime.now(timezone.utc)
    plan.update(
        created_at=instant.isoformat(), expires_at=(instant + timedelta(seconds=300)).isoformat()
    )
    plan["recovery"]["profile_digest"] = digest(data["new"])
    observed = plan["recovery"]["observation"]
    observed.update(
        identity_digest=digest(snapshot["identity"]),
        state_fingerprint=fingerprint(snapshot),
        focus_digest=digest(focus_pin(snapshot)),
    )
    manifest = deepcopy(data["manifest"])
    manifest.update(
        identity_digest=observed["identity_digest"],
        state_fingerprint=observed["state_fingerprint"],
        protected={k: snapshot[k] for k in ("identity", "windows", "processes")},
    )
    manifest_key = put(worker, manifest)
    observed["private_ref"] = manifest_key
    attempt = digest(recovery.approval_record(plan, digest(plan)))
    private_json(worker / "attempts" / f"{attempt}.json", {"request_digest": "d" * 64})
    host = {**data["child"]["host"], "pid": 80, "start_ticks": 800, "boot_id": NEW_BOOT}
    bindings, children, events, canon, objects = {}, {}, [], [], {}
    refs = data["refs"]
    for index, ref in enumerate(refs):
        item = manifest["items"][ref]["selection"]
        request = {
            **deepcopy(data["request"]),
            **item,
            "session_ref": ref,
            "attempt": attempt,
            "expires_at": plan["expires_at"],
        }
        key = digest({"attempt": attempt, "session_ref": ref})
        request_path = worker / "bootstraps" / f"{key}.json"
        private_json(request_path, request)
        claim = {
            **deepcopy(data["claim"]),
            "pid": 81 + index,
            "ppid": 80,
            "start_ticks": 801 + index,
            "boot_id": NEW_BOOT,
            "cwd": item["cwd"],
            "request": str(request_path),
            "request_sha256": sha(request_path.read_bytes()),
        }
        claim["argv"][-1] = item["file"]
        private_json(request_path.with_suffix(".started.json"), claim)
        process = {
            **host,
            "pid": claim["pid"],
            "ppid": 80,
            "start_ticks": claim["start_ticks"],
            "exe": request["node"]["path"],
            "exe_sha256": request["node"]["sha256"],
            "exe_inode": 600,
            "cwd": item["cwd"],
            "tty": 1024,
        }
        bound = {
            "process": process,
            "host": host,
            "window": {
                "id": 800,
                "pid": 80,
                "app_id": "com.mitchellh.ghostty",
                "workspace_id": 1,
                "is_floating": False,
            },
            "tty": [f"/dev/pts/{10 + index}", 1, 100 + index, 1024],
            "surface": hex(256 + index),
            "pi_bin": request["pi"]["path"],
            "bootstrap": {"kind": "retained-exec-ticket", "request": request, "claim": claim},
            "bus": {"name": ":1.42", "pid": 80, "daemon": "a" * 32},
        }
        child = {"attempt": attempt, "session_ref": ref, "pid": 80, "host": host}
        if index:
            dispatch = {
                "attempt": attempt,
                "session_ref": ref,
                "target": bindings[refs[0]]["binding"],
            }
            child["dispatch_ref"] = put(worker, dispatch)
            objects["dispatch"] = dispatch
        private_json(worker / "children" / f"{key}.json", child)
        row = {**item, "parents": [], "binding": bound, "process": process}
        bindings[ref] = row
        children[ref] = 80
        put(worker, {"attempt": attempt, "session_ref": ref, "native": row})
    for index, target in enumerate([*refs, manifest["focus_digest"]]):
        intent = {
            "attempt": attempt,
            "sequence": index,
            "kind": "launch" if index < 2 else "focus",
            "target_ref": target,
        }
        intent_ref = put(worker, intent)
        private_json(
            worker / "events" / f"{digest({'attempt': attempt, 'sequence': index})}.json",
            {"intent_ref": intent_ref},
        )
        measured = {
            "attempt": attempt,
            "intent_ref": intent_ref,
            "measurement": 80 if index < 2 else {"focused": manifest["focus"]["windows"][0]},
        }
        outcome = {
            "sequence": index,
            "intent_ref": intent_ref,
            "outcome": "observed",
            "evidence_ref": put(worker, measured),
        }
        result_ref = put(worker, outcome)
        ack = {"attempt": attempt, "sequence": index, "result_ref": result_ref}
        events.append({"intent": intent_ref, "result": result_ref, "ack": put(worker, ack)})
        canon.extend(
            [
                (
                    "intent",
                    {k: intent[k] for k in ("sequence", "kind", "target_ref")}
                    | {"intent_ref": intent_ref},
                ),
                ("result", outcome),
            ]
        )
    dimensions = {
        name: {"status": "proved", "evidence_ref": put(worker, {"dimension": name, "proved": True})}
        for name in DIMENSIONS
    }
    native = []
    for ref in refs:
        verification = {"reference": ref, "native": bindings[ref], "saved_prefix_preserved": True}
        objects[f"verification-{ref}"] = verification
        native.append(
            {
                "session_ref": ref,
                "evidence_ref": put(worker, verification),
                **{k: True for k in NATIVE},
            }
        )
    proof = {
        "dimensions": dimensions,
        "native": native,
        "interrupted": False,
        "unresolved_children": 0,
    }
    finished = {
        "complete": True,
        "proof_ref": put(worker, proof),
        "bindings": bindings,
        "children": children,
        "events": events,
        "manifest_ref": manifest_key,
    }
    private_json(worker / "finished" / f"{attempt}.json", finished)
    ledger, actual = canonical(data, plan, data["new"], canon, proof=proof, complete=True)
    assert actual == attempt
    return {
        "attempt": attempt,
        "manifest": manifest,
        "plan": plan,
        "finished": finished,
        "proof": proof,
        "objects": objects,
        "ledger": ledger,
    }


@pytest.fixture(name="settled_history")
def settled_history(real_history, monkeypatch):
    data = real_history
    key, value = candidate(data)
    resolution_candidate.approve(key, key, "resolution-observe-only")
    graph = resolution_graph.initial(value)
    objects = Objects(value["ledger"]["path"])
    monkeypatch.setattr(
        recovery_transition, "observe", lambda c, g: evidence(data, value, objects.get(g), NEW_BOOT)
    )
    proposed = recovery_transition.plan(key, data["attempt"])
    key = proposed["plan_digest"]
    approval = recovery_transition.approve(key, key, "abandon-without-retry-or-success")[
        "approval_digest"
    ]
    recovery_transition.apply(approval)
    return data, value, graph


def test_grouped_completion_preserves_old_final_view_and_allows_next_admission(settled_history):
    data, value, graph = settled_history
    before = recovery_resolution.durable_view(data["new"])
    later = completion(data)
    resolution_graph.unchanged(value, graph, durable=True)
    after = recovery_resolution.durable_view(data["new"])
    assert before == after
    assert after["historical_status"] == "indeterminate"
    assert after["resolution_disposition"] == "abandoned-settled"
    assert later["ledger"].attempt_status(later["attempt"]) == "verified"
    later["ledger"].available()
    # The original graph contains no new worker paths, despite shared selection and metadata.
    assert resolution_graph.build(value, baseline=graph) == graph
    assert later["manifest"]["items"] == data["manifest"]["items"]
    assert len(later["finished"]["events"]) == 3
    assert later["finished"]["children"] == {ref: 80 for ref in data["refs"]}
    assert (
        later["objects"]["dispatch"]["target"]
        == later["finished"]["bindings"][data["refs"][0]]["binding"]
    )
    # Subsequent read-only successful verification deduplicates the same immutable evidence.
    for row in later["proof"]["native"]:
        assert (
            put(data["worker"], later["objects"][f"verification-{row['session_ref']}"])
            == row["evidence_ref"]
        )
    assert recovery_resolution.durable_view(data["new"]) == before
    later["ledger"].available()


def test_native_present_observation_is_a_valid_root_without_absorbing_old_graph(settled_history):
    data, value, graph = settled_history
    later = completion(data)
    observed = deepcopy(later["manifest"])
    for ref, row in observed["items"].items():
        row["present"] = later["finished"]["bindings"][ref]
    observed["saved_selection"] = {
        "missing_refs": [],
        "present_refs": data["refs"],
        "unresolved_refs": [],
    }
    put(data["worker"], observed)
    resolution_graph.unchanged(value, graph, durable=True)
    assert recovery_resolution.durable_view(data["new"])["transition_state"] == "final"
    later["ledger"].available()


def test_already_present_zero_effect_completion_after_grouped_success(settled_history):
    data, value, graph = settled_history
    later = completion(data)
    manifest = deepcopy(later["manifest"])
    for ref, row in manifest["items"].items():
        row["present"] = later["finished"]["bindings"][ref]
    selected = {"missing_refs": [], "present_refs": data["refs"], "unresolved_refs": []}
    manifest["saved_selection"] = selected
    plan = deepcopy(later["plan"])
    plan["recovery"]["observation"]["saved_selection"] = selected
    plan["recovery"]["observation"]["private_ref"] = put(data["worker"], manifest)
    counts, decisions, blockers = recovery.coverage(
        plan["recovery"]["observation"], [], plan["recovery"]["schema"]
    )
    assert not blockers
    plan["recovery"].update(coverage=counts, omissions=decisions)
    attempt = digest(recovery.approval_record(plan, digest(plan)))
    private_json(data["worker"] / "attempts" / f"{attempt}.json", {"request_digest": "e" * 64})
    finished = {
        "complete": True,
        "proof_ref": digest(later["proof"]),
        "bindings": {},
        "children": {},
        "events": [],
        "manifest_ref": digest(manifest),
    }
    private_json(data["worker"] / "finished" / f"{attempt}.json", finished)
    canonical(data, plan, data["new"], proof=later["proof"], complete=True)
    resolution_graph.unchanged(value, graph, durable=True)
    assert recovery_resolution.durable_view(data["new"])["transition_state"] == "final"
    assert later["ledger"].attempt_status(attempt) == "verified"
    later["ledger"].available()


def test_later_pending_prefix_is_not_exempted_by_old_resolution(settled_history):
    data, value, graph = settled_history
    later = completion(data)
    plan = deepcopy(later["plan"])
    plan["created_at"] = (
        datetime.fromisoformat(plan["created_at"]) + timedelta(seconds=1)
    ).isoformat()
    _, attempt = canonical(data, plan, data["new"])
    private_json(data["worker"] / "attempts" / f"{attempt}.json", {"request_digest": "e" * 64})
    resolution_graph.unchanged(value, graph, durable=True)
    assert recovery_resolution.durable_view(data["new"])["transition_state"] == "final"
    assert later["ledger"].attempt_status(attempt) == "indeterminate"
    with pytest.raises(ValueError):
        later["ledger"].available()


@pytest.mark.parametrize(
    "damage",
    [
        "foreign-profile",
        "lost-old-marker",
        "new-old-binding",
        "missing-claim",
        "extra-verification",
        "extra-proof",
        "dimension-orphan",
        "unknown",
        "dispatch",
        "proof",
        "canonical-event",
        "finished",
        "ticket-source",
        "native-source",
    ],
)
def test_later_corruption_and_old_attempt_growth_never_become_unrelated(settled_history, damage):
    data, value, graph = settled_history
    later = completion(data)
    worker, attempt = data["worker"], later["attempt"]
    if damage == "foreign-profile":
        path = later["ledger"].store.path("recovery-prepared", attempt)
        record = later["ledger"].store.recovery_marker("recovery-prepared", attempt)
        record["profile_digest"] = "f" * 64
        private_json(path, record)
    elif damage == "lost-old-marker":
        (worker / "attempts" / f"{data['attempt']}.json").unlink()
    elif damage == "new-old-binding":
        put(
            worker,
            {
                "attempt": data["attempt"],
                "session_ref": data["refs"][0],
                "native": later["finished"]["bindings"][data["refs"][0]],
            },
        )
    elif damage == "missing-claim":
        key = digest({"attempt": attempt, "session_ref": data["refs"][1]})
        (worker / "bootstraps" / f"{key}.started.json").unlink()
    elif damage == "extra-verification":
        put(worker, {"reference": data["refs"][0], "matched": False})
    elif damage == "extra-proof":
        put(worker, {**later["proof"], "interrupted": True})
    elif damage == "dimension-orphan":
        put(worker, {"dimension": "focus", "proved": False})
    elif damage == "unknown":
        put(worker, {"unknown-record": True})
    elif damage == "canonical-event":
        key = digest({"attempt_digest": attempt, "sequence": 1, "event": "result"})
        later["ledger"].store.path("recovery-events", key).unlink()
    elif damage == "ticket-source":
        ref = data["refs"][0]
        key = digest({"attempt": attempt, "session_ref": ref})
        request = deepcopy(later["finished"]["bindings"][ref]["binding"]["bootstrap"]["request"])
        request["node"]["sha256"] = "f" * 64
        private_json(worker / "bootstraps" / f"{key}.json", request)
    elif damage == "native-source":
        ref = data["refs"][0]
        row = deepcopy(later["objects"][f"verification-{ref}"])
        row["native"]["id"] = "00000000-0000-4000-8000-000000000099"
        put(worker, row)
    else:
        obj = (
            later["objects"]["dispatch"]
            if damage == "dispatch"
            else later["proof"]
            if damage == "proof"
            else later["finished"]
        )
        path = (
            worker / "finished" / f"{attempt}.json"
            if damage == "finished"
            else worker / "objects" / f"{digest(obj)}.json"
        )
        obj = deepcopy(obj)
        obj["unsupported"] = True
        private_json(path, obj)
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        resolution_graph.unchanged(value, graph, durable=True)
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        later["ledger"].available()
