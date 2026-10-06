"""Real v2 validators on handwritten histories; no accepting hook or fake closure oracle."""

import json
from copy import deepcopy

import pytest
from restore_v2_fixtures import next_attempt
from test_restore_disposition_handwritten import handwritten as handwritten  # noqa: F401
from test_restore_disposition_v2 import approve, propose
from test_restore_disposition_v2 import unassociated as unassociated
from test_restore_disposition_v2_chain import finish

from niri_desktop_continuity import operation_lock, restore
from niri_desktop_continuity import restore_disposition as d
from niri_desktop_continuity import restore_history as history
from niri_desktop_continuity.restore_attempt import Attempt
from niri_desktop_continuity.store import Store


def all_refuse(s, approval, monkeypatch, tmp_path):
    monkeypatch.setattr(restore, "compositor_identity", lambda: s.identity)
    other = Store(tmp_path / "caller")
    other.put("snapshots", s.store.get("snapshots", s.source))

    def forbidden(*_):
        pytest.fail("no desktop observation/effect/retry")

    for acceptor in (
        "load",
        "admit",
        "require-clear",
        "lock",
        "attempt",
        "original",
        "other-store",
        "disposition",
    ):
        with pytest.raises((ValueError, OSError)):
            if acceptor == "lock":
                with operation_lock.operation_lock(s.identity):
                    forbidden()
            elif acceptor == "attempt":
                with Attempt(s.store, s.source, s.identity):
                    forbidden()
            elif acceptor in {"original", "other-store"}:
                restore.restore(
                    s.store if acceptor == "original" else other,
                    s.source,
                    object(),
                    apply=True,
                    observe=forbidden,
                )
            elif acceptor == "disposition":
                d.apply(s.store, approval, observer=forbidden)
            else:
                with operation_lock.operation_lock(s.identity, effectful=False, existing_only=True):
                    {
                        "load": history.load,
                        "admit": history.admit,
                        "require-clear": history.require_clear,
                    }[acceptor](s.identity)


def replace(path, mode):
    if mode == "missing":
        path.rename(path.parent.parent / (path.name + ".missing"))
    elif mode == "inode":
        data, inode = path.read_bytes(), path.stat().st_ino
        path.rename(path.parent.parent / (path.name + ".displaced"))
        path.write_bytes(data)
        path.chmod(0o600)
        assert path.stat().st_ino != inode
    elif mode == "parent":
        parent = path.parent
        old = parent.with_name(parent.name + "-displaced")
        inode, directory_inode = path.stat().st_ino, parent.stat().st_ino
        parent.rename(old)
        parent.mkdir(mode=0o700)
        for child in old.iterdir():
            child.rename(parent / child.name)
        assert path.stat().st_ino == inode and parent.stat().st_ino != directory_inode
    elif mode == "whitespace":
        path.write_bytes(path.read_bytes() + b" ")
    else:
        path.write_bytes(b"{}\n")


@pytest.mark.parametrize("kind", ["plans", "approvals", "used", "receipts", "canonical"])
@pytest.mark.parametrize("mode", ["missing", "inode", "whitespace", "parent", "semantic"])
def test_later_persisted_manifest_rejects_generated_dependency_drift_on_all_paths(
    unassociated, tmp_path, monkeypatch, kind, mode
):
    s = unassociated
    key, approval, result = finish(s)
    following = next_attempt(s, tmp_path / "following", 1)
    _, next_approval, _ = finish(following)
    refs = {
        "plans": key,
        "approvals": approval,
        "used": approval,
        "receipts": result["receipt_digest"],
    }
    path = s.directory / "00000005.json" if kind == "canonical" else s.store.path(kind, refs[kind])
    replace(path, mode)
    all_refuse(following, next_approval, monkeypatch, tmp_path)


@pytest.mark.parametrize("kind", ["plans", "approvals", "used", "receipts", "canonical"])
@pytest.mark.parametrize("mode", ["inode", "whitespace"])
def test_latest_unpinned_semantic_equivalence_before_observation_is_not_creation_inode_proof(
    unassociated, kind, mode
):
    s = unassociated
    key, approval, result = finish(s)
    refs = {
        "plans": key,
        "approvals": approval,
        "used": approval,
        "receipts": result["receipt_digest"],
    }
    path = s.directory / "00000005.json" if kind == "canonical" else s.store.path(kind, refs[kind])
    replace(path, mode)
    result = d.apply(
        s.store, approval, observer=lambda: pytest.fail("no historical native observation")
    )
    assert result["historical"] and result["historical_completion"] == "unproved"
    assert result["durability"] == "established-now"


