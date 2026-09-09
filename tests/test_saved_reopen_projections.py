"""Handwritten review projections and historical compatibility; fabricated state only."""

from copy import deepcopy
from pathlib import Path

import pytest
from test_recovery_orchestration import approve, command, execute
from test_recovery_review_regressions import repin
from test_saved_reopen import effects, plan, settings
from test_saved_reopen import saved_fixture as saved_fixture
from test_saved_reopen_backend import REF, SAVED_SET

from niri_desktop_continuity import recovery
from niri_desktop_continuity.map_preview import render_html
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_protocol import ADDITIVE, observation
from niri_desktop_continuity.recovery_requests import admitted
from niri_desktop_continuity.store import Store

OTHER = "a" * 64
LAST = "f" * 64


def projected(data, *, unresolved=False):
    value = settings(data)
    obs = value["observation"]
    refs = [OTHER, REF, LAST]
    obs["session_refs"] = refs
    obs["saved_selection"] = {
        "missing_refs": [] if unresolved else refs,
        "present_refs": [],
        "unresolved_refs": refs if unresolved else [],
    }
    obs["grouping"] = {
        "schema": "desktop-continuity.saved-grouping.v1",
        "saved_set": SAVED_SET,
        "groups": [
            {
                "session_refs": [LAST, OTHER],
                "provenance": "requested",
                "reviewed": True,
                "sequence": "desired-creation",
            },
            {
                "session_refs": [REF],
                "provenance": "inferred",
                "reviewed": True,
                "sequence": "desired-creation",
            },
        ],
    }
    obs["diagnostics"] = {
        "schema": "desktop-continuity.saved-diagnostics.v1",
        "reasons": [{"session_ref": ref, "code": "group-membership-unproved"} for ref in refs]
        if unresolved
        else [],
        "capacity": "available",
    }
    value["proof"]["native"] = [{**value["proof"]["native"][0], "session_ref": ref} for ref in refs]
    return value


def test_grouping_visible_and_bound_through_existing_cli(saved):
    data = saved()
    value = projected(data)
    repin(data, value)
    result, code = command(
        data,
        "plan",
        data["snapshot_digest"],
        "--intent",
        "reconstruct",
        "--mode",
        "additive",
        "--saved-set",
        SAVED_SET,
        "--adapter-config",
        str(data["root"] / "config.json"),
    )
    assert code == 0 and result["grouping"] == value["observation"]["grouping"]
    key = result["plan_digest"]
    store = Store(data["root"] / "state")
    stored = store.get("plans", key)
    assert recovery.payload(stored)["grouping"] == result["grouping"]
    admitted(recovery.payload(stored), schema=ADDITIVE)
    preview, code = command(data, "preview", key, "--kind", "plans")
    html = Path(preview["html"]).read_text()
    # Literal group/sequence oracle, not renderer/helper self-consistency.
    assert '<th scope="row">Group 1</th><td>requested</td><td><ol>' in html
    assert f"<li><code>{LAST}</code></li><li><code>{OTHER}</code></li>" in html
    assert f'<th scope="row">Group 2</th><td>inferred</td><td><ol><li><code>{REF}</code>' in html
    assert "not verified original tab order" in html
    assert "not a tab-transfer operation" in html
    assert "Private-store capacity: available" in html
    assert not effects(data)
    approval = approve(data, key)
    report, code = execute(data, approval)
    assert code == 0 and report["status"] == "verified"
    for name in ("grouping", "diagnostics"):
        assert report[name] == value["observation"][name]
        assert (
            command(data, "inspect", approval, "--kind", "reconstruction")[0][name] == report[name]
        )
        assert (
            command(data, "verify", approval, "--kind", "reconstruction")[0][name] == report[name]
        )
    assert [row["kind"] for row in effects(data)] == ["launch", "launch", "launch", "focus"]


def test_missing_projections_never_upgrade_historical_meaning(saved):
    data = saved()
    key = plan(data)
    stored = Store(data["root"] / "state").get("plans", key)
    before = digest(stored)
    assert all(name not in recovery.payload(stored) for name in ("grouping", "diagnostics"))
    html = render_html(data["snapshot"], plan=stored)
    assert "Grouping not supplied" in html and "Desired shared-window groups" not in html
    report, code = execute(data, approve(data, key))
    assert code == 0
    assert all(name not in report for name in ("grouping", "diagnostics"))
    assert digest(stored) == before


