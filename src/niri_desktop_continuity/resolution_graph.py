"""Three bounded history gates with separate retained-owner and prospective codecs."""

from __future__ import annotations

from pathlib import Path

from . import resolution_worker_history as owner_history
from .model import digest
from .recovery_ledger import Ledger, bounded_names
from .recovery_protocol import ADDITIVE, decode, fields, hexkey, require
from .resolution_candidate import profile_bytes
from .resolution_io import Objects, check_root, names, raw, retained_bytes, sha
from .resolution_worker_history_fixture import WORKER, worker_value  # noqa: F401
from .resolution_worker_history_fixture import prefix as fixture_prefix

GRAPH = "desktop-continuity.resolution-graph.v1"
WORKER_KINDS = ("objects", "attempts", "events", "children", "requests", "started", "finished")


def coordinator_digest():
    root = Path(__file__).parent
    return digest({p.name: sha(p.read_bytes()) for p in sorted(root.glob("*.py"))})


def references(value):
    if type(value) is str:
        return (
            {value} if len(value) == 64 and all(c in "0123456789abcdef" for c in value) else set()
        )
    if type(value) is list:
        return set().union(*(references(v) for v in value)) if value else set()
    if type(value) is dict:
        return references(list(value.values()))
    return set()


def scan(candidate):
    """Read the entire bounded union; a present catalog exclusively selects the owner codec."""
    records, byte_count = {}, 0
    for root_name in ("ledger", "worker"):
        check_root(candidate[root_name])
        root = Path(candidate[root_name]["path"])
        actual = root_name == "worker" and (root / "catalog.json").exists()
        if actual:
            paths = owner_history.paths(root)
        else:
            kinds = (
                (
                    "plans",
                    "approvals",
                    "receipts",
                    "snapshots",
                    "recovery-prepared",
                    "recovery-ready",
                    "recovery-terminal",
                    "recovery-events",
                )
                if root_name == "ledger"
                else WORKER_KINDS
            )
            if root_name == "worker":
                require(all(p.name in WORKER_KINDS for p in root.iterdir()))
            paths = (
                f"{kind}/{key}.json"
                for kind in kinds
                for key in names(
                    root / kind,
                    256
                    if kind in ("attempts", "recovery-prepared")
                    else 512
                    if root_name == "worker"
                    and kind in ("events", "children", "requests", "started")
                    else 4096,
                )
            )
        for path in paths:
            require(len(records) < 4096)
            data = raw(root / path)
            byte_count += len(data)
            require(byte_count <= 8 * 1024 * 1024)
            value = decode(data)
            require(type(value) is dict)
            if root_name == "worker" and not actual:
                worker_value(path.split("/")[0], Path(path).stem, value)
            elif root_name == "ledger" and not path.startswith("recovery-"):
                require(digest(value) == Path(path).stem)
            records[(root_name, path)] = (data, value)
    if ("worker", "catalog.json") in records:
        owner_history.inventory(records, Path(candidate["worker"]["path"]), candidate)
    else:
        worker_attempts = {
            Path(path).stem
            for root, path in records
            if root == "worker" and path.startswith("attempts/")
        }
        for (root, _), (_, value) in records.items():
            if root == "worker" and "kind" in value and value["kind"] != "manifest":
                require(value["attempt_digest"] in worker_attempts)
    for (root, path), (_, value) in records.items():
        if root == "ledger" and path.startswith("receipts/") and "event" in value:
            fields(value, ("schema", "attempt_digest", "event", "value"))
            require(value["event"] in ("intent", "result"))
            index = digest(
                {
                    "attempt_digest": hexkey(value["attempt_digest"]),
                    "sequence": value["value"]["sequence"],
                    "event": value["event"],
                }
            )
            marker = ("ledger", f"recovery-events/{index}.json")
            require(marker in records and records[marker][1] == {"receipt_digest": Path(path).stem})
        if root != "ledger" or not path.startswith("recovery-events/"):
            continue
        fields(value, ("receipt_digest",))
        receipt_key = hexkey(value["receipt_digest"])
        require(("ledger", f"receipts/{receipt_key}.json") in records)
        record = records[("ledger", f"receipts/{receipt_key}.json")][1]
        fields(record, ("schema", "attempt_digest", "event", "value"))
        require(record["event"] in ("intent", "result"))
        sequence = record["value"]["sequence"]
        require(type(sequence) is int and 0 <= sequence < 256)
        require(
            Path(path).stem
            == digest(
                {
                    "attempt_digest": hexkey(record["attempt_digest"]),
                    "sequence": sequence,
                    "event": record["event"],
                }
            )
        )
        require(("ledger", f"recovery-prepared/{record['attempt_digest']}.json") in records)
    return records