def rewrite_latest(s, key, approval_key, result, mutate):
    """Self-consistent content-addressed graph, deliberately wrong semantics; no SUT codec."""
    plan = s.store.get("plans", key)
    receipt = s.store.get("receipts", result["receipt_digest"])
    mutate(plan, receipt)
    key = s.store.put("plans", plan)
    approval = s.store.get("approvals", approval_key)
    approval.update(plan=key, confirmation=key)
    approval_key = s.store.put("approvals", approval)
    used = {
        "schema": "desktop-continuity.restore-disposition.v2",
        "family": "exec-observed-unassociated",
        "intent": "restore-disposition",
        "approval": approval_key,
        "plan": key,
    }
    path = s.store.path("used", approval_key)
    path.write_text(json.dumps(used) + "\n")
    path.chmod(0o600)
    receipt.update(plan=key, approval=approval_key)
    receipt_key = s.store.put("receipts", receipt)
    ending = s.directory / "00000005.json"
    record = json.loads(ending.read_text())
    record["receipt"] = receipt_key
    ending.write_text(json.dumps(record) + "\n")
    return approval_key


@pytest.mark.parametrize(
    "change",
    [
        "bool-owned",
        "float-protected",
        "bool-process",
        "duplicate-process",
        "missing-process",
        "foreign-boot",
        "controller-overlap",
        "image",
        "argv",
        "cwd",
        "segment",
        "extra-manifest",
        "missing-manifest",
        "duplicate-manifest",
        "family",
        "schema",
        "unknown-plan",
        "association",
        "layout",
        "retry-number",
        "unknown-receipt",
        "process-reference",
    ],
)
def test_closed_historical_semantics_reject_self_consistent_but_false_graph(
    unassociated, tmp_path, monkeypatch, change
):
    s = unassociated
    key, approval, result = finish(s)

    def mutate(plan, receipt):
        c = plan["current"]
        if change == "bool-owned":
            c["owned_window_id"] = True
        elif change == "float-protected":
            c["protected_window_ids"][0] = 70.0
        elif change == "bool-process":
            c["processes"][-1]["start_ticks"] = True
        elif change == "duplicate-process":
            c["processes"].append(deepcopy(c["processes"][-1]))
        elif change == "missing-process":
            c["processes"].pop(0)
        elif change == "foreign-boot":
            c["processes"][0]["boot_id"] = "foreign"
        elif change == "controller-overlap":
            c["controller_pids"] = [2000]
        elif change == "image":
            c["running_image"]["inode"] += 1
        elif change == "argv":
            c["argv_digest"] = "0" * 64
        elif change == "cwd":
            c["cwd"]["process_directory"]["inode"] += 1
        elif change == "segment":
            plan["segment"]["count"] = 5.0
        elif change == "extra-manifest":
            plan["manifest"].append(plan["witness"]["client_exit"])
        elif change == "missing-manifest":
            plan["manifest"].pop()
        elif change == "duplicate-manifest":
            plan["manifest"].append(deepcopy(plan["manifest"][0]))
        elif change == "family":
            plan["family"] = "other"
        elif change == "schema":
            plan["schema"] = "desktop-continuity.restore-disposition.v1"
        elif change == "unknown-plan":
            plan["pending"] = "0" * 64
        elif change == "association":
            receipt["historical_association"] = "proved"
        elif change == "layout":
            receipt["historical_layout"] = "verified"
        elif change == "retry-number":
            receipt["retry_authorized"] = 0
        elif change == "unknown-receipt":
            receipt["restored_window_id"] = 12000
        else:
            receipt["process_receipt"] = "0" * 64

    approval = rewrite_latest(s, key, approval, result, mutate)
    all_refuse(s, approval, monkeypatch, tmp_path)


