"""Rooted later-history traversal. Shared session/file/image hashes are never edges."""

from pathlib import Path

from .model import digest
from .recovery_additive import proof
from .recovery_ledger import Ledger
from .recovery_protocol import require
from .resolution_candidate import profile_bytes
from .resolution_io import sha


def extend(records, rows, roles, attached, objects, candidate=None):
    claimed = set().union(*attached.values()) if attached else set()

    def take(key, role, owner):
        path, value = objects[key]
        require(roles[path] == role)
        claimed.add(path)
        if owner is not None:
            attached[owner].add(path)
        return value

    def native(row, owner, *, launched=False, metadata=None, manifest_ref=None):
        ticket = row["binding"]["bootstrap"]
        if ticket["kind"] != "retained-exec-ticket":
            require(not launched)
            return
        request, claim = ticket["request"], ticket["claim"]
        origin = request["attempt"]
        require(origin in attached)
        if candidate is not None and origin == candidate["attempt_digest"]:
            # An embedded exact old executor ticket IS an A0 edge; a shared saved ref is not.
            require(owner == origin and manifest_ref is None)
        if launched:
            require(origin == owner)
            require(request["file_sha256"] == metadata["sha256"])
        key = digest({"attempt": origin, "session_ref": request["session_ref"]})
        path = f"bootstraps/{key}.json"
        require(rows[path][1] == request and rows[f"bootstraps/{key}.started.json"][1] == claim)
        require(sha(rows[path][0]) == claim["request_sha256"])

    # Observations are explicit roots, not arbitrary object fallback. Their embedded
    # native tickets still require original request/claim bytes and known provenance.
    for key, (path, value) in objects.items():
        if roles[path] == "manifest":
            claimed.add(path)
            for item in value["items"].values():
                if item["present"] is not None:
                    native(item["present"], None, manifest_ref=key)
                    require(
                        item["present"]["process"]["boot_id"]
                        == value["protected"]["identity"]["boot_id"]
                    )

    for attempt in attached:
        prepared = records[("ledger", f"recovery-prepared/{attempt}.json")][1]
        plan = records[("ledger", f"plans/{prepared['plan_digest']}.json")][1]
        manifest_key = plan["recovery"]["observation"]["private_ref"]
        manifest = objects[manifest_key][1]
        if candidate is not None and attempt != candidate["attempt_digest"]:
            current = Ledger(profile_bytes(candidate["new_profile"]), read_only=True)
            try:
                current.attempt_status(attempt)
            except FileNotFoundError:
                # Legitimate unfinished prefixes remain pending; normal admission still blocks.
                pass
        by_role = {}
        for path in list(attached[attempt]):
            by_role.setdefault(roles.get(path), []).append(path)
        children = {rows[p][1]["session_ref"]: (p, rows[p][1]) for p in by_role.get("children", [])}
        for path in by_role.get("dispatch", []):
            dispatch = rows[path][1]
            ref = dispatch["session_ref"]
            require(ref in manifest["saved_selection"]["missing_refs"])
            # A pending pre-send dispatch is rooted by its issued intent and request.
            require(any(rows[p][1]["session_ref"] == ref for p in by_role.get("request", [])))
            require(
                any(
                    rows[p][1]["kind"] == "launch" and rows[p][1]["target_ref"] == ref
                    for p in by_role.get("intent", [])
                )
            )
            target = dispatch["target"]
            anchors = [
                rows[p][1]
                for p in by_role.get("binding", [])
                if rows[p][1]["native"]["binding"] == target
            ]
            require(len(anchors) == 1)
            group = next(g for g in manifest["groups"] if ref in g["refs"])
            require(group["refs"][0] == anchors[0]["session_ref"] != ref)
            if ref in children:
                require(children[ref][1].get("dispatch_ref") == Path(path).stem)
        for path in by_role.get("binding", []):
            bound = rows[path][1]
            ref = bound["session_ref"]
            require(ref in children)
            row = bound["native"]
            require(row["binding"]["host"] == children[ref][1]["host"])
            require(
                all(row[k] == manifest["items"][ref]["selection"][k] for k in ("file", "id", "cwd"))
            )
            native(row, attempt, launched=True, metadata=manifest["items"][ref]["metadata"])
        for ref, (_, child) in children.items():
            if "dispatch_ref" in child:
                dispatch = take(child["dispatch_ref"], "dispatch", attempt)
                require(dispatch["attempt"] == attempt and dispatch["session_ref"] == ref)
                require(dispatch["target"]["host"] == child["host"])
        if candidate is not None and attempt != candidate["attempt_digest"]:
            from .resolution_worker_history import source_binding

            for path in by_role.get("request", []):
                request = rows[path][1]
                child = children.get(request["session_ref"])
                source_binding(candidate, request, child[1] if child else None, side="new")

        def evidence(value, bindings, complete):
            require(proof(value, sorted(manifest["items"])) == complete)
            for name, row in value["dimensions"].items():
                dimension = take(row["evidence_ref"], "dimension", attempt)
                require(dimension == {"dimension": name, "proved": row["status"] == "proved"})
            for row in value["native"]:
                verification = take(row["evidence_ref"], "verification", attempt)
                ref = row["session_ref"]
                require(verification["reference"] == ref and ref in manifest["items"])
                expected = bindings.get(ref) or manifest["items"][ref]["present"]
                if "native" in verification:
                    require(verification["native"] == expected)
                    native(
                        expected,
                        attempt,
                        launched=ref in bindings,
                        metadata=manifest["items"][ref]["metadata"],
                    )
                    if complete:
                        require(verification["saved_prefix_preserved"] is True)
                else:
                    require(not complete)

        finished_path = f"finished/{attempt}.json"
        if finished_path not in rows:
            continue
        finished = rows[finished_path][1]
        require(finished["manifest_ref"] == manifest_key)
        result = take(finished["proof_ref"], "proof", attempt)
        bindings = finished["bindings"]
        require(
            set(bindings)
            == set(finished["children"])
            == set(children)
            == set(manifest["saved_selection"]["missing_refs"])
        )
        require(len(by_role.get("binding", [])) == len(bindings))
        for ref, row in bindings.items():
            child = children[ref][1]
            require(child["pid"] == finished["children"][ref] == row["binding"]["host"]["pid"])
            bound = {"attempt": attempt, "session_ref": ref, "native": row}
            require(take(digest(bound), "binding", attempt) == bound)
            if manifest.get("groups"):
                group = next(g for g in manifest["groups"] if ref in g["refs"])
                if ref != group["refs"][0]:
                    dispatch = take(child["dispatch_ref"], "dispatch", attempt)
                    require(dispatch["target"] == bindings[group["refs"][0]]["binding"])
                    require(
                        all(
                            dispatch["target"][k] == row["binding"][k]
                            for k in ("host", "window", "bus")
                        )
                    )
                else:
                    require("dispatch_ref" not in child)
        for group in manifest.get("groups", []):
            members = [
                bindings.get(ref) or manifest["items"][ref]["present"] for ref in group["refs"]
            ]
            require(all(row is not None for row in members))
            first = members[0]["binding"]
            require(
                all(
                    all(row["binding"][k] == first[k] for k in ("host", "window", "bus"))
                    for row in members
                )
            )
            require(len({row["process"]["pid"] for row in members}) == len(members))
            require(len({int(row["binding"]["surface"], 0) for row in members}) == len(members))
        evidence(result, bindings, finished["complete"])
        ordered = (
            [ref for g in manifest.get("groups", []) for ref in g["refs"] if ref in bindings]
            if "groups" in manifest
            else sorted(bindings)
        )
        require(len(finished["events"]) == len(ordered) + bool(ordered))
        require(
            len(by_role.get("intent", []))
            == len(by_role.get("result", []))
            == len(by_role.get("ack", []))
            == len(finished["events"])
        )
        for index, refs in enumerate(finished["events"]):
            intent = take(refs["intent"], "intent", attempt)
            outcome = take(refs["result"], "result", attempt)
            ack = take(refs["ack"], "ack", attempt)
            require(intent["attempt"] == attempt and intent["sequence"] == index)
            require(intent["kind"] == ("launch" if index < len(ordered) else "focus"))
            require(
                intent["target_ref"]
                == (ordered[index] if index < len(ordered) else manifest["focus_digest"])
            )
            require(outcome["sequence"] == index and outcome["intent_ref"] == refs["intent"])
            require(ack == {"attempt": attempt, "sequence": index, "result_ref": refs["result"]})
            measured = take(outcome["evidence_ref"], "measurement", attempt)
            expected = (
                children[ordered[index]][1]["pid"]
                if index < len(ordered)
                else {"focused": manifest["focus"]["windows"][0]}
            )
            require(measured["measurement"] == expected)
            for kind, expected in (
                (
                    "intent",
                    {k: intent[k] for k in ("sequence", "kind", "target_ref")}
                    | {"intent_ref": refs["intent"]},
                ),
                ("result", outcome),
            ):
                marker_key = digest({"attempt_digest": attempt, "sequence": index, "event": kind})
                marker = records[("ledger", f"recovery-events/{marker_key}.json")][1]
                canonical = records[("ledger", f"receipts/{marker['receipt_digest']}.json")][1]
                require(canonical["value"] == expected)
        terminal = records.get(("ledger", f"recovery-terminal/{attempt}.json"))
        if terminal is not None:
            receipt = records[("ledger", f"receipts/{terminal[1]['receipt_digest']}.json")][1]
            if receipt["proof"] is not None:
                require(receipt["proof"] == result)
    require(
        all(path in claimed or any(path in slots for slots in attached.values()) for path in roles)
    )