def historical(candidate):
    old = profile_bytes(candidate["old_profile"])
    ledger = Ledger(old, read_only=True)
    attempt = candidate["attempt_digest"]
    require(ledger.attempt_status(attempt) == "indeterminate")
    prepared = ledger.store.recovery_marker("recovery-prepared", attempt)
    plan = ledger.store.get("plans", prepared["plan_digest"])
    require(plan["recovery"]["schema"] == ADDITIVE)
    observed = plan["recovery"]["observation"]
    require(observed["saved_set"] == candidate["saved_set"])
    selected = observed["saved_selection"]
    require(not selected["unresolved_refs"])
    require(
        sorted(selected["missing_refs"] + selected["present_refs"]) == candidate["selected_refs"]
    )
    used = Path(prepared["cli_used_path"])
    require(used.name == f"{attempt}.json" and used.parent.name == "used")
    return ledger, plan, used


def prefix(candidate, records, ledger, plan):
    if ("worker", "catalog.json") in records:
        return owner_history.history(candidate, records, ledger, plan)
    fixture_prefix(candidate, records, ledger, plan)
    rows = [
        (data, v)
        for (root, _), (data, v) in records.items()
        if root == "worker" and v.get("attempt_digest") == candidate["attempt_digest"]
    ]
    manifest = next(v for _, v in rows if v.get("kind") == "manifest")
    tickets = []
    if candidate["source_contract"]["prefix_rule"] == "direct-first-ack-v1":
        request_raw, request = next((data, v) for data, v in rows if v.get("kind") == "request")
        claim_raw, claim = next((data, v) for data, v in rows if v.get("kind") == "started")
        tickets = [
            {
                "request_ref": digest(request),
                "request_sha256": sha(request_raw),
                "claim_ref": digest(claim),
                "claim_sha256": sha(claim_raw),
                **{k: claim["data"][k] for k in ("boot_id", "pid", "start_ticks")},
                "expires_at": request["data"]["expires_at"],
            }
        ]
    return {
        "manifest": manifest,
        "saved_files": manifest["data"]["saved_files"],
        "tickets": tickets,
        "old_boot": plan["source_identity"]["boot_id"],
    }, set()


def worker_history(candidate):
    """Validated ORIGINAL manifest, normalized saved_files/tickets, and original old_boot.

    Ticket refs are semantic object digests; their raw hashes bind original bytes,
    irrespective of namespace filenames or JSON whitespace. No state is persisted.
    """
    ledger, plan, _ = historical(candidate)
    return prefix(candidate, scan(candidate), ledger, plan)[0]


