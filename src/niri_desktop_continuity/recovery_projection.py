"""Closed optional review projections; absent fields never upgrade historical authority."""

from .recovery_protocol import COUNT, fields, hexkey, require, sequence

GROUPING = "desktop-continuity.saved-grouping.v1"
DIAGNOSTICS = "desktop-continuity.saved-diagnostics.v1"
OPTIONAL = ("grouping", "diagnostics")
REASONS = {
    "native-metadata-unavailable": "Saved native metadata is unavailable or invalid.",
    "native-identity-mismatch": "Observed native identity does not match the selected reference.",
    "live-writer-ambiguous": "More than one possible live writer exists.",
    "existing-native-binding-unproved": "An existing session lacks a complete native binding.",
    "descendant-writer-conflict": "A live descendant prevents reopening the selected original.",
    "group-mixed-presence": "This group mixes present and missing sessions; no partial launch.",
    "group-membership-unproved": "Existing sessions do not prove the requested shared window.",
    "group-host-conflict": "Distinct requested windows share an existing host.",
}


def optional_fields(value):
    """Copy only present, validated-by-caller projections; never manufacture defaults."""
    return {name: value[name] for name in OPTIONAL if name in value}


def grouping(value, saved_set, session_refs):
    fields(value, ("schema", "saved_set", "groups"))
    require(value["schema"] == GROUPING and hexkey(value["saved_set"]) == saved_set)
    groups = sequence(value["groups"])
    require(bool(groups))
    seen = []
    for group in groups:
        fields(group, ("session_refs", "provenance", "reviewed", "sequence"))
        require(group["provenance"] in ("native", "inferred", "requested"))
        require(group["reviewed"] is True and group["sequence"] == "desired-creation")
        refs = sequence(group["session_refs"])
        require(bool(refs))
        seen.extend(hexkey(ref) for ref in refs)
    require(len(seen) <= COUNT and len(seen) == len(set(seen)))
    require(sorted(seen) == session_refs)
    return value


def diagnostics(value, unresolved_refs, selection_proved=None):
    fields(value, ("schema", "reasons", "capacity"))
    require(value["schema"] == DIAGNOSTICS)
    require(value["capacity"] in ("available", "exhausted", "unproved"))
    if selection_proved is not None and value["capacity"] != "available":
        require(selection_proved is False)
    refs = []
    for row in sequence(value["reasons"]):
        fields(row, ("session_ref", "code"))
        refs.append(hexkey(row["session_ref"]))
        require(row["code"] in REASONS)
    require(refs == unresolved_refs)
    return value


def validate(value, saved_set, session_refs, saved_selection, selection_proved=None):
    if "grouping" in value:
        grouping(value["grouping"], saved_set, session_refs)
    if "diagnostics" in value:
        diagnostics(value["diagnostics"], saved_selection["unresolved_refs"], selection_proved)
    return optional_fields(value)
