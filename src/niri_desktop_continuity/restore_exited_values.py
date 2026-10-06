"""Closed v3 values. Historical proof decoding never performs a native observation."""

import math
import os

from . import restore_state as states
from .model import digest
from .restore_reader import pin_valid, same
from .store import HEX

SCHEMA = "desktop-continuity.restore-disposition.v3"
FAMILY = "associated-shell-protected-dimensions-interrupted"
BRANCH = "exact-process-exited-and-window-absent"
LEGACY_METHOD = "native-niri-continuing-peer-pidfd-esrch.v1"
SELF_V1_METHOD = "native-niri-continuing-peer-procfs-self-pidfd-esrch.v1"
METHOD = "native-niri-continuing-peer-procfs-self-pidfd-esrch.v2"
ACCEPT = "operator-accepted-partial"
PLATFORM = {
    "schema": "desktop-continuity.native-niri-continuity-trust.v1",
    "assumption": "same-lifetime-native-niri-endpoint-and-pid-scope",
    "scope": "exact-recorded-associated-shell-only",
    "basis": "operator-accepted-trust-not-historical-measurement",
    "server_continuity": "original-process-served-retained-endpoint-throughout",
    "indirection": "no-serving-handover-namespace-changing-proxy-or-pid-translation",
    "historical_process_scope": "trusted-native-single-host",
    "historical_executable": "not-attested",
}
LIMITS = {
    "acceptance": ACCEPT,
    "historical_completion": "unproved",
    "historical_preservation": "unproved",
    "historical_association": "recorded",
    "historical_layout": "two-observed-actions-incomplete",
    "outcome": "unresolved",
    "native_session": "not-proved",
    "retry_authorized": False,
    "desktop_effects": [],
    "coverage": "exact-legacy-witness-continuing-native-peer-exited-slot-current-topology-only",
}
MAX = 2**63 - 1
# Omitted comparison is distinct from an explicitly recorded JSON null.
_NO_DIRECT_VERSION = object()


def integer(value, low=0, high=MAX):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("invalid bounded integer")
    return value


def pid(value):
    return integer(value, 1, 2147483647)


def text(value, *, empty=False):
    if not isinstance(value, str) or not int(not empty) <= len(value) <= 4096 or "\0" in value:
        raise ValueError("invalid bounded string")
    return value


def key(value):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError("invalid semantic digest")


def path(value):
    text(value)
    if not os.path.isabs(value) or os.path.normpath(value) != value or value.startswith("//"):
        raise ValueError("normalized absolute path required")
    return value


def inode(value):
    states.fields(value, "device inode")
    for v in value.values():
        integer(v)


def process(value, boot=None):
    states.fields(value, "boot_id pid start_ticks")
    text(value["boot_id"])
    pid(value["pid"])
    integer(value["start_ticks"], 1)
    if boot is not None and value["boot_id"] != boot:
        raise ValueError("foreign process boot")


def image(value):
    states.fields(value, "device inode sha256")
    inode({k: value[k] for k in ("device", "inode")})
    key(value["sha256"])


def identity(value):
    states.fields(value, "boot_id niri_socket socket_device socket_inode")
    text(value["boot_id"])
    path(value["niri_socket"])
    integer(value["socket_device"])
    integer(value["socket_inode"])


def filepin(value, *, raw=False):
    states.fields(value, "path directory device inode sha256 length" + ("" if raw else " digest"))
    pin_valid(value)
    path(value["path"])
    inode(value["directory"])
    for k in ("device", "inode", "length"):
        integer(value[k])
    integer(value["length"], 0, 16 * 1024**2)


def metadata(value, depth=0, budget=None):
    budget = [65536] if budget is None else budget
    budget[0] -= 1
    if depth > 8 or budget[0] < 0:
        raise ValueError("metadata exceeds bound")
    if value is None or type(value) is bool:
        return
    if type(value) in (int, float):
        if abs(value) > MAX or not math.isfinite(value):
            raise ValueError("metadata number exceeds bound")
        return
    if isinstance(value, str):
        text(value, empty=True)
        return
    if isinstance(value, (dict, list)) and len(value) <= 512:
        for child in [*value.keys(), *value.values()] if isinstance(value, dict) else value:
            metadata(child, depth + 1, budget)
        return
    raise ValueError("invalid bounded metadata")


def state(value):
    metadata(value)
    decoded = states.decode(value)
    if not same(states.record(decoded), value):
        raise ValueError("noncanonical State")
    for w in value["windows"]:
        pid(w["pid"])
    return decoded


def version(source, direct=_NO_DIRECT_VERSION):
    value = source.get("niri_version")
    states.fields(value, "compositor cli")
    text(value["compositor"])
    text(value["cli"])
    if direct is not _NO_DIRECT_VERSION and text(direct) != value["compositor"]:
        raise ValueError("authenticated compositor version differs")
    return value["compositor"]


def source_valid(source, expected_identity):
    identity(source["identity"])
    if (
        not same(source["identity"], expected_identity)
        or source.get("inventory_complete") is not True
    ):
        raise ValueError("source identity or inventory incomplete")
    version(source)
    rows = source.get("process_inventory")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20000:
        raise ValueError("bounded original inventory required")
    seen = set()
    for row in rows:
        states.fields(row, "cgroup comm pid ppid start_ticks")
        pid(row["pid"])
        integer(row["ppid"], 0, 2147483647)
        integer(row["start_ticks"], 1)
        text(row["comm"], empty=True)
        if row["cgroup"] is not None:
            text(row["cgroup"], empty=True)
        if row["pid"] in seen:
            raise ValueError("duplicate inventory PID")
        seen.add(row["pid"])


