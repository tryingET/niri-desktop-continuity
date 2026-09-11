"""Fabricated profiles/history/observer packets; never import or contact a native owner."""

import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_recovery_backend import private_json
from test_saved_reopen_backend import pin, provision

from niri_desktop_continuity import (
    cli,
    operation_lock,
    recovery,
    recovery_profile,
    recovery_transition,
    resolution_candidate,
)
from niri_desktop_continuity.model import digest, fingerprint, focus_pin
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.recovery_verification import receipt
from niri_desktop_continuity.resolution_graph import WORKER, coordinator_digest
from niri_desktop_continuity.resolution_io import Objects, retained
from niri_desktop_continuity.store import Store

BOOT = "00000000-0000-4000-8000-000000000001"
NEW_BOOT = "00000000-0000-4000-8000-000000000002"
REFS = ["b" * 64, "c" * 64]


def forbidden(*args, **kwargs):
    raise AssertionError("native effect or process invocation forbidden")


def worker_record(root, kind, attempt, data, *, refs=(), directory="objects"):
    value = {
        "schema": WORKER,
        "kind": kind,
        "attempt_digest": attempt,
        "sequence": 0,
        "refs": sorted(refs),
        "data": data,
    }
    key = digest(value)
    private_json(root / directory / f"{key}.json", value)
    return key


