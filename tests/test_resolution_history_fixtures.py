"""Entirely fabricated State/Journal bytes; no owner imports or live runtime queries."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_recovery_backend import private_json
from test_resolution_fixtures import BOOT
from test_resolution_fixtures import resolution as resolution_fixture  # noqa: F401
from test_saved_reopen_backend import pin as fixture_pin

from niri_desktop_continuity import recovery
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.recovery_verification import receipt
from niri_desktop_continuity.resolution_graph import coordinator_digest
from niri_desktop_continuity.resolution_io import retained, sha
from niri_desktop_continuity.store import Store


def pin(path):
    return fixture_pin(Path(path))


def put(root, value):
    key = digest(value)
    private_json(root / "objects" / f"{key}.json", value)
    return key


def canonical(data, plan, profile, events=(), *, proof=None, complete=False):
    ledger = Ledger(profile)
    cli = Store(data["root"] / "history-cli")
    plan_key = ledger.store.put("plans", plan)
    approval = recovery.approval_record(plan, plan_key)
    attempt = ledger.store.put("approvals", approval)
    cli.put("plans", plan)
    cli.put("approvals", approval)
    # Construct historical bytes, not an admission bypass used by product code.
    pair = {
        "schema": profile["schema"],
        "profile_digest": digest(profile),
        "approval_digest": attempt,
        "plan_digest": plan_key,
    }
    ledger.store.recovery_marker(
        "recovery-prepared",
        attempt,
        {**pair, "cli_used_path": str(cli.path("used", attempt)), "binding": pair},
    )
    cli.consume(attempt, pair)
    ledger.store.recovery_marker("recovery-ready", attempt, pair)
    for event, value in events:
        ledger.event(attempt, event, value)
    ledger.finish(
        cli,
        pair,
        receipt(
            plan,
            attempt,
            proof,
            history_complete=complete,
            events=[v for k, v in events if k == "result"],
        ),
    )
    return ledger, attempt


@pytest.fixture(name="real_history")
def real_history(resolution):
    data = resolution
    root = data["root"]
    worker = root / "historical-worker"
    worker.mkdir(mode=0o700)
    directories = ["objects", "attempts", "events", "children", "finished", "bootstraps"]
    for name in directories:
        (worker / name).mkdir(mode=0o700)
    private_json(
        worker / "catalog.json",
        {"schema": "workstation.saved-reopen.catalog.v1", "directories": directories},
    )
    old = deepcopy(data["old"])
    old["ledger_root"] = str(root / "historical-ledger")
    Ledger(old)
    tools = {"python": old["interpreter"]["path"]}
    for name in ("node", "pi", "bootstrap", "ghostty", "presence"):
        path = root / "old" / f"{name}.py"
        path.write_text("# fabricated never-executed tool\n")
        path.chmod(0o600)
        tools[name] = str(path)
        old["sources"].append(pin(path))
    startup = {
        "schema": "workstation.saved-reopen.presence-only.v2",
        "agent_dir": str(root / "synthetic-agent"),
        "presence_dir": str(root / "synthetic-presence"),
        "tmp_dir": str(root / "synthetic-scratch"),
        "pi_version": "1.2.3",
    }
    (root / "synthetic-agent").mkdir(mode=0o700)
    for key, name in (
        ("settings", "settings.json"),
        ("auth", "auth.json"),
        ("models_store", "models-store.json"),
    ):
        path = root / "synthetic-agent" / name
        private_json(path, {})
        startup[key] = pin(path)
        old["sources"].append(pin(path))
    config = {
        "schema": "workstation.saved-reopen.machine.v3",
        "private_root": str(worker),
        "tools": tools,
        "startup": startup,
    }
    for side in ("old", "new"):
        private_json(root / side / "saved-reopen.json", config)
    old["sources"] = [pin(p["path"]) for p in old["sources"]]
    private_json(root / "profile.json", old)
    new = deepcopy(old)
    new["endpoint"] = data["new"]["endpoint"]
    new["sources"] = [
        p for p in old["sources"] if p["path"] != str(root / "old/saved-reopen.json")
    ] + [pin(root / "new/saved-reopen.json")]
    private_json(root / "new-profile.json", new)
    observer = data["observer"]
    observer["config"] = pin(root / "new/saved-reopen.json")
    observer["sources"] = [pin(p["path"]) for p in observer["sources"]]
    private_json(root / "observer.json", observer)
    items = {}
    for index in (1, 2):
        item = {
            "file": str(root / f"fiction-{index}.jsonl"),
            "id": f"00000000-0000-4000-8000-{index:012d}",
            "cwd": str(root / f"fiction-cwd-{index}"),
        }
        items[digest({"kind": "pi", **item})] = {
            "selection": item,
            "metadata": {
                "header": {"id": item["id"], "cwd": item["cwd"], "parentSession": None},
                "bytes": 20,
                "sha256": "d" * 64,
                "device": 1,
                "inode": index + 10,
            },
            "present": None,
        }
    refs = sorted(items)
    plan = deepcopy(data["original_plan"])
    instant = datetime.now(timezone.utc) - timedelta(hours=2)
    plan["created_at"] = instant.isoformat()
    plan["expires_at"] = (instant + timedelta(seconds=300)).isoformat()
    plan["recovery"]["profile_digest"] = digest(old)
    observed = plan["recovery"]["observation"]
    observed["session_refs"] = refs
    observed["saved_selection"] = {"missing_refs": refs, "present_refs": [], "unresolved_refs": []}
    public = {
        "diagnostics": {
            "schema": "desktop-continuity.saved-diagnostics.v1",
            "reasons": [],
            "capacity": "available",
        },
        "grouping": {
            "schema": "desktop-continuity.saved-grouping.v1",
            "saved_set": observed["saved_set"],
            "groups": [
                {
                    "session_refs": refs,
                    "provenance": "requested",
                    "reviewed": True,
                    "sequence": "desired-creation",
                }
            ],
        },
    }
    observed.update(public)
    snapshot = data["ledger"].store.get("snapshots", plan["snapshot_digest"])
    manifest = {
        **{
            k: observed[k]
            for k in (
                "saved_set",
                "identity_digest",
                "state_fingerprint",
                "focus_digest",
                "saved_selection",
            )
        },
        "focus": deepcopy(plan["focus_pin"]),
        "protected": {k: snapshot[k] for k in ("identity", "windows", "processes")},
        "items": items,
        "projections": public,
        "groups": [
            {
                "session_ids": [items[r]["selection"]["id"] for r in refs],
                "refs": refs,
                "provenance": "requested",
                "reviewed": True,
                "sequence": "desired-creation",
            }
        ],
    }
    observed["private_ref"] = put(worker, manifest)
    ledger = Ledger(old)
    ledger.store.put("snapshots", snapshot)
    # The attempt digest is known before creating its event records.
    attempt = digest(recovery.approval_record(plan, digest(plan)))
    intent = {"attempt": attempt, "sequence": 0, "kind": "launch", "target_ref": refs[0]}
    intent_ref = put(worker, intent)
    private_json(
        worker / "events" / f"{digest({'attempt': attempt, 'sequence': 0})}.json",
        {"intent_ref": intent_ref},
    )
    measurement = {"attempt": attempt, "intent_ref": intent_ref, "measurement": 40}
    measured = put(worker, measurement)
    outcome = {
        "sequence": 0,
        "intent_ref": intent_ref,
        "outcome": "observed",
        "evidence_ref": measured,
    }
    result_ref = put(worker, outcome)
    ack = {"attempt": attempt, "sequence": 0, "result_ref": result_ref}
    put(worker, ack)
    first = items[refs[0]]["selection"]
    child = {
        "attempt": attempt,
        "session_ref": refs[0],
        "pid": 40,
        "host": {
            "pid": 40,
            "start_ticks": 42,
            "boot_id": BOOT,
            "exe": tools["ghostty"],
            "exe_sha256": pin(tools["ghostty"])["sha256"],
            "exe_device": 1,
            "exe_inode": 5,
            "cwd": first["cwd"],
            "tty": 0,
        },
    }
    key = digest({"attempt": attempt, "session_ref": refs[0]})
    private_json(worker / "children" / f"{key}.json", child)
    request = {
        "attempt": attempt,
        "session_ref": refs[0],
        **first,
        "file_sha256": "d" * 64,
        "expires_at": plan["expires_at"],
        **{k: pin(tools[k]) for k in ("node", "pi", "bootstrap", "python")},
        "startup": {**startup, "presence": pin(tools["presence"])},
    }
    request_path = worker / "bootstraps" / f"{key}.json"
    private_json(request_path, request)
    # Intentionally noncanonical original serialization (as bootstrap's json.dump).
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    claim = {
        "request": str(request_path),
        "request_sha256": sha(request_path.read_bytes()),
        "pid": 41,
        "start_ticks": 43,
        "boot_id": BOOT,
        "ppid": 40,
        "cwd": first["cwd"],
        "argv": [
            tools["node"],
            tools["pi"],
            "--no-extensions",
            "--offline",
            "--extension",
            tools["presence"],
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-approve",
            "--no-context-files",
            "--session",
            first["file"],
        ],
    }
    claim_path = request_path.with_suffix(".started.json")
    private_json(claim_path, claim)
    claim_path.write_text(json.dumps(claim, sort_keys=True))
    private_json(worker / "attempts" / f"{attempt}.json", {"request_digest": "a" * 64})
    ledger, actual_attempt = canonical(
        data,
        plan,
        old,
        [
            (
                "intent",
                {"sequence": 0, "kind": "launch", "intent_ref": intent_ref, "target_ref": refs[0]},
            ),
            ("result", outcome),
        ],
    )
    assert actual_attempt == attempt
    original_files = [
        retained(p["path"])
        for p in sorted([old["endpoint"], *old["sources"]], key=lambda p: p["path"])
    ]
    old_config, new_config = (
        retained(root / "old/saved-reopen.json"),
        retained(root / "new/saved-reopen.json"),
    )
    review = json.loads((root / "review.json").read_text())
    review.update(
        old_profile_digest=digest(old),
        new_profile_digest=digest(new),
        old_config_sha256=old_config["sha256"],
        new_config_sha256=new_config["sha256"],
        original_sources_digest=digest(
            [{k: v[k] for k in ("path", "sha256")} for v in original_files]
        ),
        prefix_rule="direct-first-ack-v1",
        coordinator_sha256=coordinator_digest(),
    )
    private_json(root / "review.json", review)
    source = data["source"]
    source.update(
        original_files=original_files,
        old_config=old_config,
        new_config=new_config,
        original_profile_digest=digest(old),
        prefix_rule="direct-first-ack-v1",
        review_artifact=retained(root / "review.json"),
        coordinator_sha256=coordinator_digest(),
    )
    private_json(root / "source.json", source)
    data.update(
        old=old,
        new=new,
        worker=worker,
        ledger=ledger,
        attempt=attempt,
        original_plan=plan,
        manifest=manifest,
        request=request,
        request_path=request_path,
        claim=claim,
        claim_path=claim_path,
        child=child,
        intent=intent,
        outcome=outcome,
        measurement=measurement,
        ack=ack,
        refs=refs,
    )
    return data
