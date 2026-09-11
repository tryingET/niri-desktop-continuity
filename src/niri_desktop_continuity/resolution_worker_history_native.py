"""Closed data shapes emitted by current grouped census/Journal.bind/Machine.verify.

This module validates retained data, not native truth or current process liveness.
"""

from .model import digest
from .recovery_additive import DIMENSIONS, proof
from .recovery_protocol import fields, hexkey, require
from .resolution_worker_history_schema import absolute, argv, host, number, selection, text


def process(value):
    require(type(value) is dict and "ppid" in value)
    host({k: v for k, v in value.items() if k != "ppid"})
    number(value["ppid"], 1)


def binding(value):
    fields(value, ("process", "host", "window", "tty", "surface", "pi_bin", "bootstrap", "bus"))
    process(value["process"])
    host(value["host"])
    window = value["window"]
    fields(window, ("id", "pid", "app_id", "workspace_id", "is_floating"))
    for key in ("id", "pid", "workspace_id"):
        number(window[key])
    text(window["app_id"])
    require(type(window["is_floating"]) is bool and window["pid"] == value["host"]["pid"])
    bus = value["bus"]
    fields(bus, ("name", "pid", "daemon"))
    text(bus["name"])
    require(bus["name"].startswith(":") and len(bus["name"]) <= 255)
    require(type(bus["pid"]) is int and bus["pid"] == value["host"]["pid"])
    require(type(bus["daemon"]) is str and len(bus["daemon"]) == 32)
    require(all(c in "0123456789abcdef" for c in bus["daemon"]))
    tty = value["tty"]
    require(type(tty) is list and len(tty) == 4)
    absolute(tty[0])
    require(tty[0].startswith("/dev/pts/"))
    for v in tty[1:]:
        number(v)
    text(value["surface"])
    require(0 < int(value["surface"], 0) < 2**64)
    absolute(value["pi_bin"])
    ticket = value["bootstrap"]
    if ticket.get("kind") == "observed-exact-native-argv":
        fields(ticket, ("kind", "argv"))
        require(type(ticket["argv"]) is list and 1 <= len(ticket["argv"]) <= 32)
        for arg in ticket["argv"]:
            text(arg)
    else:
        from .resolution_worker_history_schema import record

        fields(ticket, ("kind", "request", "claim"))
        require(ticket["kind"] == "retained-exec-ticket")
        request, claim = ticket["request"], ticket["claim"]
        record("bootstraps/" + "0" * 64 + ".json", request)
        record("bootstraps/" + "0" * 64 + ".started.json", claim)
        require(claim["argv"] == argv(request))
        require(
            all(
                claim[k] == value["process"][k]
                for k in ("pid", "ppid", "start_ticks", "boot_id", "cwd")
            )
        )
        require(value["process"]["exe_sha256"] == request["node"]["sha256"])
        require(value["process"]["exe"] == request["node"]["path"])
        require(value["pi_bin"] == request["pi"]["path"])
    require(value["host"]["boot_id"] == value["process"]["boot_id"])
    require(value["process"]["pid"] != value["host"]["pid"])


def native(value):
    fields(value, ("file", "id", "cwd", "parents", "binding", "process"))
    selection({k: value[k] for k in ("file", "id", "cwd")})
    require(type(value["parents"]) is list and len(value["parents"]) <= 256)
    for parent in value["parents"]:
        absolute(parent)
    require(len(value["parents"]) == len(set(value["parents"])))
    process(value["process"])
    binding(value["binding"])
    require(value["process"] == value["binding"]["process"])
    require(value["cwd"] == value["process"]["cwd"])
    ticket = value["binding"]["bootstrap"]
    if ticket["kind"] == "retained-exec-ticket":
        request = ticket["request"]
        require(all(request[k] == value[k] for k in ("file", "id", "cwd")))
        require(
            request["session_ref"]
            == digest({"kind": "pi", **{k: value[k] for k in ("file", "id", "cwd")}})
        )


def extra_object(value):
    """Recognized finite shapes only. Their existence still requires a provenance root."""
    if set(value) == {"attempt", "session_ref", "target"}:
        hexkey(value["attempt"])
        hexkey(value["session_ref"])
        binding(value["target"])
        return "dispatch"
    if set(value) == {"attempt", "session_ref", "native"}:
        hexkey(value["attempt"])
        hexkey(value["session_ref"])
        native(value["native"])
        return "binding"
    if set(value) == {"dimension", "proved"}:
        require(value["dimension"] in DIMENSIONS and type(value["proved"]) is bool)
        return "dimension"
    if set(value) == {"reference", "native", "saved_prefix_preserved"}:
        hexkey(value["reference"])
        native(value["native"])
        require(type(value["saved_prefix_preserved"]) is bool)
        return "verification"
    if set(value) == {"reference", "matched"}:
        hexkey(value["reference"])
        require(value["matched"] is False)
        return "verification"
    if set(value) == {"dimensions", "native", "interrupted", "unresolved_children"}:
        proof(value, [r["session_ref"] for r in value["native"]])
        return "proof"
    require(False)


def finished(value):
    fields(value, ("complete", "proof_ref", "bindings", "events", "children", "manifest_ref"))
    require(type(value["complete"]) is bool)
    hexkey(value["proof_ref"])
    hexkey(value["manifest_ref"])
    require(type(value["bindings"]) is dict and len(value["bindings"]) <= 256)
    for ref, row in value["bindings"].items():
        hexkey(ref)
        native(row)
    require(type(value["children"]) is dict and len(value["children"]) <= 256)
    for ref, pid in value["children"].items():
        hexkey(ref)
        number(pid, 2)
    require(type(value["events"]) is list and len(value["events"]) <= 256)
    for event in value["events"]:
        fields(event, ("intent", "result", "ack"))
        for ref in event.values():
            hexkey(ref)
