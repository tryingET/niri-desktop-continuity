"""Exact retained owner first-host history: read bytes, correlate, never run owner code.

The catalog selects this decoder exclusively. Persisted records are neither repaired
nor projected into another store. Normalization below is an in-memory API only.
"""

from pathlib import Path

from .model import digest
from .recovery_profile import profile_pins
from .recovery_protocol import decode, hexkey, require
from .resolution_io import raw, retained_bytes, sha
from .resolution_worker_history_schema import CATALOG, DIRECTORIES, argv, record
from .store import private_directory


def paths(root):
    """Closed catalog and bounded namespace union, including non-digest claim names."""
    require({p.name for p in root.iterdir()} == {*DIRECTORIES, "catalog.json"})
    require(decode(raw(root / "catalog.json")) == CATALOG)
    yield "catalog.json"
    for kind in DIRECTORIES:
        directory = root / kind
        private_directory(directory, create=False)
        maximum = 256 if kind == "attempts" else 4096 if kind == "objects" else 512
        for index, path in enumerate(directory.iterdir()):
            require(index < maximum and path.suffix == ".json")
            key = path.stem
            if kind == "bootstraps" and key.endswith(".started"):
                key = key.removesuffix(".started")
            hexkey(key)
            yield f"{kind}/{path.name}"


def inventory(records, root, candidate=None):
    """Validate all original-associated rows and detect orphan reverse edges explicitly.

    Shared file/session/image hashes are not graph edges. Unexecuted manifests and
    unrelated later first-host prefixes can coexist without enlarging the A0 graph.
    """
    rows = {path: pair for (owner, path), pair in records.items() if owner == "worker"}
    require(rows["catalog.json"][1] == CATALOG)
    roles = {path: record(path, pair[1]) for path, pair in rows.items() if path != "catalog.json"}
    require(sum(role == "request" for role in roles.values()) <= 256)
    require(sum(role == "claim" for role in roles.values()) <= 256)
    objects = {Path(p).stem: (p, rows[p][1]) for p in roles if p.startswith("objects/")}
    attempts = {Path(p).stem for p, role in roles.items() if role == "attempts"}
    attached = {attempt: {f"attempts/{attempt}.json", "catalog.json"} for attempt in attempts}
    for path, role in roles.items():
        value = rows[path][1]
        if role in (
            "manifest",
            "attempts",
            "events",
            "claim",
            "result",
            "dimension",
            "verification",
            "proof",
        ):
            continue
        attempt = Path(path).stem if role == "finished" else value["attempt"]
        require(attempt in attempts)
        attached[attempt].add(path)
        if role in ("children", "request"):
            key = digest({"attempt": attempt, "session_ref": value["session_ref"]})
            require(Path(path).stem == key)
    intents = {}
    for key, (path, value) in objects.items():
        if roles[path] != "intent":
            continue
        attempt, sequence = value["attempt"], value["sequence"]
        marker = f"events/{digest({'attempt': attempt, 'sequence': sequence})}.json"
        require(marker in rows and rows[marker][1] == {"intent_ref": key})
        require((attempt, sequence) not in intents)
        intents[(attempt, sequence)] = key
        attached[attempt].add(marker)
    for path, role in roles.items():
        value = rows[path][1]
        if role == "events":
            key = value["intent_ref"]
            require(key in objects and roles[objects[key][0]] == "intent")
            intent = objects[key][1]
            require(
                path
                == f"events/{digest({'attempt': intent['attempt'], 'sequence': intent['sequence']})}.json"
            )
        if role in ("measurement", "result"):
            key = value["intent_ref"]
            require(key in objects and roles[objects[key][0]] == "intent")
            intent = objects[key][1]
            attempt = intent["attempt"]
            if role == "measurement":
                require(value["attempt"] == attempt)
            else:
                require(value["sequence"] == intent["sequence"])
                measured = objects[value["evidence_ref"]]
                require(roles[measured[0]] == "measurement")
                require(measured[1]["attempt"] == attempt and measured[1]["intent_ref"] == key)
            attached[attempt].add(path)
        if role == "ack":
            result_path, result = objects[value["result_ref"]]
            require(roles[result_path] == "result")
            intent = objects[result["intent_ref"]][1]
            require(
                value["attempt"] == intent["attempt"] and value["sequence"] == result["sequence"]
            )
        if role in ("children", "request"):
            require(
                any(
                    i["attempt"] == value["attempt"]
                    and i["target_ref"] == value["session_ref"]
                    and i["kind"] == "launch"
                    for p, i in objects.values()
                    if roles[p] == "intent"
                )
            )
        if role == "claim":
            request_path = path.removesuffix(".started.json") + ".json"
            require(request_path in rows and roles[request_path] == "request")
            request_raw, request = rows[request_path]
            require(value["request"] == str(root / request_path))
            require(value["request_sha256"] == sha(request_raw))
            require(value["cwd"] == request["cwd"] and value["argv"] == argv(request))
            attached[request["attempt"]].add(path)
    # Every measurement must have its result, and every result may have at most one ACK.
    # A missing ACK is allowed only as unrelated unfinished history, never the A0 prefix.
    for key, (path, value) in objects.items():
        if roles[path] == "measurement":
            require(sum(v.get("evidence_ref") == key for _, v in objects.values()) == 1)
        if roles[path] == "result":
            require(sum(v.get("result_ref") == key for _, v in objects.values()) <= 1)
    for attempt in attempts:
        prepared = records[("ledger", f"recovery-prepared/{attempt}.json")][1]
        plan = records[("ledger", f"plans/{prepared['plan_digest']}.json")][1]
        observed = plan["recovery"]["observation"]
        manifest_path, manifest = objects[observed["private_ref"]]
        require(roles[manifest_path] == "manifest")
        bind_manifest(manifest, plan)
        attached[attempt].add(manifest_path)
        for path in attached[attempt]:
            role = roles.get(path)
            value = rows[path][1]
            if role == "request":
                selected = manifest["items"][value["session_ref"]]
                require(value["session_ref"] in manifest["saved_selection"]["missing_refs"])
                require(all(value[k] == selected["selection"][k] for k in ("file", "id", "cwd")))
                require(value["file_sha256"] == selected["metadata"]["sha256"])
                require(value["expires_at"] == plan["expires_at"])
            if role == "children":
                require(value["host"]["boot_id"] == plan["source_identity"]["boot_id"])
            if role == "claim":
                require(value["boot_id"] == plan["source_identity"]["boot_id"])
    from .resolution_worker_history_completed import extend

    extend(records, rows, roles, attached, objects, candidate)
    return rows, roles, attached


