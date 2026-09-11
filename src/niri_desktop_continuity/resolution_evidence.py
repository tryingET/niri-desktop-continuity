"""Closed owner observation packet and finite settlement predicate; no native producer."""

from datetime import datetime
from uuid import UUID

from .model import digest
from .recovery_protocol import fields, hexkey, require
from .resolution_candidate import lifetime

EVIDENCE = "desktop-continuity.settlement-evidence.v1"
PACKET = "desktop-continuity.settlement-packet.v1"
PROTOCOL = "desktop-continuity.settlement-observer.v1"


def integer(value, maximum=2**63 - 1):
    require(type(value) is int and 0 <= value <= maximum)


def uuid(value):
    require(type(value) is str and str(UUID(value)) == value)


def sequence(value, maximum):
    require(type(value) is list and len(value) <= maximum)
    return value


def attachment(value):
    schema = value.get("schema")
    if schema in {"desktop-continuity.process-names.v1", "desktop-continuity.process-names.v2"}:
        scoped = schema == "desktop-continuity.process-names.v2"
        fields(
            value,
            ("schema", "tasks") + (("discovery_scope", "stability_scope") if scoped else ()),
        )
        if scoped:
            require(value["discovery_scope"] == "all-visible-same-account-tasks")
            require(value["stability_scope"] == "candidate-and-protected-cohort")
        for task in sequence(value["tasks"], 100000):
            integer(task)
            require(task > 0)
        require(value["tasks"] == sorted(set(value["tasks"])))
    elif schema == "desktop-continuity.process-rows.v1":
        fields(value, ("schema", "rows"))
        for row in sequence(value["rows"], 100000):
            fields(
                row,
                (
                    "boot_id",
                    "pid",
                    "tgid",
                    "start_ticks",
                    "ppid",
                    "pgid",
                    "sid",
                    "uid",
                    "image_digest",
                    "pid_namespace_inode",
                ),
            )
            uuid(row["boot_id"])
            hexkey(row["image_digest"])
            for key in set(row) - {"boot_id", "image_digest"}:
                integer(row[key])
            require(row["pid"] > 0 and row["tgid"] > 0 and row["start_ticks"] > 0)
        require([r["pid"] for r in value["rows"]] == sorted({r["pid"] for r in value["rows"]}))
        require(len({r["tgid"] for r in value["rows"]}) <= 20000)
    elif schema == "desktop-continuity.candidate-discovery.v1":
        fields(value, ("schema", "rows", "contract"))
        require(value["contract"] == "owner-reviewed-possible-writer-and-recovery-executor-v1")
        for row in sequence(value["rows"], 100000):
            fields(row, ("process_ref", "classification", "association_ref"))
            hexkey(row["process_ref"])
            require(
                row["classification"]
                in (
                    "noncandidate",
                    "observer",
                    "controller",
                    "protected",
                    "possible-writer",
                    "recovery-executor",
                    "unknown",
                )
            )
            if row["association_ref"] is not None:
                hexkey(row["association_ref"])
        require(
            [r["process_ref"] for r in value["rows"]]
            == sorted({r["process_ref"] for r in value["rows"]})
        )
    elif schema == "desktop-continuity.writer-association.v1":
        fields(
            value,
            (
                "schema",
                "process_ref",
                "session_ref",
                "saved_device",
                "saved_inode",
                "disposition",
                "birth_digest",
            ),
        )
        for key in ("process_ref", "session_ref", "birth_digest"):
            hexkey(value[key])
        for key in ("saved_device", "saved_inode"):
            integer(value[key])
        require(value["disposition"] in ("unrelated", "selected", "descendant", "unknown"))
    else:
        require(False)


def fingerprint(evidence):
    return digest(
        {
            key: evidence[key]
            for key in (
                "mode",
                "current_identity",
                "focus_digest",
                "protected_digest",
                "writers",
                "tickets",
                "saved_files",
                "source_contract_digest",
                "graph_digest",
                "candidate_digest",
            )
        }
    )


