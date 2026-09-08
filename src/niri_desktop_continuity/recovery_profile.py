"""Owner-established compatibility profile; caller config cannot choose trust or ledger roots."""

from __future__ import annotations

import hashlib
import os
import pwd
import stat
from pathlib import Path

from .model import digest
from .recovery_protocol import (
    ADDITIVE,
    CONTRACT,
    VERSION2,
    RecoveryRefusal,
    decode,
    fields,
    hexkey,
    require,
    version,
)


def profile_path():
    # Deliberately ignore HOME, XDG_* and --state-root for the owner trust anchor.
    return (
        Path(pwd.getpwuid(os.getuid()).pw_dir)
        / ".config/niri-desktop-continuity/recovery-profile.json"
    )


def safe_path(path, *, private=False):
    require(type(path) is str and Path(path).is_absolute())
    value = Path(path)
    require(str(value) == path and ".." not in value.parts)
    for parent in (value, *value.parents):
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode))
        if parent != value:
            require(stat.S_ISDIR(info.st_mode) and info.st_uid in {0, os.getuid()})
            # Shared sticky ancestors (e.g. TMPDIR in tests) cannot replace owned children.
            require(not info.st_mode & 0o022 or bool(info.st_mode & stat.S_ISVTX))
    info = value.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    require(info.st_uid in ({os.getuid()} if private else {0, os.getuid()}))
    require(not info.st_mode & (0o077 if private else 0o022))
    return value


def read_private(path):
    path = safe_path(str(path), private=True)
    require(path.stat().st_size <= 1024 * 1024)
    return decode(path.read_bytes())


def pin_spec(value):
    fields(value, ("path", "sha256"))
    path = value["path"]
    require(
        type(path) is str
        and Path(path).is_absolute()
        and str(Path(path)) == path
        and ".." not in Path(path).parts
    )
    hexkey(value["sha256"])


def pin_file(value):
    pin_spec(value)
    path = safe_path(value["path"])
    before = path.stat()
    require(before.st_size <= 512 * 1024 * 1024)
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    require(
        (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size)
        == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)
    )
    require(actual == value["sha256"])


def load_profile(config=None, *, expected=None):
    try:
        return _load_profile(config, expected=expected)
    except FileNotFoundError:
        raise RecoveryRefusal("reconstruction-adapter-unavailable") from None


def identify_profile():
    """Read the safe fixed trust anchor/ledger identity, never executable admission.

    No caller root/config fallback; pin specifications remain strictly validated data.
    Every actual adapter invocation must separately pass load_profile().
    """
    profile = read_private(profile_path())
    schema = version(profile["schema"])
    fields(
        profile,
        (
            "schema",
            "contract",
            "reviewed",
            "interpreter",
            "endpoint",
            "sources",
            "ledger_root",
            "legacy_locations",
        )
        + (("platform",) if schema in (VERSION2, ADDITIVE) else ()),
    )
    require(profile["contract"] == CONTRACT and profile["reviewed"] is True)
    require(type(profile["sources"]) is list and 1 <= len(profile["sources"]) <= 256)
    if schema in (VERSION2, ADDITIVE):
        fields(profile["platform"], ("kind", "pins"))
        require(profile["platform"]["kind"] == "owner-trusted-application-platform")
        require(
            type(profile["platform"]["pins"]) is list
            and 1 <= len(profile["platform"]["pins"]) <= 256
        )
    pins = profile_pins(profile)
    for pin in pins:
        pin_spec(pin)
    paths = [pin["path"] for pin in pins]
    require(len(paths) == len(set(paths)))
    for key in ("ledger_root",):
        path = profile[key]
        require(
            type(path) is str
            and Path(path).is_absolute()
            and str(Path(path)) == path
            and ".." not in Path(path).parts
        )
        # Owner provisions the ledger; no freely chosen root is created on invocation.
        root = Path(path)
        require(root.is_dir())
        for parent in (root, *root.parents):
            info = parent.lstat()
            require(
                stat.S_ISDIR(info.st_mode)
                and not stat.S_ISLNK(info.st_mode)
                and info.st_uid in {0, os.getuid()}
            )
            require(not info.st_mode & 0o022 or bool(info.st_mode & stat.S_ISVTX))
        require(root.stat().st_uid == os.getuid() and not root.stat().st_mode & 0o077)
    locations = profile["legacy_locations"]
    require(type(locations) is list and len(locations) <= 256)
    require(
        all(
            type(p) is str and Path(p).is_absolute() and ".." not in Path(p).parts
            for p in locations
        )
    )
    require(locations == sorted(set(locations)))
    return profile


def _load_profile(config=None, *, expected=None):
    profile = identify_profile()
    for pin in profile_pins(profile):
        pin_file(pin)
    require(os.access(profile["interpreter"]["path"], os.X_OK))
    key = digest(profile)
    if expected is not None:
        require(key == hexkey(expected))
    if config is not None:
        configured = read_private(config)
        fields(configured, ("schema", "profile_digest", "interpreter", "endpoint"))
        require(
            configured
            == {
                "schema": profile["schema"],
                "profile_digest": key,
                "interpreter": profile["interpreter"],
                "endpoint": profile["endpoint"],
            }
        )
    return profile


def profile_pins(profile):
    return [
        profile["interpreter"],
        profile["endpoint"],
        *profile["sources"],
        *(profile["platform"]["pins"] if profile["schema"] in (VERSION2, ADDITIVE) else []),
    ]