def inventory(source, peer):
    process(peer, source["identity"]["boot_id"])
    rows = [
        r
        for r in source["process_inventory"]
        if r["pid"] == peer["pid"] and r["start_ticks"] == peer["start_ticks"]
    ]
    if len(rows) != 1:
        raise ValueError("authenticated peer lacks unique original inventory tuple")
    return {"snapshot": digest(source), "row_digest": digest(rows[0])}


def caller(value, boot, absent):
    states.fields(value, "process ancestry")
    process(value["process"], boot)
    rows = value["ancestry"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
        raise ValueError("bounded caller ancestry required")
    expected, seen = value["process"]["pid"], set()
    for row in rows:
        states.fields(row, "process ppid")
        process(row["process"], boot)
        p = row["process"]["pid"]
        pid(row["ppid"])
        if p != expected or p in seen or p in (1, absent):
            raise ValueError("unproved or overlapping caller ancestry")
        seen.add(p)
        expected = row["ppid"]
    if expected != 1 or not same(rows[0]["process"], value["process"]):
        raise ValueError("caller ancestry must end at namespace init")


def current(value, source, launched, associated):
    states.fields(
        value,
        "method state owned_window_ids protected_window_ids processes peer scope absence caller",
    )
    if value["method"] not in (LEGACY_METHOD, SELF_V1_METHOD, METHOD) or not same(
        value["owned_window_ids"], []
    ):
        raise ValueError("invalid exited-host current method/partition")
    decoded = state(value["state"])
    boot, old = source["identity"]["boot_id"], launched["pid"]
    process(launched, boot)
    if associated in decoded[0] or any(w["pid"] == old for w in decoded[0].values()):
        raise ValueError("old associated ID or PID still present")
    if not same(value["protected_window_ids"], sorted(decoded[0])):
        raise ValueError("every present window must be protected")
    pins = value["processes"]
    if not isinstance(pins, list) or len(pins) > 512:
        raise ValueError("invalid protected process cohort")
    for p in pins:
        process(p, boot)
    if not same([p["pid"] for p in pins], sorted({w["pid"] for w in decoded[0].values()})):
        raise ValueError("incomplete protected process pins")
    peer = value["peer"]
    states.fields(peer, "process credentials endpoint inventory version running_image")
    process(peer["process"], boot)
    states.fields(peer["credentials"], "pid uid gid")
    for k in ("uid", "gid"):
        integer(peer["credentials"][k], 0, 2**32 - 2)
    pid(peer["credentials"]["pid"])
    # ubs:ignore[python.ctcompare.secret_eq] -- Kernel PID metadata, not secret.
    if peer["credentials"]["pid"] != peer["process"]["pid"] or peer["process"]["pid"] == old:
        raise ValueError("peer credential/process mismatch")
    endpoint = peer["endpoint"]
    states.fields(endpoint, "path directory device inode uid gid mode")
    path(endpoint["path"])
    inode(endpoint["directory"])
    for k in ("device", "inode", "uid", "gid"):
        integer(endpoint[k])
    integer(endpoint["mode"], 0, 0o7777)
    ident = source["identity"]
    # ubs:ignore[python.ctcompare.secret_eq] -- Kernel UID metadata, not secret.
    if (
        endpoint["path"] != ident["niri_socket"]
        or endpoint["device"] != ident["socket_device"]
        or endpoint["inode"] != ident["socket_inode"]
        or endpoint["mode"] & 0o022
        or endpoint["uid"] != peer["credentials"]["uid"]
    ):
        raise ValueError("endpoint differs from original/current credential scope")
    if not same(peer["inventory"], inventory(source, peer["process"])):
        raise ValueError("original peer bridge differs")
    version(source, peer["version"])
    image(peer["running_image"])
    scope = value["scope"]
    states.fields(scope, "pid_namespace user_namespace procfs")
    inode(scope["pid_namespace"])
    inode(scope["user_namespace"])
    proc = scope["procfs"]
    if value["method"] == LEGACY_METHOD:
        namespace = "init_pid_namespace"
        states.fields(proc, "device inode filesystem init_pid_namespace")
    elif value["method"] == SELF_V1_METHOD:
        namespace = "pid_namespace"
        states.fields(proc, "device inode filesystem mount_id pid_namespace")
        integer(proc["mount_id"], 1, 2**64 - 1)
    elif value["method"] == METHOD:
        namespace = "pid_namespace"
        states.fields(proc, "device inode filesystem mount_id pid_namespace")
        integer(proc["mount_id"], 1, 2**64 - 1)
    else:
        raise ValueError("unknown current proof method")
    inode({k: proc[k] for k in ("device", "inode")})
    if proc["filesystem"] != "proc" or not same(proc[namespace], scope["pid_namespace"]):
        raise ValueError("unbound proc namespace-init anchor")
    if not same(
        value["absence"],
        {"process": launched, "primitive": "linux-pidfd-open", "flags": 0, "errno": "ESRCH"},
    ):
        raise ValueError("exact original pidfd ESRCH evidence required")
    caller(value["caller"], boot, old)
    all_pins = [*pins, peer["process"], *(r["process"] for r in value["caller"]["ancestry"])]
    seen = {}
    for p in all_pins:
        if p["pid"] in seen and not same(p, seen[p["pid"]]):
            raise ValueError("conflicting held generation pins")
        seen[p["pid"]] = p


def live_method(plan):
    if plan["current"].get("method") != METHOD:
        raise ValueError("unfinished historical current method cannot authorize live work")
