"""Explicit prospective fixture codec, separate from the retained owner decoder."""

from .model import digest
from .recovery_protocol import fields, hexkey, require
from .resolution_io import sha

WORKER = "desktop-continuity.resolution-worker-data.v1"


def worker_value(kind, key, value):
    """Closed prospective codec; no arbitrary JSON-pointer historical reinterpretation."""
    if kind == "attempts":
        fields(value, ("request_digest",))
        hexkey(value["request_digest"])
        return
    fields(value, ("schema", "kind", "attempt_digest", "sequence", "refs", "data"))
    require(
        value["schema"] == WORKER
        and value["kind"]
        in ("manifest", "intent", "result", "ack", "child", "request", "started", "finished")
    )
    directories = {
        "manifest": "objects",
        "intent": "events",
        "result": "objects",
        "ack": "events",
        "child": "children",
        "request": "requests",
        "started": "started",
        "finished": "finished",
    }
    require(kind == directories[value["kind"]])
    require(key == (value["attempt_digest"] if value["kind"] == "finished" else digest(value)))
    hexkey(value["attempt_digest"])
    require(type(value["sequence"]) is int and 0 <= value["sequence"] < 256)
    require(type(value["refs"]) is list and len(value["refs"]) <= 256)
    for ref in value["refs"]:
        hexkey(ref)
    require(value["refs"] == sorted(set(value["refs"])))
    layouts = {
        "manifest": ("saved_set", "selected_refs", "first_ref", "saved_files"),
        "intent": ("intent_ref", "target_ref"),
        "result": ("intent_ref", "measurement_ref", "pid"),
        "ack": ("intent_ref", "result_ref", "child_ref"),
        "child": ("boot_id", "pid", "start_ticks", "measurement_ref"),
        "request": ("child_ref", "session_ref", "file_sha256", "expires_at", "argv_digest"),
        "started": (
            "request_ref",
            "request_sha256",
            "boot_id",
            "pid",
            "start_ticks",
            "ppid",
            "argv_digest",
        ),
        "finished": (),
    }
    fields(value["data"], layouts[value["kind"]])


def prefix(candidate, records, ledger, plan):
    attempt = candidate["attempt_digest"]
    events = ledger.events(attempt)
    worker = [
        (slot, value)
        for slot, (_, value) in records.items()
        if slot[0] == "worker"
        and (value.get("attempt_digest") == attempt or slot[1] == f"attempts/{attempt}.json")
    ]
    require(sum(slot[1] == f"attempts/{attempt}.json" for slot, _ in worker) == 1)
    require(all(value.get("kind") != "finished" for _, value in worker))
    manifests = [v["data"] for _, v in worker if v.get("kind") == "manifest"]
    require(len(manifests) == 1)
    manifest = manifests[0]
    require(manifest["saved_set"] == candidate["saved_set"])
    require(manifest["selected_refs"] == candidate["selected_refs"])
    require(manifest["first_ref"] in candidate["selected_refs"])
    require(type(manifest["saved_files"]) is list and len(manifest["saved_files"]) == 2)
    require([f["session_ref"] for f in manifest["saved_files"]] == candidate["selected_refs"])
    for saved in manifest["saved_files"]:
        fields(
            saved,
            ("session_ref", "device", "inode", "prefix_bytes", "prefix_sha256", "metadata_ref"),
        )
        for key in ("session_ref", "prefix_sha256", "metadata_ref"):
            hexkey(saved[key])
        require(
            all(
                type(saved[k]) is int and saved[k] >= 0 for k in ("device", "inode", "prefix_bytes")
            )
        )
    rule = candidate["source_contract"]["prefix_rule"]
    if rule == "zero-permit-v1":
        require(
            not events
            and all(
                "request_digest" in value or value.get("kind") == "manifest" for _, value in worker
            )
        )
        return
    require(len(events) == 1 and events[0]["sequence"] == 0 and events[0]["outcome"] == "observed")
    intent = events[0]["intent"]
    require(intent["kind"] == "launch" and intent["target_ref"] in candidate["selected_refs"])
    roles = {}
    for slot, value in worker:
        if "request_digest" in value:
            continue
        role = value["kind"]
        require(role not in roles and value["sequence"] == 0)
        roles[role] = (slot[1].split("/")[1][:-5], value["data"])
    require(set(roles) == {"manifest", "intent", "result", "ack", "child", "request", "started"})
    manifest, wi, result, ack, child, request, started = [
        roles[k][1] for k in ("manifest", "intent", "result", "ack", "child", "request", "started")
    ]
    require(
        manifest["saved_set"] == candidate["saved_set"]
        and manifest["selected_refs"] == candidate["selected_refs"]
    )
    require(
        manifest["first_ref"] == wi["target_ref"] == intent["target_ref"] == request["session_ref"]
    )
    require(wi["intent_ref"] == result["intent_ref"] == ack["intent_ref"] == intent["intent_ref"])
    require(
        ack["result_ref"] == roles["result"][0]
        and ack["child_ref"] == request["child_ref"] == roles["child"][0]
    )
    require(events[0]["result"]["evidence_ref"] == roles["result"][0])
    require(result["measurement_ref"] == child["measurement_ref"])
    require(
        type(child["pid"]) is int
        and child["pid"] > 1
        and result["pid"] == child["pid"] == started["ppid"]
    )
    require(type(started["pid"]) is int and started["pid"] > 1)
    require(all(type(v["start_ticks"]) is int and v["start_ticks"] > 0 for v in (child, started)))
    require(child["boot_id"] == started["boot_id"] == plan["source_identity"]["boot_id"])
    require(
        started["request_ref"] == roles["request"][0]
        and started["argv_digest"] == request["argv_digest"]
    )
    request_raw = next(
        data
        for (root, path), (data, _) in records.items()
        if root == "worker" and path.endswith(f"/{roles['request'][0]}.json")
    )
    require(started["request_sha256"] == sha(request_raw))
    for key in ("file_sha256", "argv_digest"):
        hexkey(request[key])
    require(
        request["file_sha256"]
        == next(
            f["prefix_sha256"]
            for f in manifest["saved_files"]
            if f["session_ref"] == request["session_ref"]
        )
    )
