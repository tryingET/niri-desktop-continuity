"""Read-only restore source selection; never repair pointers or relax restore admission."""

from __future__ import annotations

from dataclasses import dataclass

from .model import readiness, require_snapshot
from .store import check_file

DISPLAY_UNAVAILABLE = {
    "no-usable-output",
    "no-active-workspace",
    "window-on-unavailable-workspace",
}


@dataclass(frozen=True)
class Selection:
    digest: str
    snapshot: dict
    source_pointer: str | None
    fallback_reason: str | None = None
    latest_identity: dict | None = None

    def metadata(self):
        return {
            "source_pointer": self.source_pointer,
            "snapshot_digest": self.digest,
            "fallback_reason": self.fallback_reason,
        }

    def same_instance(self, identity):
        # A disabled display in this instance must not resurrect an older desktop.
        return self.snapshot["identity"] == identity or self.latest_identity == identity


def _pointer(store, name):
    path = store.root / f"{name}.json"
    try:
        path.lstat()
    except FileNotFoundError:
        return None  # Only genuine pointer absence permits fallback.
    # Store.pointer uses exists(): explicitly reject even a dangling symlink here.
    check_file(path)
    key = store.pointer(name)
    if key is None:
        raise ValueError("restore pointer disappeared during selection")
    return key


def _snapshot(store, key):
    value = store.get("snapshots", key)
    require_snapshot(value)
    return value


def _require_ready(value):
    if not readiness(value)["ready"]:
        raise ValueError("saved snapshot is not display-valid; refusing to reopen from it")


def select_snapshot(store, explicit=None):
    """Prefer ready latest; fallback only on display unavailability or pointer absence.

    Artifact, permission, schema and pointer errors propagate without another selection.
    Cached display metadata is not evidence; readiness is recomputed from the source.
    """
    if explicit is not None:
        # Preserve login's same-instance skip before restore checks display readiness.
        # Explicit selection never consults pointers or acquires fallback semantics.
        return Selection(explicit, _snapshot(store, explicit), None)

    latest = _pointer(store, "latest-observed")
    latest_identity = None
    reason = "latest-pointer-missing"
    if latest is not None:
        value = _snapshot(store, latest)
        display = readiness(value)
        if display["ready"]:
            return Selection(latest, value, "latest-observed")
        if not set(display["reasons"]) <= DISPLAY_UNAVAILABLE:
            _require_ready(value)  # Incoherence is not a display-unavailable fallback.
        # Readiness also labels missing references as an unavailable workspace.
        # Invalid references must not authorize selection of a different desktop.
        workspace_ids = {workspace["id"] for workspace in value["workspaces"]}
        for window in value["windows"]:
            reference = window.get("workspace_id")
            if type(reference) is not int or reference not in workspace_ids:
                raise ValueError("invalid saved window workspace reference; refusing fallback")
        latest_identity = value["identity"]
        reason = "latest-display-unavailable"

    fallback = _pointer(store, "last-display-valid")
    if fallback is None:
        if latest is None:
            raise ValueError("no saved desktop to reopen")
        raise ValueError("no display-valid saved desktop to reopen")
    value = _snapshot(store, fallback)
    _require_ready(value)
    return Selection(fallback, value, "last-display-valid", reason, latest_identity)