@pytest.mark.parametrize(
    "change",
    ["error", "type", "effect", "association", "width", "entry-alias", "diagnostic", "exit"],
)
def test_only_exact_original_unassociated_witness_qualifies(unassociated, change):
    s = unassociated
    receipt = s.store.get("receipts", s.interrupted)
    if change == "error":
        receipt["error"] = "another failure"
    elif change == "type":
        receipt["error_type"] = "RuntimeError"
    elif change == "effect":
        receipt["effects"] = [["focus-window", "1"]]
    elif change == "association":
        receipt["windows"][0]["restored_window_id"] = 12000
    elif change == "width":
        receipt["windows"][0]["geometry_coverage"]["width"] = "verified"
    elif change == "entry-alias":
        receipt["windows"][0]["window_id"] = True
    elif change == "diagnostic":
        receipt["final_observation"] = {"unavailable": 1}
    else:
        s.exit_file.write_text("0\n")
    s.interrupted = s.store.put("receipts", receipt)
    s.result.write_text(
        json.dumps({"snapshot_digest": s.source, "receipt_digest": s.interrupted, **receipt})
    )
    with pytest.raises(ValueError):
        propose(s)
    assert not list((s.store.root / "plans").iterdir())


@pytest.mark.parametrize("stage", ["approve", "apply"])
@pytest.mark.parametrize("change", ["absent", "surplus", "protected-id", "focus", "unknown-pid"])
def test_fresh_partition_changes_refuse_without_native_effects(unassociated, stage, change):
    s = unassociated
    key = propose(s)
    approval = approve(s, key) if stage == "apply" else None
    value = s.observe()
    windows = value["state"]["windows"]
    if change == "absent":
        windows.pop()
    elif change == "surplus":
        other = deepcopy(windows[-1])
        other["id"] = 13000
        other["layout"]["pos_in_scrolling_layout"] = [4, 1]
        windows.append(other)
    elif change == "protected-id":
        windows[0]["pid"] = 2000
    elif change == "focus":
        value["coherent"] = False
    else:
        windows[0]["pid"] = None
    s.observe = lambda: deepcopy(value)
    with pytest.raises((ValueError, TypeError)):
        approve(s, key) if stage == "approve" else d.apply(s.store, approval, observer=s.observe)
    assert not list((s.store.root / "used").iterdir())
    assert len(list(s.directory.iterdir())) == 5


@pytest.mark.parametrize(
    "kind", ["snapshot", "process", "interrupted", "result", "exit", "payload"]
)
@pytest.mark.parametrize("mode", ["missing", "inode", "whitespace"])
def test_original_transitive_evidence_never_reconstructed_or_rebased(
    unassociated, tmp_path, monkeypatch, kind, mode
):
    s = unassociated
    finish(s)
    following = next_attempt(s, tmp_path / "following", 1)
    _, approval, _ = finish(following)
    row = s.store.get("receipts", s.interrupted)["windows"][0]
    first = json.loads((s.directory / "00000000.json").read_text())
    path = {
        "snapshot": s.store.path("snapshots", s.source),
        "process": s.store.path("receipts", row["process_receipt"]),
        "interrupted": s.store.path("receipts", s.interrupted),
        "result": s.result,
        "exit": s.exit_file,
        "payload": s.store.path("receipts", first["receipt"]),
    }[kind]
    replace(path, mode)
    all_refuse(following, approval, monkeypatch, tmp_path)


@pytest.mark.parametrize("kind", ["canonical", "receipt"])
def test_prior_ordinary_terminal_is_a_real_bound_dependency(
    unassociated, tmp_path, monkeypatch, kind
):
    s = unassociated
    finish(s)
    ordinary = next_attempt(s, tmp_path / "ordinary", 1, ordinary=True)
    following = next_attempt(s, tmp_path / "following", 2)
    _, approval, _ = finish(following)
    path = s.directory / "00000008.json"
    if kind == "receipt":
        path = ordinary.store.path("receipts", json.loads(path.read_text())["receipt"])
    replace(path, "inode")
    all_refuse(following, approval, monkeypatch, tmp_path)


def test_latest_canonical_numeric_origin_alias_is_not_a_closed_v2_envelope(
    unassociated, tmp_path, monkeypatch
):
    s = unassociated
    _, approval, _ = finish(s)
    path = s.directory / "00000005.json"
    value = json.loads(path.read_text())
    value["origin"]["pin"]["device"] = float(value["origin"]["pin"]["device"])
    path.write_text(json.dumps(value))
    all_refuse(s, approval, monkeypatch, tmp_path)
