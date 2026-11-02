"""Read-only serialization versus effect admission across real cooperating entrypoints."""

import hashlib
import os

import pytest
from test_core import FakeTransport, admitted
from test_recovery_orchestration import approve, command, execute, plan
from test_recovery_orchestration import fixture as fixture  # noqa: F401 - pytest fixture
from test_reopen import FakeDesktop, recipe, saved, window

from niri_desktop_continuity import operation_lock, recovery, recovery_profile, reopen
from niri_desktop_continuity.reconcile import reconcile
from niri_desktop_continuity.recovery_adapter import Adapter
from niri_desktop_continuity.store import Store

IDENTITY = {"boot_id": "fabricated", "socket_device": 1, "socket_inode": 2}
fence_path = operation_lock.fence_path


@pytest.fixture(autouse=True)
def runtime(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: root)
    monkeypatch.setattr(reopen.probe, "compositor_identity", lambda: dict(IDENTITY))


def retain_fence(identity, suffix=".restore"):
    with operation_lock.operation_lock(identity):
        path = fence_path(identity).with_suffix(suffix)
        path.write_text("{")  # Fabricated torn marker must still fence effects.
        path.chmod(0o600)
    return path


@pytest.mark.parametrize("suffix", [".restore", ".permit"])
def test_read_only_lock_ignores_fence_but_really_serializes(suffix):
    marker = retain_fence(IDENTITY, suffix)
    with operation_lock.operation_lock(IDENTITY, effectful=False) as fd:
        assert isinstance(fd, int) and os.fstat(fd)
        assert not os.get_inheritable(fd)
        for mode in (False, True):
            with pytest.raises(ValueError, match="another continuity writer"):
                with operation_lock.operation_lock(IDENTITY, effectful=mode):
                    pytest.fail("read-only acquisition did not retain flock")
    with pytest.raises(ValueError, match="fences this compositor"):
        with operation_lock.operation_lock(IDENTITY):
            pytest.fail("read-only access cleared the effect fence")
    assert marker.read_text() == "{"


def test_read_only_lock_still_validates_identity():
    with pytest.raises(ValueError, match="complete compositor"):
        with operation_lock.operation_lock({}, effectful=False):
            pytest.fail("incomplete identity admitted")


@pytest.mark.parametrize("mode", [None, 0, 1, "false"])
def test_lock_mode_requires_explicit_boolean(mode):
    with pytest.raises(ValueError, match="effectful"):
        with operation_lock.operation_lock(IDENTITY, effectful=mode):
            pytest.fail("implicit truthiness granted read-only admission")


def test_read_only_lock_refuses_a_concurrent_writer():
    with operation_lock.operation_lock(IDENTITY):
        with pytest.raises(ValueError, match="another continuity writer"):
            with operation_lock.operation_lock(IDENTITY, effectful=False):
                pytest.fail("read-only path bypassed active writer")


def test_dry_run_observer_cannot_inherit_ambient_effect_bypass(tmp_path):
    retain_fence(IDENTITY)
    store = Store(tmp_path / "state")
    key = store.put("snapshots", saved([]))
    desktop = FakeDesktop([])
    calls = []

    def observe():
        calls.append("observe")
        # On the old implementation, ContextVar ambient state yields an unlocked scope here.
        with pytest.raises(ValueError):
            with operation_lock.operation_lock(IDENTITY):
                pytest.fail("effectful callback inherited observation-only bypass")
        return saved([])

    result = reopen.reopen(store, key, desktop, apply=False, observe=observe, entries=[], users={})
    assert calls == ["observe"]
    assert result["status"] == "dry-run" and desktop.actions == []


def test_dry_run_checks_identity_before_observer(tmp_path, monkeypatch):
    monkeypatch.setattr(reopen.probe, "compositor_identity", lambda: {})
    store = Store(tmp_path / "state")
    key = store.put("snapshots", saved([]))
    calls = []
    with pytest.raises(ValueError, match="complete compositor"):
        reopen.reopen(
            store,
            key,
            FakeDesktop([]),
            apply=False,
            observe=lambda: calls.append("observe") or saved([]),
            entries=[],
            users={},
        )
    assert calls == []


@pytest.mark.parametrize("phase", ["propose", "validate", "inspect", "verify"])
@pytest.mark.parametrize("suffix", [".restore", ".permit"])
def test_recovery_read_only_consumers_under_retained_restore_fence(fixture, phase, suffix):
    data = fixture()
    key = plan(data)
    approval = approve(data, key)
    if phase in {"inspect", "verify"}:
        result, status = execute(data, approval)
        assert status == 0 and result["status"] == "verified"
    effects = data["root"] / "effects.jsonl"
    before = effects.read_bytes() if effects.exists() else None
    marker = retain_fence(data["snapshot"]["identity"], suffix)
    if phase == "propose":
        proposed = plan(data)
        assert Store(data["root"] / "state").get("plans", proposed)["intent"] == "reconstruct"
    elif phase == "validate":
        validated = recovery.validate(
            Store(data["root"] / "state"),
            key,
            data["snapshot"],
            Adapter(recovery_profile.load_profile()),
        )
        assert validated["intent"] == "reconstruct"
    else:
        observed, status = command(data, phase, approval, "--kind", "reconstruction")
        assert status == 0
        if phase == "inspect":
            assert observed["runtime_effects"] == "none" and not observed["retry_authorized"]
        else:
            assert observed["fresh_verification"] is True
    assert (effects.read_bytes() if effects.exists() else None) == before
    assert marker.read_text() == "{"
    with pytest.raises(ValueError, match="fences this compositor"):
        with operation_lock.operation_lock(data["snapshot"]["identity"]):
            pytest.fail("inspection granted subsequent effects")