@pytest.mark.parametrize(
    "damage",
    [
        "foreign-set",
        "foreign-schema",
        "extra",
        "empty-groups",
        "empty-members",
        "duplicate",
        "unknown-ref",
        "missing-ref",
        "unreviewed",
        "bad-provenance",
        "native-order",
        "bad-order-type",
    ],
)
def test_closed_grouping_partition_refuses_ambiguous_or_overclaiming_input(saved, damage):
    data = saved()
    obs = projected(data)["observation"]
    group = obs["grouping"]
    first = group["groups"][0]
    if damage == "foreign-set":
        group["saved_set"] = "0" * 64
    elif damage == "foreign-schema":
        group["schema"] = "unknown"
    elif damage == "extra":
        first["title"] = "FABRICATED-PRIVATE"
    elif damage == "empty-groups":
        group["groups"] = []
    elif damage == "empty-members":
        first["session_refs"] = []
    elif damage == "duplicate":
        first["session_refs"] = [LAST, LAST]
    elif damage == "unknown-ref":
        first["session_refs"] = ["0" * 64, OTHER]
    elif damage == "missing-ref":
        first["session_refs"] = [LAST]
    elif damage == "unreviewed":
        first["reviewed"] = 1
    elif damage == "bad-provenance":
        first["provenance"] = "title-match"
    elif damage == "native-order":
        first["sequence"] = "exact-native-order"
    elif damage == "bad-order-type":
        first["session_refs"] = {"first": LAST}
    with pytest.raises(ValueError):
        observation(obs, digest([]), ADDITIVE)


@pytest.mark.parametrize(
    "damage", ["missing", "duplicate", "unordered", "unknown", "extra", "capacity", "contradiction"]
)
def test_diagnostics_are_closed_exact_and_not_secret_bearing(saved, damage):
    data = saved()
    obs = projected(data, unresolved=True)["observation"]
    diagnostics = obs["diagnostics"]
    if damage == "missing":
        diagnostics["reasons"].pop()
    elif damage == "duplicate":
        diagnostics["reasons"][1] = diagnostics["reasons"][0]
    elif damage == "unordered":
        diagnostics["reasons"].reverse()
    elif damage == "unknown":
        diagnostics["reasons"][0]["code"] = "exception text"
    elif damage == "extra":
        diagnostics["reasons"][0]["path"] = "FABRICATED-PRIVATE"
    elif damage == "capacity":
        diagnostics["capacity"] = "plenty"
    elif damage == "contradiction":
        diagnostics["capacity"] = "exhausted"
    with pytest.raises(ValueError):
        observation(obs, digest([]), ADDITIVE)


@pytest.mark.parametrize(
    "capacity,blocker",
    [
        ("exhausted", "saved-store-capacity-exhausted"),
        ("unproved", "saved-store-capacity-unproved"),
    ],
)
def test_capacity_and_per_reference_reason_are_visible_without_generic_misdirection(
    saved, capacity, blocker
):
    data = saved()
    value = projected(data, unresolved=True)
    value["observation"]["selection_proved"] = False
    value["observation"]["diagnostics"]["capacity"] = capacity
    repin(data, value)
    key = plan(data)
    stored = Store(data["root"] / "state").get("plans", key)
    assert blocker in stored["admission"]["blockers"]
    assert (
        "saved-selection-identity-absence-or-protection-unproved"
        not in stored["admission"]["blockers"]
    )
    rendered = render_html(data["snapshot"], plan=stored)
    assert f"Private-store capacity: {capacity}" in rendered
    assert rendered.count("Existing sessions do not prove the requested shared window.") == 3
    with pytest.raises(ValueError):
        approve(data, key)
    assert effects(data) == []


def test_review_projection_tampering_changes_digest_and_refuses_approval(saved, monkeypatch):
    from niri_desktop_continuity.recovery_adapter import Adapter

    data = saved()
    value = projected(data)
    repin(data, value)
    key = plan(data)
    changed = deepcopy(value["observation"])
    changed["grouping"]["groups"][0]["session_refs"].reverse()
    assert digest(changed) != digest(value["observation"])
    monkeypatch.setattr(Adapter, "call", lambda *a, **kw: changed)
    with pytest.raises(ValueError):
        approve(data, key)
    assert effects(data) == []
