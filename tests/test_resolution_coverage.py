"""Handwritten version/scope oracles; historical full-set v1 never gains v2 meaning."""

from copy import deepcopy

import pytest
from test_resolution_fixtures import candidate, packet
from test_resolution_fixtures import resolution as resolution_fixture  # noqa: F401

from niri_desktop_continuity.model import digest
from niri_desktop_continuity.resolution_evidence import persist_packet
from niri_desktop_continuity.resolution_graph import initial
from niri_desktop_continuity.resolution_io import Objects


def replace(value, key, attachment):
    scan = value["evidence"]["process_scan"]
    values = {a["digest"]: a["value"] for a in value["attachments"]}
    scan[key] = digest(attachment)
    values[digest(attachment)] = attachment
    used = {v for k, v in scan.items() if k.endswith("_ref")} | set(value["evidence"]["writers"])
    value["attachments"] = [{"digest": k, "value": values[k]} for k in sorted(used)]


def scoped(value):
    names = {
        "schema": "desktop-continuity.process-names.v2",
        "discovery_scope": "all-visible-same-account-tasks",
        "stability_scope": "candidate-and-protected-cohort",
        "tasks": [20],
    }
    for key in ("names_before_ref", "names_after_ref"):
        replace(value, key, names)
    discovery = deepcopy(
        next(
            a["value"]
            for a in value["attachments"]
            if a["value"]["schema"] == "desktop-continuity.candidate-discovery.v1"
        )
    )
    discovery["rows"][0]["classification"] = "protected"
    replace(value, "attribution_ref", discovery)
    return value


def test_v1_full_set_still_retains_noncandidates_and_requires_full_equality(resolution):
    _, c = candidate(resolution)
    graph = initial(c)
    objects = Objects(c["ledger"]["path"])
    value = packet(c, digest(graph))
    assert objects.get(persist_packet(value, c, graph, objects))["verdict"] == "settled"
    # A harmless extra task is still required in v1, never treated as scoped churn.
    replace(
        value,
        "names_after_ref",
        {"schema": "desktop-continuity.process-names.v1", "tasks": [20, 21]},
    )
    with pytest.raises(ValueError):
        persist_packet(value, c, graph, objects)
    value["evidence"].update(verdict="blocked", blockers=["census-incomplete"])
    assert objects.get(persist_packet(value, c, graph, objects))["verdict"] == "blocked"


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "discovery",
        "stability",
        "missing-scope",
        "extra-field",
        "mixed",
        "lying-v1",
        "noncandidate",
        "rows-mismatch",
        "incomplete",
    ],
)
def test_v2_exact_pair_scope_and_rows(resolution, fault):
    _, c = candidate(resolution)
    graph = initial(c)
    objects = Objects(c["ledger"]["path"])
    value = scoped(packet(c, digest(graph)))
    names = deepcopy(
        next(
            a["value"]
            for a in value["attachments"]
            if a["value"]["schema"] == "desktop-continuity.process-names.v2"
        )
    )
    if fault == "discovery":
        names["discovery_scope"] = "candidate-and-protected-cohort"
    elif fault == "stability":
        names["stability_scope"] = "all-visible-same-account-tasks"
    elif fault == "missing-scope":
        del names["discovery_scope"]
    elif fault == "extra-field":
        names["complete"] = True
    elif fault == "mixed":
        names = {"schema": "desktop-continuity.process-names.v1", "tasks": [20]}
    elif fault == "lying-v1":
        names["schema"] = "desktop-continuity.process-names.v1"
    elif fault == "rows-mismatch":
        names["tasks"] = [20, 21]
    elif fault == "noncandidate":
        discovery = deepcopy(
            next(
                a["value"]
                for a in value["attachments"]
                if a["value"]["schema"] == "desktop-continuity.candidate-discovery.v1"
            )
        )
        discovery["rows"][0]["classification"] = "noncandidate"
        replace(value, "attribution_ref", discovery)
    elif fault == "incomplete":
        value["evidence"]["process_scan"]["complete"] = False
    replace(value, "names_after_ref", names)
    if fault is None:
        assert objects.get(persist_packet(value, c, graph, objects))["verdict"] == "settled"
    else:
        with pytest.raises(ValueError):
            persist_packet(value, c, graph, objects)