def build(candidate, baseline=None):
    ledger, plan, used = historical(candidate)
    records = scan(candidate)
    terminal = ledger.store.recovery_marker("recovery-terminal", candidate["attempt_digest"])
    for (root, path), (_, record) in records.items():
        if (
            root == "ledger"
            and path.startswith("receipts/")
            and record.get("attempt_digest") == candidate["attempt_digest"]
        ):
            key = Path(path).stem
            if "event" in record:
                require(record["event"] in ("intent", "result"))
                event_key = digest(
                    {
                        "attempt_digest": candidate["attempt_digest"],
                        "sequence": record["value"]["sequence"],
                        "event": record["event"],
                    }
                )
                require(
                    records[("ledger", f"recovery-events/{event_key}.json")][1]
                    == {"receipt_digest": key}
                )
            else:
                require(key == terminal["receipt_digest"])
    _, owner_slots = prefix(candidate, records, ledger, plan)
    actual = ("worker", "catalog.json") in records
    known = {candidate["attempt_digest"]}
    attributable = set(known)
    selected = set(owner_slots)
    # For the actual codec, ONLY explicit owner edges select worker records. Shared
    # saved references, file hashes and image pins must never reverse-link later work.
    while True:
        before = len(selected), len(known), len(attributable)
        for slot, (_, value) in records.items():
            if actual and slot[0] == "worker":
                continue
            key = Path(slot[1]).stem
            refs = references(value)
            if key in known or refs & attributable:
                selected.add(slot)
                known.update(refs)
                if slot[1].startswith(("recovery-events/", "receipts/")) or (
                    slot[0] == "worker" and value.get("kind") not in (None, "manifest")
                ):
                    attributable.add(key)
                    if value.get("event") == "intent":
                        attributable.add(value["value"]["intent_ref"])
        if before == (len(selected), len(known), len(attributable)):
            break
    if baseline is None and not actual:
        require(
            all(
                slot in selected or value.get("kind") == "manifest"
                for slot, (_, value) in records.items()
                if slot[0] == "worker"
            )
        )
    if baseline is not None:
        for item in baseline["files"]:
            slot = (item["root"], item["relative_path"])
            if slot[0] in ("ledger", "worker"):
                require(slot in records)
                selected.add(slot)
    files = []
    for root, path in sorted(selected):
        data, value = records[(root, path)]
        files.append(
            {
                "root": root,
                "relative_path": path,
                "bytes": len(data),
                "raw_sha256": sha(data),
                "object_digest": digest(value),
            }
        )
    data = raw(used)
    files.append(
        {
            "root": "original-cli",
            "relative_path": f"used/{used.name}",
            "bytes": len(data),
            "raw_sha256": sha(data),
            "object_digest": digest(decode(data)),
        }
    )
    archives = [candidate[k] for k in ("old_profile", "old_config", "new_config")]
    archives += candidate["source_contract"]["original_files"] + [
        candidate["source_contract"]["review_artifact"]
    ]
    for item in sorted({v["sha256"]: v for v in archives}.values(), key=lambda v: v["sha256"]):
        data = retained_bytes(item)
        files.append(
            {
                "root": "archive",
                "relative_path": f"{item['sha256']}.bin",
                "bytes": len(data),
                "raw_sha256": sha(data),
                "object_digest": None,
            }
        )
    absences = []
    for sequence in range(256):
        for event in ("intent", "result"):
            key = digest(
                {
                    "attempt_digest": candidate["attempt_digest"],
                    "sequence": sequence,
                    "event": event,
                }
            )
            path = f"recovery-events/{key}.json"
            if ("ledger", path) not in records:
                absences.append({"root": "ledger", "relative_path": path})
    absent = f"finished/{candidate['attempt_digest']}.json"
    require(("worker", absent) not in records)
    absences.append({"root": "worker", "relative_path": absent})
    return {
        "schema": GRAPH,
        "attempt_digest": candidate["attempt_digest"],
        "original_profile_digest": digest(profile_bytes(candidate["old_profile"])),
        "ledger": candidate["ledger"],
        "worker": candidate["worker"],
        "original_cli_root": str(used.parent.parent),
        "files": files,
        "absences": absences,
        "prefix": candidate["source_contract"]["prefix_rule"],
    }


def initial(candidate):
    objects = Objects(candidate["ledger"]["path"])
    require(not any(objects.markers().values()))
    require(bounded_names(objects.root / "recovery-prepared") == {candidate["attempt_digest"]})
    for kind in ("recovery-ready", "recovery-terminal"):
        require(bounded_names(objects.root / kind) <= {candidate["attempt_digest"]})
    require(
        set(names(Path(candidate["worker"]["path"]) / "attempts")) == {candidate["attempt_digest"]}
    )
    return build(candidate)


def unchanged(candidate, graph, *, durable=False):
    fields(
        graph,
        (
            "schema",
            "attempt_digest",
            "original_profile_digest",
            "ledger",
            "worker",
            "original_cli_root",
            "files",
            "absences",
            "prefix",
        ),
    )
    require(graph["schema"] == GRAPH)
    if not durable:
        require(
            bounded_names(Path(candidate["ledger"]["path"]) / "recovery-prepared")
            == {candidate["attempt_digest"]}
        )
        require(
            set(names(Path(candidate["worker"]["path"]) / "attempts"))
            == {candidate["attempt_digest"]}
        )
    require(build(candidate, baseline=graph) == graph)
    if durable:
        current = Ledger(profile_bytes(candidate["new_profile"]), read_only=True)
        prepared = bounded_names(current.store.root / "recovery-prepared")
        for kind in ("recovery-ready", "recovery-terminal"):
            require(bounded_names(current.store.root / kind) <= prepared)
        for key in prepared - {candidate["attempt_digest"]}:
            try:
                current.attempt_status(key)
            except FileNotFoundError:
                pass
