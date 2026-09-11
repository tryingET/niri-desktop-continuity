"""Handwritten refusal/crash oracles, independent expected outcomes; fabricated effects only."""

from copy import deepcopy

import pytest
from test_recovery_backend import private_json
from test_resolution_fixtures import (  # noqa: F401
    BOOT,
    NEW_BOOT,
    approved,
    candidate,
    forbidden,
    packet,
    worker_record,
)
from test_resolution_fixtures import resolution as resolution_fixture  # noqa: F401

from niri_desktop_continuity import (
    cli,
    recovery,
    recovery_profile,
    recovery_resolution,
    recovery_transition,
    resolution_candidate,
    resolution_evidence,
    resolution_graph,
    resolution_observer,
)
from niri_desktop_continuity.model import digest
from niri_desktop_continuity.recovery_ledger import Ledger
from niri_desktop_continuity.resolution_io import Objects, raw, retained, retained_bytes
from niri_desktop_continuity.store import Store


def test_candidate_is_data_only_and_explicit_admission(resolution):
    key, value = candidate(resolution)
    assert not resolution_candidate.anchor("candidate-admissions", key).exists()
    with pytest.raises(FileNotFoundError):
        resolution_observer.observe(key, "a" * 64)
    # Old control drift is not reconstructed from live sources and never runs old code.
    old = resolution["root"] / "endpoint.py"
    old.write_text("drifted old controls; must not execute")
    result = resolution_candidate.approve(key, key, "resolution-observe-only")
    assert result["native_effects"] == [] and result["activation_authorized"] is False
    assert raw(recovery_profile.profile_path()) == retained_bytes(value["old_profile"])
    with pytest.raises(FileExistsError):
        resolution_candidate.approve(key, key, "resolution-observe-only")
    with pytest.raises(ValueError):
        resolution_candidate.approve(key, "0" * 64, "resolution-observe-only")


def test_final_is_one_shared_edge_not_success_or_replay(resolution, monkeypatch):
    approval, value = approved(resolution, monkeypatch)
    ledger = resolution["ledger"]
    originals = {
        p: p.read_bytes()
        for name in ("recovery-prepared", "recovery-ready", "recovery-terminal", "recovery-events")
        for p in (ledger.store.root / name).iterdir()
    }
    with pytest.raises(ValueError):
        ledger.available()
    result = recovery_transition.apply(approval)
    assert result["historical_status"] == "indeterminate"
    assert result["resolution_disposition"] == "abandoned-settled"
    assert result["transition_state"] == "final" and result["replay_authorized"] is False
    assert result["native_effects"] == [] and result["next_attempt_authorized"] is False
    assert all(p.read_bytes() == before for p, before in originals.items())
    assert not list((resolution["worker"] / "finished").iterdir())
    assert Ledger(resolution["new"]).available() is None
    assert Ledger(resolution["new"]).admission_disposition() == [
        {"attempt_digest": resolution["attempt"], "status": "indeterminate", "admissible": True}
    ]
    assert ledger.attempt_status(resolution["attempt"]) == "indeterminate"
    with pytest.raises(ValueError):
        ledger.available()  # An old-pinned client never gets general foreign-profile tolerance.
    with pytest.raises(ValueError):
        recovery_transition.apply(approval)
    other = Store(resolution["root"] / "other")
    for kind, key in (
        ("plans", digest(resolution["original_plan"])),
        ("approvals", resolution["attempt"]),
    ):
        other.put(kind, ledger.store.get(kind, key))
    with pytest.raises(ValueError):
        recovery.execute(other, resolution["attempt"], forbidden)
    assert raw(recovery_profile.profile_path()) == retained_bytes(value["new_profile"])