def bind_manifest(manifest, plan):
    observed = plan["recovery"]["observation"]
    for key in (
        "saved_set",
        "identity_digest",
        "state_fingerprint",
        "focus_digest",
        "saved_selection",
    ):
        require(manifest[key] == observed[key])
    require(sorted(manifest["items"]) == observed["session_refs"])
    require(manifest["protected"]["identity"] == plan["source_identity"])
    require(manifest["focus"] == plan["focus_pin"])
    require(
        manifest["projections"]
        == {k: observed[k] for k in ("diagnostics", "grouping") if k in observed}
    )


def source_binding(candidate, request, child, *, side="old"):
    """Bind historic request controls to retained original profile/config, not live pins."""
    from .resolution_candidate import profile_bytes

    config = decode(retained_bytes(candidate[f"{side}_config"]))
    require(config["schema"] == "workstation.saved-reopen.machine.v3")
    pins = {p["path"]: p for p in profile_pins(profile_bytes(candidate[f"{side}_profile"]))}
    for key in ("node", "pi", "bootstrap", "python"):
        path = config["tools"][key]
        require(request[key] == pins[path])
    require(
        request["startup"] == {**config["startup"], "presence": pins[config["tools"]["presence"]]}
    )
    if child is not None:
        require(child["host"]["exe"] == config["tools"]["ghostty"])
        require(child["host"]["exe_sha256"] == pins[config["tools"]["ghostty"]]["sha256"])


