"""Exact owner admission of data and a closed observer, never profile activation."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import recovery_profile as profiles
from .model import digest
from .recovery_protocol import ADDITIVE, decode, encode, fields, hexkey, require
from .resolution_io import (
    Objects,
    check_root,
    raw,
    retained,
    retained_bytes,
    root_pin,
)
from .resolution_lock import serialized
from .store import Store, private_directory

CANDIDATE = "desktop-continuity.profile-candidate.v1"
ADMISSION = "desktop-continuity.profile-admission.v1"
SOURCE = "desktop-continuity.resolution-source.v1"
CAPABILITY = "resolution-observe-only"
MACHINE = "workstation.saved-reopen.machine.v3"


def now():
    return datetime.now(timezone.utc)


def times(ttl):
    require(type(ttl) is int and 30 <= ttl <= 600)
    created = now()
    return {
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(seconds=ttl)).isoformat(),
    }


def lifetime(value, *, fresh=True):
    start, end = (datetime.fromisoformat(value[k]) for k in ("created_at", "expires_at"))
    require(start.utcoffset() == timedelta(0) and end.utcoffset() == timedelta(0))
    require(30 <= (end - start).total_seconds() <= 600)
    if fresh:
        require(start <= now() < end)


def anchor(kind, key):
    require(kind in ("candidates", "candidate-admissions"))
    return profiles.profile_path().parent / f"recovery-{kind}" / f"{hexkey(key)}.json"


def profile_bytes(value):
    return profiles.validate_profile(decode(retained_bytes(value)))


def machine_config(profile, retained_config):
    # A single real adapter configuration source, not caller-defined JSON pointers.
    pins = [p for p in profile["sources"] if Path(p["path"]).name == "saved-reopen.json"]
    require(len(pins) == 1)
    require(pins[0] == {k: retained_config[k] for k in ("path", "sha256")})
    config = decode(retained_bytes(retained_config))
    require(type(config) is dict and config.get("schema") == MACHINE)
    require(type(config.get("private_root")) is str)
    # Other machine configuration bytes remain opaque, covered by exact owner admission.
    return root_pin(config["private_root"])


def observer_spec(value, *, live=False):
    fields(value, ("interpreter", "endpoint", "sources", "modules", "platform", "config"))
    require(type(value["sources"]) is list and 1 <= len(value["sources"]) <= 256)
    pins = [value["interpreter"], value["endpoint"], *value["sources"]]
    for pin in pins:
        profiles.pin_spec(pin)
    require(len({p["path"] for p in pins}) == len(pins))
    require(value["config"] in value["sources"])
    fields(value["platform"], ("schema", "python_sha256", "stdlib_root", "policy"))
    platform = value["platform"]
    require(platform["schema"] == "desktop-continuity.observer-platform.v1")
    require(platform["python_sha256"] == value["interpreter"]["sha256"])
    require(platform["policy"] == "isolated-source-only-v1")
    require(type(platform["stdlib_root"]) is str and Path(platform["stdlib_root"]).is_absolute())
    require(".." not in Path(platform["stdlib_root"]).parts)
    modules = value["modules"]
    require(type(modules) is dict and 1 <= len(modules) <= 256)
    require(len(set(modules.values())) == len(modules))
    for name, path in modules.items():
        require(re.fullmatch(r"[a-zA-Z_]\w*(\.[a-zA-Z_]\w*)*", name) is not None)
        require(path in [p["path"] for p in value["sources"]] and path.endswith(".py"))
    if live:
        for pin in pins:
            profiles.pin_file(pin)
        require(os.access(value["interpreter"]["path"], os.X_OK))


def source_spec(source, old, new, old_config, new_config):
    fields(
        source,
        (
            "schema",
            "original_files",
            "old_config",
            "new_config",
            "review_artifact",
            "original_profile_digest",
            "coordinator_sha256",
            "prefix_rule",
        ),
    )
    require(source["schema"] == SOURCE and source["original_profile_digest"] == digest(old))
    require(source["prefix_rule"] in ("direct-first-ack-v1", "zero-permit-v1"))
    hexkey(source["coordinator_sha256"])
    require(source["old_config"] == old_config and source["new_config"] == new_config)
    files = source["original_files"]
    require(type(files) is list and 1 <= len(files) <= 256)
    for item in [*files, source["review_artifact"]]:
        retained_bytes(item)
    require(len({f["path"] for f in files}) == len(files))
    # Historic sources are proved only by retained provenance, never drifted live bytes.
    require(
        [{k: f[k] for k in ("path", "sha256")} for f in files]
        == sorted([old["endpoint"], *old["sources"]], key=lambda p: p["path"])
    )
    review = decode(retained_bytes(source["review_artifact"]))
    fields(
        review,
        (
            "schema",
            "old_profile_digest",
            "new_profile_digest",
            "old_config_sha256",
            "new_config_sha256",
            "original_sources_digest",
            "coordinator_sha256",
            "prefix_rule",
            "claim",
        ),
    )
    require(
        review
        == {
            "schema": "desktop-continuity.resolution-source-review.v1",
            "old_profile_digest": digest(old),
            "new_profile_digest": digest(new),
            "old_config_sha256": old_config["sha256"],
            "new_config_sha256": new_config["sha256"],
            "original_sources_digest": digest(
                [{k: f[k] for k in ("path", "sha256")} for f in files]
            ),
            "coordinator_sha256": source["coordinator_sha256"],
            "prefix_rule": source["prefix_rule"],
            "claim": "wait-before-terminal;permit-before-dispatch;no-detached-transport;one-shot-bootstrap;no-autostart",
        }
    )


def validate(candidate, *, live=False, active="old", fresh=True):
    fields(
        candidate,
        (
            "schema",
            "created_at",
            "expires_at",
            "old_profile",
            "new_profile",
            "old_config",
            "new_config",
            "ledger",
            "worker",
            "attempt_digest",
            "saved_set",
            "selected_refs",
            "observer",
            "source_contract",
        ),
    )
    require(candidate["schema"] == CANDIDATE)
    lifetime(candidate, fresh=fresh)
    old, new = (profile_bytes(candidate[k]) for k in ("old_profile", "new_profile"))
    require(old["schema"] == new["schema"] == ADDITIVE and digest(old) != digest(new))
    require(old["ledger_root"] == new["ledger_root"] == candidate["ledger"]["path"])
    require(old["legacy_locations"] == new["legacy_locations"])
    for key in ("ledger", "worker"):
        check_root(candidate[key])
    require(machine_config(old, candidate["old_config"]) == candidate["worker"])
    require(machine_config(new, candidate["new_config"]) == candidate["worker"])
    hexkey(candidate["attempt_digest"])
    hexkey(candidate["saved_set"])
    refs = candidate["selected_refs"]
    require(type(refs) is list and len(refs) == 2 and refs == sorted(set(refs)))
    for ref in refs:
        hexkey(ref)
    observer_spec(candidate["observer"], live=live)
    require(
        candidate["observer"]["config"]
        == {k: candidate["new_config"][k] for k in ("path", "sha256")}
    )
    source_spec(
        candidate["source_contract"], old, new, candidate["old_config"], candidate["new_config"]
    )
    if active is not None:
        require(raw(profiles.profile_path()) == retained_bytes(candidate[f"{active}_profile"]))
    if live:
        for pin in profiles.profile_pins(new):
            profiles.pin_file(pin)
        require(raw(candidate["new_config"]["path"]) == retained_bytes(candidate["new_config"]))
        # Pin the complete portable coordinator closure, not a single truth boolean.
        from .resolution_graph import coordinator_digest

        require(candidate["source_contract"]["coordinator_sha256"] == coordinator_digest())
    return old, new


def admission(candidate, record, *, fresh=True):
    fields(
        record,
        ("schema", "candidate_digest", "confirmation", "admitted_at", "expires_at", "capability"),
    )
    require(record["schema"] == ADMISSION and record["capability"] == CAPABILITY)
    require(record["confirmation"] == record["candidate_digest"] == digest(candidate))
    require(record["expires_at"] == candidate["expires_at"])
    at = datetime.fromisoformat(record["admitted_at"])
    require(
        datetime.fromisoformat(candidate["created_at"])
        <= at
        < datetime.fromisoformat(record["expires_at"])
    )
    lifetime(candidate, fresh=fresh)


def admitted(key, *, live=True, active="old", fresh=True):
    candidate = decode(raw(anchor("candidates", key)))
    require(digest(candidate) == key)
    record = decode(raw(anchor("candidate-admissions", key)))
    admission(candidate, record, fresh=fresh)
    validate(candidate, live=live, active=active, fresh=fresh)
    return candidate, record


@serialized
def plan(new_path, observer_path, source_path, attempt, ttl=300):
    source = decode(raw(source_path))
    old_raw, new_raw = retained(profiles.profile_path()), retained(new_path)
    old, new = profile_bytes(old_raw), profile_bytes(new_raw)
    from .recovery_ledger import Ledger

    ledger = Ledger(old, read_only=True)
    prepared = ledger.store.recovery_marker("recovery-prepared", hexkey(attempt))
    original = ledger.store.get("plans", prepared["plan_digest"])
    observed = original["recovery"]["observation"]
    selected = observed["saved_selection"]
    candidate = {
        "schema": CANDIDATE,
        **times(ttl),
        "old_profile": old_raw,
        "new_profile": new_raw,
        "old_config": source["old_config"],
        "new_config": source["new_config"],
        "ledger": root_pin(old["ledger_root"]),
        "worker": machine_config(new, source["new_config"]),
        "attempt_digest": attempt,
        "saved_set": observed["saved_set"],
        "selected_refs": sorted(selected["missing_refs"] + selected["present_refs"]),
        "observer": decode(raw(observer_path)),
        "source_contract": source,
    }
    validate(candidate)
    from .resolution_graph import initial

    initial(candidate)
    key = Objects(old["ledger_root"]).put(candidate)
    return {
        "candidate_digest": key,
        "native_effects": [],
        "accounting_mutations": ["candidate-object"],
        "activation_authorized": False,
    }


@serialized
def approve(key, confirmation, acceptance):
    require(confirmation == hexkey(key) and acceptance == CAPABILITY)
    profile = profiles.identify_profile()
    objects = Objects(profile["ledger_root"])
    candidate = objects.get(key)
    validate(candidate, live=True)
    from .resolution_graph import initial

    initial(candidate)
    record = {
        "schema": ADMISSION,
        "candidate_digest": key,
        "confirmation": confirmation,
        "admitted_at": now().isoformat(),
        "expires_at": candidate["expires_at"],
        "capability": CAPABILITY,
    }
    admission(candidate, record)
    for kind, value in (("candidates", candidate), ("candidate-admissions", record)):
        path = anchor(kind, key)
        private_directory(path.parent)
        # A torn first write is deliberately not repaired by a second approval.
        Store._create(objects, path, encode(value))
    objects.put(record)
    return {
        "candidate_digest": key,
        "capability": CAPABILITY,
        "native_effects": [],
        "accounting_mutations": ["fixed-candidate-anchor", "exact-owner-admission"],
        "activation_authorized": False,
    }