@pytest.mark.parametrize("step", ["stage", "prepared", "used", "ready", "pending", "cas", "final"])
def test_every_crash_prefix_blocks_both_readers_without_repair(resolution, monkeypatch, step):
    approval, _ = approved(resolution, monkeypatch)
    create = Objects.create
    sync = recovery_transition.sync_directory
    native_create = Store._create

    def fault(self, kind, key, data):
        create(self, kind, key, data)
        if kind == step:
            raise OSError("fabricated crash after durable marker")

    def stage(self, path, content):
        native_create(self, path, content)
        if step == "stage" and path.suffix == ".stage":
            raise OSError("fabricated staging crash")

    def cas(path):
        sync(path)
        if step == "cas":
            raise OSError("fabricated CAS uncertainty")

    monkeypatch.setattr(Objects, "create", fault)
    monkeypatch.setattr(Store, "_create", stage)
    monkeypatch.setattr(recovery_transition, "sync_directory", cas)
    with pytest.raises(OSError):
        recovery_transition.apply(approval)
    current = recovery_profile.identify_profile()
    before = {p: p.read_bytes() for p in resolution["root"].rglob("*") if p.is_file()}
    if step == "final":
        # fsynced final is authority even if the caller lost its reply.
        assert recovery_resolution.durable_view(current)["transition_state"] == "final"
        Ledger(current).available()
    else:
        with pytest.raises(ValueError):
            Ledger(current).available()
        assert recovery_resolution.inspect(current, approval)["next_attempt_authorized"] is False
    with pytest.raises((ValueError, FileExistsError)):
        recovery_transition.apply(approval)
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize("kind", ["prepared", "used", "ready", "pending", "final"])
def test_torn_or_orphan_markers_fence_admission(resolution, kind):
    objects = Objects(resolution["old"]["ledger_root"])
    objects.create(kind, "a" * 64, b'{"torn":')
    with pytest.raises(ValueError):
        Ledger(resolution["old"]).available()
    assert (
        recovery_resolution.inspect(resolution["old"], resolution["attempt"])["transition_state"]
        == "blocked-or-damaged"
    )


@pytest.mark.parametrize(
    "damage",
    [
        "root",
        "inode",
        "observer-config",
        "mapping",
        "legacy",
        "retained",
        "profile-cas",
        "live-config",
    ],
)
def test_candidate_exact_roots_pins_and_retained_provenance(resolution, damage):
    _, value = candidate(resolution)
    if damage == "root":
        value["worker"]["path"] = str(resolution["root"] / "runtime")
    elif damage == "inode":
        value["ledger"]["inode"] += 1
    elif damage == "observer-config":
        value["observer"]["config"] = value["observer"]["sources"][0]
    elif damage == "mapping":
        config = resolution["root"] / "new/saved-reopen.json"
        private_json(
            config,
            {
                "schema": resolution_candidate.MACHINE,
                "private_root": str(resolution["root"] / "runtime"),
            },
        )
        value["new_config"] = retained(config)
    elif damage == "legacy":
        profile = deepcopy(resolution["new"])
        profile["legacy_locations"] = [str(resolution["root"] / "runtime")]
        path = resolution["root"] / "new-profile.json"
        private_json(path, profile)
        value["new_profile"] = retained(path)
    elif damage == "retained":
        value["source_contract"]["original_files"][0]["sha256"] = "0" * 64
    elif damage == "profile-cas":
        private_json(recovery_profile.profile_path(), resolution["new"])
    else:
        (resolution["root"] / "new/saved-reopen.json").write_text("drift")
    with pytest.raises(ValueError):
        resolution_candidate.validate(value, live=True)


def test_final_survives_unrelated_manifest_but_not_a0_orphan(resolution, monkeypatch):
    approval, value = approved(resolution, monkeypatch)
    recovery_transition.apply(approval)
    worker_record(resolution["worker"], "manifest", "1" * 64, resolution["manifest"])
    assert recovery_resolution.durable_view(resolution["new"])["transition_state"] == "final"
    worker_record(
        resolution["worker"],
        "intent",
        resolution["attempt"],
        {"intent_ref": "2" * 64, "target_ref": value["selected_refs"][0]},
    )
    with pytest.raises(ValueError):
        recovery_resolution.durable_view(resolution["new"])