@pytest.mark.parametrize("phase", ["approve", "execute"])
def test_recovery_effect_admission_still_refuses_restore_fence(fixture, phase):
    data = fixture()
    key = plan(data)
    approval = approve(data, key)
    marker = retain_fence(data["snapshot"]["identity"])
    with pytest.raises(ValueError):
        approve(data, key) if phase == "approve" else execute(data, approval)
    assert not (data["root"] / "effects.jsonl").exists()
    assert marker.exists()


def test_reconcile_consumer_refuses_retained_restore_fence(tmp_path):
    store, source, _, _, approval = admitted(tmp_path)
    marker = retain_fence(source["identity"])
    desktop = FakeTransport(source)
    with pytest.raises(ValueError, match="fences this compositor"):
        reconcile(store, approval, desktop)
    assert desktop.actions == []
    assert not store.path("used", approval).exists()
    assert marker.exists()


# --- A strict record is refused for being there -----------------------------------------------

OTHER = {**IDENTITY, "socket_inode": 3}  # the compositor before this one, in the same boot


def plant(identity, kind="chain"):
    """What the retired strict engine may have left in the runtime directory."""
    with operation_lock.operation_lock(identity, effectful=False):
        path = fence_path(identity)
    if kind == "chain":
        path.mkdir(mode=0o700)
        (path / "00000000.json").write_text('{"type": "prepared"}')
    elif kind == "empty-chain":
        path.mkdir(mode=0o700)
    elif kind == "legacy-file":
        path.write_text("{")
    elif kind == "dangling-link":
        path.symlink_to(path.with_name("gone"))
    else:
        path = path.with_suffix(".permit")
        path.write_text("{")
    return path


def source_of(store, identity):
    snapshot = saved([window(1, 1, 1, app="x", reopen=recipe("app", "x"))])
    return store.put("snapshots", {**snapshot, "identity": identity})


def apply(store, key, desktop):
    return reopen.reopen(
        store, key, desktop, apply=True, observe=lambda: saved([]), entries=[], users={}
    )


@pytest.mark.parametrize("kind", ["chain", "empty-chain", "legacy-file", "dangling-link", "permit"])
def test_any_record_for_this_compositor_refuses_effects(kind):
    plant(IDENTITY, kind)
    with pytest.raises(ValueError, match="fences this compositor"):
        with operation_lock.operation_lock(IDENTITY):
            pytest.fail("a strict record granted effects")


def test_refusal_reads_nothing_and_changes_nothing():
    path = plant(IDENTITY)
    record = path / "00000000.json"
    record.chmod(0)
    before = (sorted(p.name for p in path.iterdir()), os.lstat(record).st_mtime_ns)
    with pytest.raises(ValueError, match="fences this compositor"):
        with operation_lock.operation_lock(IDENTITY):
            pytest.fail("an unreadable record granted effects")
    assert (sorted(p.name for p in path.iterdir()), os.lstat(record).st_mtime_ns) == before


def test_a_record_of_another_compositor_does_not_block_this_one():
    plant(OTHER)
    with operation_lock.operation_lock(IDENTITY) as fd:
        assert isinstance(fd, int)


def test_a_fence_that_cannot_be_checked_refuses():
    (operation_lock.runtime_root() / "niri-desktop-continuity-locks").write_text("not a directory")
    with pytest.raises(OSError):
        operation_lock.require_clear(IDENTITY)


def test_a_missing_runtime_directory_refuses(monkeypatch, tmp_path):
    monkeypatch.setattr(operation_lock, "runtime_root", lambda: tmp_path / "gone")
    with pytest.raises(ValueError, match="runtime directory is unavailable"):
        with operation_lock.operation_lock(IDENTITY):
            pytest.fail("no runtime directory, no lock")


def test_the_fence_keeps_the_name_the_retired_engine_gave_it():
    # Handwritten canonical JSON, so a change in digest() cannot move the fence unnoticed.
    canonical = b'{"boot_id":"fabricated","socket_device":1,"socket_inode":2}'
    name = hashlib.sha256(canonical).hexdigest() + ".restore"
    assert fence_path(IDENTITY) == (
        operation_lock.runtime_root() / "niri-desktop-continuity-locks" / name
    )


def test_apply_refuses_a_source_attempted_on_the_compositor_before_this_one(tmp_path):
    # The running compositor is clear; only the source's own compositor holds a record.
    store = Store(tmp_path / "state")
    key = source_of(store, OTHER)
    plant(OTHER)
    desktop = FakeDesktop([])
    with pytest.raises(ValueError, match="fences this compositor"):
        apply(store, key, desktop)
    assert desktop.actions == []


def test_a_dry_run_still_plans_a_fenced_source(tmp_path):
    store = Store(tmp_path / "state")
    key = source_of(store, OTHER)
    plant(OTHER)
    plant(IDENTITY)
    desktop = FakeDesktop([])
    result = reopen.reopen(
        store, key, desktop, apply=False, observe=lambda: saved([]), entries=[], users={}
    )
    assert result["status"] == "dry-run" and desktop.actions == []


def test_a_clear_source_reaches_the_launch(tmp_path):
    store = Store(tmp_path / "state")
    key = source_of(store, OTHER)
    desktop = FakeDesktop([])
    apply(store, key, desktop)
    assert [action[0] for action in desktop.actions if action[0] == "spawn"] == ["spawn"]


@pytest.mark.parametrize("identity", ["not-an-object", None, {}], ids=["text", "null", "empty"])
def test_a_source_without_a_compositor_identity_keeps_its_plain_refusal(tmp_path, identity):
    store = Store(tmp_path / "state")
    key = source_of(store, identity)
    desktop = FakeDesktop([])
    with pytest.raises(ValueError, match="missing compositor identity"):
        apply(store, key, desktop)
    assert desktop.actions == []