def history(candidate, records, ledger, plan):
    rows, roles, attached = inventory(records, Path(candidate["worker"]["path"]), candidate)
    attempt = candidate["attempt_digest"]
    require(attempt in attached)
    paths_for_attempt = attached[attempt]
    manifest_key = plan["recovery"]["observation"]["private_ref"]
    manifest = rows[f"objects/{manifest_key}.json"][1]
    require(manifest["saved_set"] == candidate["saved_set"])
    require(sorted(manifest["items"]) == candidate["selected_refs"])
    require(len(manifest["items"]) == 2 and not manifest["saved_selection"]["unresolved_refs"])
    saved = [
        {
            "session_ref": ref,
            "device": item["metadata"]["device"],
            "inode": item["metadata"]["inode"],
            "prefix_bytes": item["metadata"]["bytes"],
            "prefix_sha256": item["metadata"]["sha256"],
            "metadata_ref": digest(item["metadata"]),
        }
        for ref, item in sorted(manifest["items"].items())
    ]
    result = {
        "manifest": manifest,
        "saved_files": saved,
        "tickets": [],
        "old_boot": plan["source_identity"]["boot_id"],
    }
    events = ledger.events(attempt)
    by_role = {}
    for path in paths_for_attempt - {"catalog.json"}:
        by_role.setdefault(roles[path], []).append(path)
    if candidate["source_contract"]["prefix_rule"] == "zero-permit-v1":
        require(not events and set(by_role) == {"manifest", "attempts"})
        return result, {("worker", path) for path in paths_for_attempt}
    require(candidate["source_contract"]["prefix_rule"] == "direct-first-ack-v1")
    require(
        set(by_role)
        == {
            "manifest",
            "attempts",
            "intent",
            "events",
            "measurement",
            "result",
            "ack",
            "children",
            "request",
            "claim",
        }
    )
    require(all(len(paths) == 1 for paths in by_role.values()))
    values = {role: rows[paths[0]][1] for role, paths in by_role.items()}
    intent, measurement, outcome, ack, child, request, claim = [
        values[k]
        for k in (
            "intent",
            "measurement",
            "result",
            "ack",
            "children",
            "request",
            "claim",
        )
    ]
    require(len(events) == 1 and events[0]["sequence"] == 0 and events[0]["outcome"] == "observed")
    require(intent["sequence"] == outcome["sequence"] == ack["sequence"] == 0)
    require(intent["kind"] == "launch")
    missing = manifest["saved_selection"]["missing_refs"]
    ordered = (
        [ref for g in manifest.get("groups", []) for ref in g["refs"] if ref in missing]
        if "groups" in manifest
        else missing
    )
    require(
        bool(ordered)
        and intent["target_ref"] == ordered[0] == child["session_ref"] == request["session_ref"]
    )
    require(
        {k: events[0]["intent"][k] for k in ("sequence", "kind", "target_ref")}
        == {k: intent[k] for k in ("sequence", "kind", "target_ref")}
    )
    require(events[0]["intent"]["intent_ref"] == digest(intent))
    require({k: events[0]["result"][k] for k in outcome} == outcome)
    require(measurement["measurement"] == child["pid"] == claim["ppid"])
    require(child["host"]["cwd"] == request["cwd"])
    require(claim["pid"] != child["pid"] and claim["start_ticks"] >= child["host"]["start_ticks"])
    source_binding(candidate, request, child)
    result["tickets"] = [
        {
            "request_ref": digest(request),
            "request_sha256": sha(rows[by_role["request"][0]][0]),
            "claim_ref": digest(claim),
            "claim_sha256": sha(rows[by_role["claim"][0]][0]),
            **{key: claim[key] for key in ("boot_id", "pid", "start_ticks")},
            "expires_at": request["expires_at"],
        }
    ]
    return result, {("worker", path) for path in paths_for_attempt}