def test_new_normal_admission_rechecks_config_root_and_foreign_profile(resolution, monkeypatch):
    approval, _ = approved(resolution, monkeypatch)
    recovery_transition.apply(approval)
    (resolution["root"] / "new/saved-reopen.json").write_text("changed private root")
    with pytest.raises(ValueError):
        Ledger(resolution["new"]).available()
    # Offline historical view does not execute or validate drifted live control bytes.
    assert (
        recovery_resolution.durable_view(resolution["new"])["historical_status"] == "indeterminate"
    )
    foreign = deepcopy(resolution["new"])
    foreign["reviewed"] = False
    with pytest.raises(ValueError):
        recovery_resolution.durable_view(foreign)


def test_unknown_writer_blocks_but_noncandidate_needs_no_pid_waiver(resolution, monkeypatch):
    key, value = candidate(resolution)
    resolution_candidate.approve(key, key, "resolution-observe-only")
    graph = resolution_graph.initial(value)
    objects = Objects(value["ledger"]["path"])
    good = packet(value, digest(graph))
    assert resolution_evidence.persist_packet(good, value, graph, objects)
    blocked = packet(value, digest(graph), unknown=True)
    key = resolution_evidence.persist_packet(blocked, value, graph, objects)
    assert objects.get(key)["verdict"] == "blocked"
    lied = deepcopy(blocked)
    lied["evidence"].update(verdict="settled", blockers=[])
    with pytest.raises(ValueError):
        resolution_evidence.persist_packet(lied, value, graph, objects)


@pytest.mark.parametrize("selected_index", [0, 1])
@pytest.mark.parametrize("identity", ["hardlink", "different-device", "different-inode"])
def test_unrelated_writer_claim_cannot_hide_selected_descriptor(
    resolution, selected_index, identity
):
    import os

    # Real scratch hardlink + open descriptor; no native process census is consulted.
    selected = resolution["root"] / "selected.jsonl"
    selected.write_bytes(b"fabricated saved bytes\n")
    alias = resolution["root"] / "unrelated-name.jsonl"
    os.link(selected, alias)
    with alias.open("rb") as descriptor:
        info = os.fstat(descriptor.fileno())
    assert (info.st_dev, info.st_ino) == (selected.stat().st_dev, selected.stat().st_ino)
    saved = resolution["manifest"]["saved_files"][selected_index]
    saved.update(device=info.st_dev, inode=info.st_ino)
    # Replace only the not-yet-admitted fabricated manifest, before graph creation.
    (original,) = (resolution["worker"] / "objects").iterdir()
    original.unlink()
    worker_record(resolution["worker"], "manifest", resolution["attempt"], resolution["manifest"])
    _, value = candidate(resolution)
    graph = resolution_graph.initial(value)
    result = packet(value, digest(graph))
    evidence = result["evidence"]
    evidence["saved_files"][selected_index].update(device=info.st_dev, inode=info.st_ino)
    attachments = {item["digest"]: item["value"] for item in result["attachments"]}
    discovery = attachments.pop(evidence["process_scan"]["attribution_ref"])
    row = discovery["rows"][0]
    association = {
        "schema": "desktop-continuity.writer-association.v1",
        "process_ref": row["process_ref"],
        "birth_digest": row["process_ref"],
        "session_ref": "9" * 64,  # Claimed argv session is outside both selected refs.
        "saved_device": info.st_dev + (identity == "different-device"),
        "saved_inode": info.st_ino + (identity == "different-inode"),
        "disposition": "unrelated",
    }
    row.update(classification="possible-writer", association_ref=digest(association))
    attachments.update({digest(discovery): discovery, digest(association): association})
    evidence["process_scan"]["attribution_ref"] = digest(discovery)
    evidence["writers"] = [digest(association)]
    result["attachments"] = [{"digest": k, "value": v} for k, v in sorted(attachments.items())]
    objects = Objects(value["ledger"]["path"])
    if identity == "hardlink":
        with pytest.raises(ValueError):
            resolution_evidence.persist_packet(result, value, graph, objects)
        evidence.update(verdict="blocked", blockers=["writer-conflict"])
    key = resolution_evidence.persist_packet(result, value, graph, objects)
    assert objects.get(key)["blockers"] == (["writer-conflict"] if identity == "hardlink" else [])


