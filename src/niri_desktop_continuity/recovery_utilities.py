"""Exact v2 btop utility identities; no native sessions or invented running-image pins."""

from .model import digest
from .recovery_protocol import boolean, fields, hexkey, process_pin, require, sequence

BIRTH = ("boot_id", "pid", "start_ticks", "uid")
PREDICATES = ("identity", "installed_file", "capabilities", "sole_owned_leaf", "causal_window")


def utility_limits(observation):
    return [
        item["utility_ref"]
        for item in observation["utilities"]
        if item["identity"]["kind"] == "capability-btop"
    ]


def utility(item):
    fields(
        item,
        (
            "utility_ref",
            "kind",
            "host_pin",
            "identity",
            "owned",
            "identity_proved",
            "protected_overlap",
            "evidence_ref",
        ),
    )
    require(item["kind"] == "btop")
    process_pin(item["host_pin"])
    hexkey(item["evidence_ref"])
    for name in ("owned", "identity_proved", "protected_overlap"):
        boolean(item[name])
    identity, host = item["identity"], item["host_pin"]
    fields(
        identity,
        (
            "kind",
            *BIRTH,
            "parent_pid",
            "cgroup_digest",
            "argv_digest",
            "image_pin",
            "installed_file_ref",
            "capabilities_digest",
            "running_image",
        ),
    )
    require(identity["kind"] in ("observed-image", "capability-btop"))
    require(identity["boot_id"] == host["boot_id"] and identity["uid"] == host["uid"])
    for name in ("pid", "start_ticks", "uid", "parent_pid"):
        require(type(identity[name]) is int and 0 <= identity[name] < 2**63)
    require(all(identity[name] > 0 for name in ("pid", "start_ticks", "parent_pid")))
    require(identity["parent_pid"] == host["pid"] and identity["pid"] != host["pid"])
    for name in ("cgroup_digest", "argv_digest", "installed_file_ref"):
        hexkey(identity[name])
    if identity["kind"] == "observed-image":
        require(identity["running_image"] == "observed" and identity["capabilities_digest"] is None)
        process_pin(identity["image_pin"])
        require(all(identity[name] == identity["image_pin"][name] for name in BIRTH))
    else:
        require(identity["running_image"] == "unobservable" and identity["image_pin"] is None)
        hexkey(identity["capabilities_digest"])
    require(
        hexkey(item["utility_ref"])
        == digest({name: item[name] for name in ("kind", "host_pin", "identity")})
    )


def utilities(observation):
    refs, pids, hosts = [], [], {}
    native = {item["pin"]["pid"]: item["pin"] for item in observation["processes"]}
    require(len(native) == len(observation["processes"]))
    for item in sequence(observation["utilities"]):
        utility(item)
        refs.append(item["utility_ref"])
        pids.append(item["identity"]["pid"])
        host = item["host_pin"]
        require(hosts.get(host["pid"], host) == host)
        require(native.get(host["pid"], host) == host)
        hosts[host["pid"]] = host
    require(refs == sorted(set(refs)))
    require(
        len(pids) == len(set(pids)) and not set(pids).intersection(native.keys() | hosts.keys())
    )


def utility_proof(value, admitted):
    refs, complete = [], True
    expected = {item["utility_ref"]: item for item in admitted}
    for item in sequence(value):
        fields(item, ("utility_ref", "evidence_ref", *PREDICATES, "running_image"))
        ref = hexkey(item["utility_ref"])
        refs.append(ref)
        require(ref in expected)
        hexkey(item["evidence_ref"])
        for name in PREDICATES:
            boolean(item[name])
            complete &= item[name]
        wanted = (
            "accepted-unobservable"
            if expected[ref]["identity"]["kind"] == "capability-btop"
            else "proved"
        )
        require(item["running_image"] in (wanted, "failed", "unknown"))
        complete &= item["running_image"] == wanted
    require(refs == sorted(expected))
    return bool(complete)