def validate(value, candidate, graph, objects, *, fresh=True):
    fields(
        value,
        (
            "schema",
            "candidate_digest",
            "graph_digest",
            "observed_at",
            "expires_at",
            "observer_digest",
            "boot_before",
            "boot_after",
            "current_identity",
            "focus_digest",
            "protected_digest",
            "process_scan",
            "writers",
            "tickets",
            "saved_files",
            "source_contract_digest",
            "mode",
            "verdict",
            "blockers",
        ),
    )
    require(value["schema"] == EVIDENCE)
    lifetime({"created_at": value["observed_at"], "expires_at": value["expires_at"]}, fresh=fresh)
    require(
        datetime.fromisoformat(value["expires_at"])
        <= datetime.fromisoformat(candidate["expires_at"])
    )
    require(
        value["candidate_digest"] == digest(candidate) and value["graph_digest"] == digest(graph)
    )
    require(value["observer_digest"] == digest(candidate["observer"]))
    require(value["source_contract_digest"] == digest(candidate["source_contract"]))
    identity = value["current_identity"]
    fields(identity, ("boot_id", "niri_socket", "socket_device", "socket_inode"))
    uuid(identity["boot_id"])
    require(type(identity["niri_socket"]) is str and 1 <= len(identity["niri_socket"]) <= 4096)
    for key in ("socket_device", "socket_inode"):
        integer(identity[key])
    for key in ("boot_before", "boot_after"):
        uuid(value[key])
    for key in ("focus_digest", "protected_digest"):
        hexkey(value[key])
    scan = value["process_scan"]
    fields(
        scan,
        (
            "rows_ref",
            "names_before_ref",
            "names_after_ref",
            "attribution_ref",
            "complete",
            "escaped_cohort",
        ),
    )
    require(type(scan["complete"]) is bool)
    require(scan["escaped_cohort"] in ("excluded-by-boot", "not-created", "unproved"))
    loaded = {}
    for key in ("rows_ref", "names_before_ref", "names_after_ref", "attribution_ref"):
        loaded[key] = objects.get(hexkey(scan[key]))
        attachment(loaded[key])
    require(loaded["rows_ref"]["schema"] == "desktop-continuity.process-rows.v1")
    require(loaded["attribution_ref"]["schema"] == "desktop-continuity.candidate-discovery.v1")
    before, after = (loaded[k] for k in ("names_before_ref", "names_after_ref"))
    require(
        before["schema"] == after["schema"]
        and before["schema"]
        in {"desktop-continuity.process-names.v1", "desktop-continuity.process-names.v2"}
    )
    # V1 still asserts full-set stability. V2 asserts full reviewed discovery
    # with candidate/protected stability, not unrelated task/FD quiescence.
    # Scope literals were checked by attachment; mixed versions cannot agree.
    rows = loaded["rows_ref"]["rows"]
    discovery = loaded["attribution_ref"]["rows"]
    if before["schema"] == "desktop-continuity.process-names.v2":
        require(all(r["classification"] != "noncandidate" for r in discovery))
    require({digest(r) for r in rows} == {r["process_ref"] for r in discovery})
    require(all(row["boot_id"] == identity["boot_id"] for row in rows))
    blockers = set()
    if (
        not scan["complete"]
        or loaded["names_before_ref"] != loaded["names_after_ref"]
        or loaded["names_before_ref"]["tasks"] != [r["pid"] for r in rows]
    ):
        blockers.add("census-incomplete")
    require(value["boot_before"] == value["boot_after"] == identity["boot_id"])
    writers = sequence(value["writers"], 256)
    require(writers == sorted(set(writers)))
    associations = {}
    writer_files = set()
    for key in writers:
        item = objects.get(hexkey(key))
        attachment(item)
        require(item["schema"] == "desktop-continuity.writer-association.v1")
        require(item["process_ref"] in {digest(r) for r in rows})
        require(item["birth_digest"] == item["process_ref"])
        require(item["process_ref"] not in associations)
        associations[item["process_ref"]] = key
        writer_files.add((item["saved_device"], item["saved_inode"]))
        if item["disposition"] != "unrelated" or item["session_ref"] in candidate["selected_refs"]:
            blockers.add("writer-conflict")
    relevant = set()
    for item in discovery:
        role = item["classification"]
        if role in ("unknown", "recovery-executor"):
            blockers.add("capability-unknown")
        if role == "possible-writer":
            relevant.add(item["process_ref"])
            if (
                associations.get(item["process_ref"]) != item["association_ref"]
                or item["association_ref"] is None
            ):
                blockers.add("capability-unknown")
        else:
            require(item["association_ref"] is None)
    require(set(associations) <= relevant)
    from .resolution_graph import worker_history

    history = worker_history(candidate)
    require(
        sum(
            r["root"] == "worker" and r["object_digest"] == digest(history["manifest"])
            for r in graph["files"]
        )
        == 1
    )
    saved = sequence(value["saved_files"], 256)
    require([r["session_ref"] for r in saved] == candidate["selected_refs"])
    for item in saved:
        fields(
            item,
            (
                "session_ref",
                "device",
                "inode",
                "bytes",
                "sha256",
                "original_prefix_bytes",
                "original_prefix_sha256",
                "metadata_ref",
                "prefix_preserved",
            ),
        )
        for key in ("session_ref", "sha256", "original_prefix_sha256", "metadata_ref"):
            hexkey(item[key])
        for key in ("device", "inode", "bytes", "original_prefix_bytes"):
            integer(item[key])
        original = next(
            f for f in history["saved_files"] if f["session_ref"] == item["session_ref"]
        )
        require(all(item[k] == original[k] for k in ("device", "inode", "metadata_ref")))
        require(item["original_prefix_bytes"] == original["prefix_bytes"])
        require(item["original_prefix_sha256"] == original["prefix_sha256"])
        require(type(item["prefix_preserved"]) is bool)
        if not item["prefix_preserved"] or item["bytes"] < item["original_prefix_bytes"]:
            blockers.add("saved-prefix-changed")
    # Native identity overrides a claimed unrelated ref/disposition (e.g. a hardlink
    # or selected-file descriptor alongside argv naming an unrelated session).
    if writer_files & {(item["device"], item["inode"]) for item in saved}:
        blockers.add("writer-conflict")
    tickets = sequence(value["tickets"], 256)
    for ticket in tickets:
        fields(
            ticket,
            (
                "request_ref",
                "request_sha256",
                "claim_ref",
                "claim_sha256",
                "boot_id",
                "pid",
                "start_ticks",
                "expires_at",
                "disposition",
            ),
        )
        for key in ("request_ref", "request_sha256", "claim_ref", "claim_sha256"):
            hexkey(ticket[key])
        uuid(ticket["boot_id"])
        integer(ticket["pid"])
        integer(ticket["start_ticks"])
        require(ticket["pid"] > 1 and ticket["start_ticks"] > 0)
        require(ticket["disposition"] in ("old-boot", "absent", "live", "unknown"))
        if ticket["disposition"] in ("live", "unknown"):
            blockers.add("ticket-damaged")
    require(
        [{k: v for k, v in t.items() if k != "disposition"} for t in tickets] == history["tickets"]
    )
    old_boot = history["old_boot"]
    if graph["prefix"] == "direct-first-ack-v1":
        mode = (
            "new-boot-direct"
            if identity["boot_id"] != old_boot
            else "historical-same-boot-unproved"
        )
        require(len(tickets) == 1)
        ticket = tickets[0]
        require(ticket["boot_id"] == old_boot)
        for ref, hashkey in (("request_ref", "request_sha256"), ("claim_ref", "claim_sha256")):
            matches = [
                r
                for r in graph["files"]
                if r["root"] == "worker" and r["object_digest"] == ticket[ref]
            ]
            require(len(matches) == 1 and matches[0]["raw_sha256"] == ticket[hashkey])
        if mode != "new-boot-direct":
            blockers.add("historical-same-boot-unproved")
        elif ticket["disposition"] != "old-boot" or scan["escaped_cohort"] != "excluded-by-boot":
            blockers.add("ticket-damaged")
        if datetime.fromisoformat(ticket["expires_at"]) >= datetime.fromisoformat(
            value["observed_at"]
        ):
            blockers.add("ticket-damaged")
    else:
        mode = "same-boot-zero-permit"
        require(not tickets and identity["boot_id"] == old_boot)
        if scan["escaped_cohort"] != "not-created":
            blockers.add("capability-unknown")
    require(value["mode"] == mode)
    require(value["blockers"] == sorted(blockers))
    require(value["verdict"] == ("blocked" if blockers else "settled"))
    return not blockers


def persist_packet(packet, candidate, graph, objects):
    fields(packet, ("schema", "evidence", "attachments"))
    require(packet["schema"] == PACKET)
    attachments = sequence(packet["attachments"], 512)
    keys = []
    for item in attachments:
        fields(item, ("digest", "value"))
        require(digest(item["value"]) == hexkey(item["digest"]))
        attachment(item["value"])
        keys.append(item["digest"])
    require(keys == sorted(set(keys)))

    # Validate all packet data before persisting any observer-provided bytes.
    class PacketObjects:
        def get(self, key):
            require(key in keys)
            return next(item["value"] for item in attachments if item["digest"] == key)

    validate(packet["evidence"], candidate, graph, PacketObjects())
    evidence = packet["evidence"]
    expected = set(evidence["writers"]) | {
        v for k, v in evidence["process_scan"].items() if k.endswith("_ref")
    }
    require(set(keys) == expected)
    for item in attachments:
        objects.put(item["value"])
    return objects.put(evidence)