@pytest.mark.parametrize(
    "damage", ["inode", "prefix", "unbound", "churn", "incomplete", "extra-attachment", "boot"]
)
def test_evidence_handwritten_counterexamples(resolution, damage):
    _, value = candidate(resolution)
    graph = resolution_graph.initial(value)
    result = packet(value, digest(graph))
    evidence = result["evidence"]
    if damage == "inode":
        evidence["saved_files"][0]["inode"] += 1
    elif damage == "prefix":
        evidence["saved_files"][0]["prefix_preserved"] = False
    elif damage == "unbound":
        evidence["graph_digest"] = "0" * 64
    elif damage == "churn":
        evidence["process_scan"]["names_after_ref"] = "0" * 64
    elif damage == "incomplete":
        evidence["process_scan"]["complete"] = False
    elif damage == "boot":
        evidence["boot_after"] = NEW_BOOT
    else:
        result["attachments"].append(result["attachments"][0])
    with pytest.raises(ValueError):
        resolution_evidence.persist_packet(result, value, graph, Objects(value["ledger"]["path"]))


@pytest.mark.parametrize("command", ["profile", "resolution", "inspect"])
def test_offline_routes_precede_store_locks_and_subprocess(resolution, monkeypatch, command):
    approval, value = approved(resolution, monkeypatch)
    objects = Objects(value["ledger"]["path"])
    key = digest(value) if command == "profile" else objects.get(approval)["plan_digest"]
    args = (
        ["inspect", approval, "--kind", "resolution"]
        if command == "inspect"
        else ["preview", key, "--kind", command]
    )
    monkeypatch.setattr(cli, "Store", forbidden)
    monkeypatch.setattr("niri_desktop_continuity.resolution_lock.owner_guard", forbidden)
    monkeypatch.setattr(recovery_profile, "load_profile", forbidden)
    before = {p: p.read_bytes() for p in resolution["root"].rglob("*") if p.is_file()}
    result, status = cli.run(
        cli.parser().parse_args(["--state-root", str(resolution["root"] / "does-not-exist"), *args])
    )
    assert status == 0 and result["native_effects"] == [] and result["accounting_mutations"] == []
    assert not (resolution["root"] / "does-not-exist").exists()
    assert before == {p: p.read_bytes() for p in resolution["root"].rglob("*") if p.is_file()}


def test_original_cli_marker_and_worker_corruption_block(resolution):
    _, value = candidate(resolution)
    path = resolution["root"] / "state/used" / f"{resolution['attempt']}.json"
    path.write_text("{}")
    with pytest.raises(ValueError):
        resolution_graph.initial(value)


def test_final_allows_later_normal_plan_and_retains_later_indeterminate(resolution, monkeypatch):
    approval, _ = approved(resolution, monkeypatch)
    recovery_transition.apply(approval)
    new = resolution["new"]
    root = resolution["root"]
    private_json(
        root / "config.json",
        {
            "schema": new["schema"],
            "profile_digest": digest(new),
            "interpreter": new["interpreter"],
            "endpoint": new["endpoint"],
        },
    )
    store = Store(root / "state")
    snapshot_key = resolution["original_plan"]["snapshot_digest"]
    result = recovery.propose(
        store,
        snapshot_key,
        root / "config.json",
        store.get("snapshots", snapshot_key),
        mode="additive",
        saved_set=resolution["manifest"]["saved_set"],
    )
    assert result["admission"]["status"] == "awaiting-approval"
    plan = store.get("plans", result["plan_digest"])
    approval = recovery.approval_record(plan, digest(plan))
    key = store.put("approvals", approval)
    ledger = Ledger(new)
    ledger.store.put("plans", plan)
    ledger.store.put("approvals", approval)
    pair = ledger.prepare(store, key, digest(plan))
    from niri_desktop_continuity.recovery_verification import receipt

    ledger.finish(store, pair, receipt(plan, key, None, history_complete=False, events=[]))
    private_json(resolution["worker"] / "attempts" / f"{key}.json", {"request_digest": "a" * 64})
    assert recovery_resolution.durable_view(new)["transition_state"] == "final"
    with pytest.raises(ValueError):
        ledger.available()  # Only the exact original attempt was settled, not the later failure.


