"""Fresh verification after transition; prospective codec isolates the accounting route."""

from copy import deepcopy

import pytest
from test_recovery_backend import private_json
from test_resolution_fixtures import approved, forbidden
from test_resolution_fixtures import resolution as resolution_fixture  # noqa: F401

from niri_desktop_continuity import recovery, recovery_resolution, recovery_transition
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.recovery_verification import receipt
from niri_desktop_continuity.store import Store


def later_attempt(data, monkeypatch, status):
    approval, _ = approved(data, monkeypatch)
    recovery_transition.apply(approval)
    new, root = data["new"], data["root"]
    private_json(
        root / "config.json",
        {
            "schema": new["schema"],
            "profile_digest": digest(new),
            "interpreter": new["interpreter"],
            "endpoint": new["endpoint"],
        },
    )
    store = Store(root / "state")
    snapshot = data["original_plan"]["snapshot_digest"]
    proposal = recovery.propose(
        store,
        snapshot,
        root / "config.json",
        store.get("snapshots", snapshot),
        mode="additive",
        saved_set=data["manifest"]["saved_set"],
    )
    assert proposal["admission"]["status"] == "awaiting-approval"
    plan = store.get("plans", proposal["plan_digest"])
    approval = recovery.approval_record(plan, digest(plan))
    key = store.put("approvals", approval)
    ledger = Ledger(new)
    ledger.store.put("plans", plan)
    ledger.store.put("approvals", approval)
    pair = ledger.prepare(store, key, digest(plan))
    # Handwritten full two-launch/focus history, not an effect-planning helper.
    events = []
    for sequence, (kind, target) in enumerate(
        [("launch", "b" * 64), ("launch", "c" * 64), ("focus", digest(plan["focus_pin"]))]
    ):
        intent = {
            "sequence": sequence,
            "kind": kind,
            "target_ref": target,
            "intent_ref": str(sequence + 1) * 64,
        }
        result = {
            "sequence": sequence,
            "intent_ref": intent["intent_ref"],
            "outcome": "observed",
            "evidence_ref": "e" * 64,
        }
        ledger.event(key, "intent", intent)
        ledger.event(key, "result", result)
        events.append(result)
    proof = {
        "dimensions": {
            name: {"status": "proved", "evidence_ref": "e" * 64}
            for name in ("causal_ownership", "new_images", "focus", "protected_preservation")
        },
        "native": [
            {
                "session_ref": ref,
                "evidence_ref": "f" * 64,
                "file": True,
                "cwd": True,
                "runtime": True,
                "bootstrap": True,
                "surface": True,
                "causal_window": True,
            }
            for ref in ("b" * 64, "c" * 64)
        ],
        "interrupted": False,
        "unresolved_children": 0,
    }
    historical_proof = deepcopy(proof)
    if status == "partial":
        historical_proof["native"][0]["cwd"] = False
    ledger.finish(
        store,
        pair,
        receipt(
            plan, key, historical_proof, history_complete=status != "indeterminate", events=events
        ),
    )
    # Deliberately prospective history, not an actual-owner completed-history claim.
    private_json(data["worker"] / "attempts" / f"{key}.json", {"request_digest": "a" * 64})
    assert ledger.attempt_status(key) == status
    return store, ledger, key, plan, proof


@pytest.mark.parametrize("history", ["verified", "partial", "indeterminate"])
@pytest.mark.parametrize("fresh_complete", [True, False])
def test_final_then_later_attempt_fresh_verification_uses_own_history_and_proof(
    resolution, monkeypatch, history, fresh_complete
):
    store, ledger, key, plan, proof = later_attempt(resolution, monkeypatch, history)
    before = {p: p.read_bytes() for p in ledger.store.root.rglob("*") if p.is_file()}
    if not fresh_complete:
        proof["native"][1]["cwd"] = False
    calls = []

    def verify(adapter, phase, payload):
        assert adapter.profile == resolution["new"]
        assert phase == "verify" and payload["attempt_digest"] == key
        assert payload["plan_digest"] == digest(plan)
        calls.append(phase)
        return deepcopy(proof)

    monkeypatch.setattr(Adapter, "call", verify)
    monkeypatch.setattr(Ledger, "admission_disposition", forbidden)
    report = recovery.inspect_or_verify(store, key, verify=True)
    expected = (
        "indeterminate" if history != "verified" else "verified" if fresh_complete else "partial"
    )
    assert report["status"] == expected
    assert report["historical_status"] == history
    assert report["fresh_verification"] is True and report["proof"] == proof
    assert report["attempt_digest"] == key and calls == ["verify"]
    edge = recovery_resolution.durable_view(resolution["new"])
    assert ledger.disposition(resolution=edge) == sorted(
        [
            {"attempt_digest": resolution["attempt"], "status": "indeterminate"},
            {"attempt_digest": key, "status": history},
        ],
        key=lambda row: row["attempt_digest"],
    )
    assert resolution["ledger"].attempt_status(resolution["attempt"]) == "indeterminate"
    # An abandoned old-profile target cannot borrow the new profile's proof.
    with pytest.raises(ValueError):
        recovery.inspect_or_verify(store, resolution["attempt"], verify=True)
    assert calls == ["verify"]
    assert before == {p: p.read_bytes() for p in ledger.store.root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("damage", ["edge", "later-profile"])
def test_later_fresh_verification_rejects_damaged_edge_or_foreign_accounting(
    resolution, monkeypatch, damage
):
    store, ledger, key, _, _ = later_attempt(resolution, monkeypatch, "verified")
    if damage == "edge":
        (path,) = (ledger.store.root / "resolution-final").iterdir()
        path.write_text("{}")
    else:
        path = ledger.store.path("recovery-prepared", key)
        record = ledger.store.recovery_marker("recovery-prepared", key)
        record["profile_digest"] = digest(resolution["old"])
        private_json(path, record)
    monkeypatch.setattr(Adapter, "call", forbidden)
    with pytest.raises(ValueError):
        recovery.inspect_or_verify(store, key, verify=True)
