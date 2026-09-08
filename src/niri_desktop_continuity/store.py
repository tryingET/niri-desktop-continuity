"""Private immutable artifacts, durable atomic pointers and single-use receipts."""

from __future__ import annotations

import json
import os
import re
import stat
import uuid
from pathlib import Path

from .model import digest, readiness, require_snapshot, verify

RECOVERY_MARKERS = {"recovery-prepared", "recovery-ready", "recovery-terminal", "recovery-events"}
KINDS = {"snapshots", "plans", "approvals", "used", "receipts", "previews"} | RECOVERY_MARKERS
HEX = re.compile(r"[0-9a-f]{64}\Z")


def default_root() -> Path:
    return (
        Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        / "niri-desktop-continuity"
    )


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path: Path, *, create=True) -> None:
    path = path.absolute()
    # Establish every edge root-to-leaf, never mkdir(parents=True): each new name
    # must be durable in its parent before any descendant record can grant effects.
    for directory in (*reversed(path.parents), path):
        if create:
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError:
                pass
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("refusing symlink state directory")
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in {0, os.getuid()}
            or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)
        ):
            raise ValueError("unsafe state directory ancestry")
        if directory == path and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("state directory must be owned by you and mode 0700")
        if create:
            # Also sync existing edges: they may have survived an earlier interrupted
            # mkdir without its parent fsync. This does not repair permissions/content.
            sync_directory(directory)
            if directory.parent != directory:
                sync_directory(directory.parent)


def check_file(path: Path) -> None:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("artifact must be a private regular file owned by the current user")
    if info.st_size > 16 * 1024 * 1024:
        raise ValueError("artifact exceeds 16 MiB bound")


class Store:
    def __init__(self, root: Path | None = None, *, create=True):
        self.root = (root or default_root()).absolute()
        private_directory(self.root, create=create)
        if create:
            for kind in sorted(KINDS):
                private_directory(self.root / kind)

    def path(self, kind: str, key: str) -> Path:
        if kind not in KINDS or not HEX.fullmatch(key):
            raise ValueError("invalid artifact kind or content address")
        return self.root / kind / f"{key}.json"

    @staticmethod
    def _sync_dir(path: Path) -> None:
        sync_directory(path)

    def _create(self, path: Path, content: bytes) -> None:
        if len(content) > 16 * 1024 * 1024:
            raise ValueError("artifact exceeds 16 MiB bound")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        self._sync_dir(path.parent)

    def put(self, kind: str, value: dict) -> str:
        key = digest(value)
        path = self.path(kind, key)
        content = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        try:
            self._create(path, content)
        except FileExistsError:
            if self.get(kind, key) != value:
                raise ValueError("immutable artifact conflict") from None
        return key

    def get(self, kind: str, key: str) -> dict:
        path = self.path(kind, key)
        check_file(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            value = json.load(stream)
        if not isinstance(value, dict) or digest(value) != key:
            raise ValueError("artifact integrity mismatch")
        return value

    def pointer(self, name: str, key: str | None = None) -> str | None:
        if name not in {"latest-observed", "last-display-valid", "last-layout-verified"}:
            raise ValueError("invalid state pointer")
        path = self.root / f"{name}.json"
        if key is None:
            if not path.exists():
                return None
            check_file(path)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as stream:
                value = json.load(stream)["snapshot_digest"]
            self.get("snapshots", value)
            return value
        self.get("snapshots", key)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}")
        self._create(temporary, (json.dumps({"snapshot_digest": key}) + "\n").encode())
        os.replace(temporary, path)
        self._sync_dir(path.parent)
        return key

    def save_snapshot(self, snapshot: dict) -> str:
        require_snapshot(snapshot)
        key = self.put("snapshots", snapshot)
        self.pointer("latest-observed", key)
        if readiness(snapshot)["ready"]:
            self.pointer("last-display-valid", key)
        return key

    def save_verification(self, desired: dict, actual: dict) -> tuple[str, dict]:
        report = verify(desired, actual)
        record = {
            **report,
            "desired_digest": self.put("snapshots", desired),
            "actual_digest": self.put("snapshots", actual),
        }
        receipt = self.put("receipts", record)
        if report["layout_verified"]:
            self.pointer("last-layout-verified", record["actual_digest"])
        return receipt, report

    def consume(self, approval_key: str, record: dict) -> None:
        # The marker name binds the approval, not the marker content. O_EXCL is the replay fence.
        self.get("approvals", approval_key)
        self._create(self.path("used", approval_key), (json.dumps(record) + "\n").encode())

    def recovery_marker(self, kind: str, key: str, value: dict | None = None):
        if kind not in RECOVERY_MARKERS:
            raise ValueError("invalid reconstruction marker")
        path = self.path(kind, key)
        if value is not None:
            self._create(path, (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode())
            return value
        from .recovery_profile import read_private

        return read_private(path)

    def write_preview(self, key: str, suffix: str, content: str) -> Path:
        self.path("snapshots", key)  # validate digest shape; preview can also address a plan
        if suffix not in {"html", "svg"}:
            raise ValueError("invalid preview format")
        path = self.root / "previews" / f"{key}.{suffix}"
        try:
            self._create(path, content.encode())
        except FileExistsError:
            check_file(path)
            if path.read_text() != content:
                raise ValueError("preview is immutable; regenerate for a new capture") from None
        return path
