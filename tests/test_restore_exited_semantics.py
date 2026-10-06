"""Handwritten tampering oracles: content-address consistency is not semantic validity."""

import json
from copy import deepcopy

import pytest
from test_restore_exited_contract import accounting as accounting  # noqa: F401
from test_restore_exited_history import FAMILY, scene, sha  # noqa: F401
from test_restore_exited_history import legacy_ten as legacy_ten

from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history


@pytest.mark.parametrize("offset", range(10))
def test_each_suffix_payload_is_closed(legacy_ten, offset):
    s = legacy_ten
    previous = None
    for seq in range(10):
        path = s.directory / f"{seq:08d}.json"
        record = json.loads(path.read_text())
        if seq == offset:
            payload = s.store.get("receipts", record["receipt"])
            payload["unreviewed"] = True
            record["receipt"] = s.store.put("receipts", payload)
        record["previous"] = previous
        path.write_text(json.dumps(record))
        previous = sha(record)
    with pytest.raises(ValueError):
        d.inspect(s.store, None, s.attempt, s.interrupted, s.result, s.exit_file, family=FAMILY)


def test_later_diagnostic_read_is_not_rejected_sample_or_preservation(legacy_ten):
    s = legacy_ten
    receipt = deepcopy(s.receipt)
    receipt["final_observation"] = scene(0)
    receipt["final_observation"]["windows"][0]["layout"]["tile_size"][1] = 1234.0
    key = s.store.put("receipts", receipt)
    s.result.write_text(json.dumps({"snapshot_digest": s.source, "receipt_digest": key, **receipt}))
    assert d.inspect(s.store, None, s.attempt, key, s.result, s.exit_file, family=FAMILY)[
        "eligible_family"
    ]


def rewrite(s, result, change):
    plan = s.store.get("plans", s.plan)
    receipt = s.store.get("receipts", result["receipt_digest"])
    change(plan, receipt)
    plan_key = s.store.put("plans", plan)
    approval = s.store.get("approvals", s.approval)
    approval.update(plan=plan_key, confirmation=plan_key)
    approval_key = s.store.put("approvals", approval)
    used = {
        "schema": "desktop-continuity.restore-disposition.v3",
        "family": FAMILY,
        "branch": "exact-process-exited-and-window-absent",
        "intent": "restore-disposition",
        "approval": approval_key,
        "plan": plan_key,
    }
    path = s.store.path("used", approval_key)
    path.write_text(json.dumps(used))
    path.chmod(0o600)
    receipt.update(plan=plan_key, approval=approval_key, current_digest=sha(plan["current"]))
    key = s.store.put("receipts", receipt)
    path = s.directory / "00000010.json"
    record = json.loads(path.read_text())
    record["receipt"] = key
    path.write_text(json.dumps(record))
    return approval_key


@pytest.mark.parametrize(
    "case",
    [
        "branch",
        "method",
        "owned",
        "missing-protected",
        "bool-process",
        "float-pid",
        "duplicate-process",
        "peer-credential",
        "inventory",
        "version",
        "namespace",
        "absence",
        "controller-overlap",
        "controller-gap",
        "caller-first",
        "extra-current",
        "platform",
        "segment-count",
        "segment-envelope",
        "manifest-extra",
        "manifest-missing",
        "manifest-duplicate",
        "receipt-layout",
        "receipt-retry",
        "receipt-extra",
        "receipt-platform",
        "receipt-caller-overlap",
    ],
)
def test_self_consistent_false_graph_never_admits(accounting, case):
    s = accounting
    result = d.apply(s.store, s.approval)

    def change(plan, receipt):
        current = plan["current"]
        if case == "branch":
            plan["branch"] = "present-host"
        elif case == "method":
            current["method"] = "process-lookup-error"
        elif case == "owned":
            current["owned_window_ids"] = [70]
        elif case == "missing-protected":
            current["protected_window_ids"].pop()
        elif case == "bool-process":
            current["processes"][0]["start_ticks"] = True
        elif case == "float-pid":
            current["processes"][0]["pid"] = 170.0
        elif case == "duplicate-process":
            current["processes"].append(current["processes"][0])
        elif case == "peer-credential":
            current["peer"]["credentials"]["pid"] += 1
        elif case == "inventory":
            current["peer"]["inventory"]["row_digest"] = "a" * 64
        elif case == "version":
            current["peer"]["version"] = "fixture-client"
        elif case == "namespace":
            current["scope"]["procfs"]["pid_namespace"]["inode"] += 1
        elif case == "absence":
            current["absence"]["errno"] = "ENOENT"
        elif case == "controller-overlap":
            current["caller"]["ancestry"][0]["process"]["pid"] = 2000
            current["caller"]["process"]["pid"] = 2000
        elif case == "controller-gap":
            current["caller"]["ancestry"][0]["ppid"] = 2
        elif case == "caller-first":
            current["caller"]["process"]["pid"] += 1
        elif case == "extra-current":
            current["coherent"] = True
        elif case == "platform":
            plan["platform"]["historical_executable"] = "attested"
        elif case == "segment-count":
            plan["segment"]["count"] = 10.0
        elif case == "segment-envelope":
            plan["segment"]["focus_observed"] = plan["history_tail"]
        elif case == "manifest-extra":
            plan["manifest"].append(plan["witness"]["client_exit"])
        elif case == "manifest-missing":
            plan["manifest"].pop()
        elif case == "manifest-duplicate":
            plan["manifest"].append(plan["manifest"][0])
        elif case == "receipt-layout":
            receipt["historical_layout"] = "complete"
        elif case == "receipt-retry":
            receipt["retry_authorized"] = 0
        elif case == "receipt-extra":
            receipt["success"] = True
        elif case == "receipt-platform":
            receipt["platform_ack"] = "b" * 64
        elif case == "receipt-caller-overlap":
            pin = {"boot_id": "fabricated-boot", "pid": 3000, "start_ticks": 999}
            receipt["caller"] = {"process": pin, "ancestry": [{"process": pin, "ppid": 1}]}

    approval = rewrite(s, result, change)
    with pytest.raises(ValueError):
        history.admit(s.identity)
    with pytest.raises(ValueError):
        d.apply(s.store, approval)