@pytest.fixture(name="resolution")
def resolution(tmp_path, monkeypatch):
    root = tmp_path / "fixture"
    data = provision(root)
    monkeypatch.setattr(recovery_profile, "profile_path", lambda: root / "profile.json")
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: root / "runtime")
    monkeypatch.setattr(cli, "capture", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    worker = root / "worker"
    worker.mkdir(mode=0o700)
    for name in ("objects", "attempts", "events", "children", "requests", "started", "finished"):
        (worker / name).mkdir(mode=0o700)
    for name in ("old", "new", "stdlib"):
        (root / name).mkdir(mode=0o700)
    for name in ("old", "new"):
        private_json(
            root / name / "saved-reopen.json",
            {"schema": resolution_candidate.MACHINE, "private_root": str(worker)},
        )
    snapshot = deepcopy(data["snapshot"])
    snapshot["identity"]["boot_id"] = BOOT
    store = Store(root / "state")
    snapshot_key = store.put("snapshots", snapshot)
    old = data["profile"]
    old["sources"].append(pin(root / "old/saved-reopen.json"))
    private_json(root / "profile.json", old)
    configured = {
        "schema": old["schema"],
        "profile_digest": digest(old),
        "interpreter": old["interpreter"],
        "endpoint": old["endpoint"],
    }
    private_json(root / "config.json", configured)
    observation = json.loads((root / "settings.json").read_text())["observation"]
    observation.update(
        identity_digest=digest(snapshot["identity"]),
        state_fingerprint=fingerprint(snapshot),
        focus_digest=digest(focus_pin(snapshot)),
        session_refs=REFS,
        saved_selection={"missing_refs": REFS, "present_refs": [], "unresolved_refs": []},
    )
    monkeypatch.setattr(Adapter, "call", lambda *a, **kw: deepcopy(observation))
    planned = recovery.propose(
        store,
        snapshot_key,
        root / "config.json",
        snapshot,
        mode="additive",
        saved_set=observation["saved_set"],
    )
    plan = store.get("plans", planned["plan_digest"])
    approval = recovery.approval_record(plan, digest(plan))
    attempt = store.put("approvals", approval)
    ledger = Ledger(old)
    ledger.store.put("snapshots", snapshot)
    ledger.store.put("plans", plan)
    ledger.store.put("approvals", approval)
    pair = ledger.prepare(store, attempt, digest(plan))
    ledger.finish(store, pair, receipt(plan, attempt, None, history_complete=False, events=[]))
    private_json(worker / "attempts" / f"{attempt}.json", {"request_digest": "a" * 64})
    saved_files = [
        {
            "session_ref": ref,
            "device": 1,
            "inode": i + 10,
            "prefix_bytes": 20,
            "prefix_sha256": "d" * 64,
            "metadata_ref": "e" * 64,
        }
        for i, ref in enumerate(REFS)
    ]
    manifest = {
        "saved_set": observation["saved_set"],
        "selected_refs": REFS,
        "first_ref": REFS[0],
        "saved_files": saved_files,
    }
    worker_record(worker, "manifest", attempt, manifest)
    new = deepcopy(old)
    endpoint = root / "new/endpoint.py"
    endpoint.write_text("raise RuntimeError('fabricated endpoint never executed')\n")
    endpoint.chmod(0o600)
    new["endpoint"] = pin(endpoint)
    new["sources"] = [pin(root / "new/saved-reopen.json")]
    private_json(root / "new-profile.json", new)
    module = root / "new/observer.py"
    module.write_text("# fabricated closed module\n")
    module.chmod(0o600)
    observer = {
        "interpreter": pin(Path(sys.executable).resolve()),
        "endpoint": pin(endpoint),
        "sources": [pin(module), pin(root / "new/saved-reopen.json")],
        "modules": {"fabricated_observer": str(module)},
        "config": pin(root / "new/saved-reopen.json"),
        "platform": {
            "schema": "desktop-continuity.observer-platform.v1",
            "python_sha256": pin(Path(sys.executable).resolve())["sha256"],
            "stdlib_root": str(root / "stdlib"),
            "policy": "isolated-source-only-v1",
        },
    }
    private_json(root / "observer.json", observer)
    original_files = [
        retained(p["path"])
        for p in sorted([old["endpoint"], *old["sources"]], key=lambda p: p["path"])
    ]
    old_config, new_config = (
        retained(root / "old/saved-reopen.json"),
        retained(root / "new/saved-reopen.json"),
    )
    review = {
        "schema": "desktop-continuity.resolution-source-review.v1",
        "old_profile_digest": digest(old),
        "new_profile_digest": digest(new),
        "old_config_sha256": old_config["sha256"],
        "new_config_sha256": new_config["sha256"],
        "original_sources_digest": digest(
            [{k: v[k] for k in ("path", "sha256")} for v in original_files]
        ),
        "coordinator_sha256": coordinator_digest(),
        "prefix_rule": "zero-permit-v1",
        "claim": "wait-before-terminal;permit-before-dispatch;no-detached-transport;one-shot-bootstrap;no-autostart",
    }
    private_json(root / "review.json", review)
    source = {
        "schema": resolution_candidate.SOURCE,
        "original_files": original_files,
        "old_config": old_config,
        "new_config": new_config,
        "review_artifact": retained(root / "review.json"),
        "original_profile_digest": digest(old),
        "coordinator_sha256": coordinator_digest(),
        "prefix_rule": "zero-permit-v1",
    }
    private_json(root / "source.json", source)
    data.update(
        old=old,
        new=new,
        worker=worker,
        attempt=attempt,
        original_plan=plan,
        source=source,
        observer=observer,
        saved_files=saved_files,
        ledger=ledger,
        manifest=manifest,
    )
    return data


def candidate(data):
    root = data["root"]
    result = resolution_candidate.plan(
        root / "new-profile.json",
        root / "observer.json",
        root / "source.json",
        data["attempt"],
        600,
    )
    key = result["candidate_digest"]
    return key, Objects(data["old"]["ledger_root"]).get(key)


def packet(candidate, graph_key, *, boot=BOOT, unknown=False):
    instant = datetime.now(timezone.utc)
    row = {
        "boot_id": boot,
        "pid": 20,
        "tgid": 20,
        "start_ticks": 100,
        "ppid": 1,
        "pgid": 20,
        "sid": 20,
        "uid": 1000,
        "image_digest": "a" * 64,
        "pid_namespace_inode": 8,
    }
    names = {"schema": "desktop-continuity.process-names.v1", "tasks": [20]}
    rows = {"schema": "desktop-continuity.process-rows.v1", "rows": [row]}
    discovery = {
        "schema": "desktop-continuity.candidate-discovery.v1",
        "contract": "owner-reviewed-possible-writer-and-recovery-executor-v1",
        "rows": [
            {
                "process_ref": digest(row),
                "classification": "unknown" if unknown else "noncandidate",
                "association_ref": None,
            }
        ],
    }
    attachments = sorted({digest(v): v for v in (names, rows, discovery)}.items())
    evidence = {
        "schema": "desktop-continuity.settlement-evidence.v1",
        "candidate_digest": digest(candidate),
        "graph_digest": graph_key,
        "observed_at": instant.isoformat(),
        "expires_at": min((instant + timedelta(seconds=300)).isoformat(), candidate["expires_at"]),
        "observer_digest": digest(candidate["observer"]),
        "boot_before": boot,
        "boot_after": boot,
        "current_identity": {
            "boot_id": boot,
            "niri_socket": "/fabricated",
            "socket_device": 1,
            "socket_inode": 1,
        },
        "focus_digest": "f" * 64,
        "protected_digest": "e" * 64,
        "process_scan": {
            "rows_ref": digest(rows),
            "names_before_ref": digest(names),
            "names_after_ref": digest(names),
            "attribution_ref": digest(discovery),
            "complete": True,
            "escaped_cohort": "not-created",
        },
        "writers": [],
        "tickets": [],
        "saved_files": [
            {
                "session_ref": ref,
                "device": 1,
                "inode": i + 10,
                "bytes": 30,
                "sha256": "a" * 64,
                "original_prefix_bytes": 20,
                "original_prefix_sha256": "d" * 64,
                "metadata_ref": "e" * 64,
                "prefix_preserved": True,
            }
            for i, ref in enumerate(REFS)
        ],
        "source_contract_digest": digest(candidate["source_contract"]),
        "mode": "same-boot-zero-permit",
        "verdict": "blocked" if unknown else "settled",
        "blockers": ["capability-unknown"] if unknown else [],
    }
    return {
        "schema": "desktop-continuity.settlement-packet.v1",
        "evidence": evidence,
        "attachments": [{"digest": k, "value": v} for k, v in attachments],
    }


def approved(data, monkeypatch):
    key, value = candidate(data)
    resolution_candidate.approve(key, key, "resolution-observe-only")
    monkeypatch.setattr(recovery_transition, "observe", lambda c, g: packet(value, g))
    planned = recovery_transition.plan(key, data["attempt"])
    key = planned["plan_digest"]
    approval = recovery_transition.approve(key, key, "abandon-without-retry-or-success")
    return approval["approval_digest"], value