@pytest.mark.parametrize(
    "damage", ["prepared", "used", "ready", "pending", "final", "archive", "cli-used", "active"]
)
def test_final_equality_never_substitutes_for_transitive_commit(resolution, monkeypatch, damage):
    approval, value = approved(resolution, monkeypatch)
    recovery_transition.apply(approval)
    objects = Objects(value["ledger"]["path"])
    if damage in ("prepared", "used", "ready", "pending", "final"):
        objects.path(damage, resolution["attempt"] if damage == "pending" else approval).write_text(
            "{}"
        )
    elif damage == "archive":
        objects.path("archives", value["old_profile"]["sha256"]).write_text("corrupt")
    elif damage == "cli-used":
        (resolution["root"] / "state/used" / f"{resolution['attempt']}.json").write_text("{}")
    else:
        private_json(recovery_profile.profile_path(), resolution["old"])
    with pytest.raises(ValueError):
        recovery_resolution.durable_view(recovery_profile.identify_profile())
    with pytest.raises(ValueError):
        Ledger(recovery_profile.identify_profile()).available()


def test_machine_hook_is_same_view_root_bound_and_expiry_is_historical(resolution, monkeypatch):
    from datetime import timedelta

    approval, _ = approved(resolution, monkeypatch)
    recovery_transition.apply(approval)
    future = resolution_candidate.now() + timedelta(days=2)
    monkeypatch.setattr(resolution_candidate, "now", lambda: future)
    hook = recovery_resolution.legacy_disposition
    result = hook(resolution["new"], resolution["worker"], resolution["attempt"], "indeterminate")
    assert result == {
        "historical_status": "indeterminate",
        "resolution_disposition": "abandoned-settled",
        "accounted_settled": True,
        "replay_authorized": False,
    }
    assert Ledger(resolution["new"]).available() is None
    with pytest.raises(ValueError):
        hook(
            resolution["new"],
            resolution["root"] / "runtime",
            resolution["attempt"],
            "indeterminate",
        )
    with pytest.raises(ValueError):
        hook(resolution["new"], resolution["worker"], resolution["attempt"], "verified")
    assert hook(resolution["new"], resolution["worker"], "0" * 64, "indeterminate") is None


@pytest.mark.parametrize("damage", ["orphan-marker", "duplicate-json", "foreign-worker-orphan"])
def test_bounded_graph_rejects_orphans_and_noncanonical_json(resolution, damage):
    if damage == "orphan-marker":
        resolution["ledger"].store.recovery_marker(
            "recovery-events", "0" * 64, {"receipt_digest": "1" * 64}
        )
    elif damage == "duplicate-json":
        (resolution["worker"] / "attempts" / f"{resolution['attempt']}.json").write_text(
            '{"request_digest":"' + "a" * 64 + '","request_digest":"' + "a" * 64 + '"}'
        )
    else:
        worker_record(
            resolution["worker"],
            "intent",
            "1" * 64,
            {"intent_ref": "2" * 64, "target_ref": "b" * 64},
            directory="events",
        )
    with pytest.raises(ValueError):
        candidate(resolution)


def test_anchor_exclusion_precedes_authoritative_profile_read(resolution, monkeypatch):
    from niri_desktop_continuity.resolution_lock import mutex, owner_guard

    with mutex(resolution["root"] / ".recovery-owner.lock"):
        monkeypatch.setattr(recovery_profile, "identify_profile", forbidden)
        with pytest.raises(BlockingIOError), owner_guard():
            forbidden()


def test_unsupported_machine_worker_format_is_not_guessed(resolution):
    private_json(
        resolution["worker"] / "objects" / ("0" * 64 + ".json"),
        {"schema": "unreviewed-owner-format"},
    )
    with pytest.raises(ValueError):
        candidate(resolution)
