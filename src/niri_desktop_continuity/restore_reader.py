"""Per-pass v2 dependency IO budgets. No settlement, native observation or approval authority."""

import os
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from pathlib import Path

from . import restore_reader_io as bounded
from . import restore_retained as retained
from .model import digest
from .restore_disposition_failure import release
from .restore_reader_io import identity
from .store import HEX, private_directory, sync_artifact

FILE_BYTES = 16 * 1024 * 1024
RAW_FIELDS = "path directory device inode sha256 length".split()


@dataclass(frozen=True)
class Limits:
    files: int = 32768
    raw_bytes: int = 512 * 1024 * 1024
    file_bytes: int = FILE_BYTES

    def __post_init__(self):
        if any(type(n) is not int or n < 0 for n in (self.files, self.raw_bytes, self.file_bytes)):
            raise ValueError("invalid dependency limits")
        if self.files > 32768 or self.raw_bytes > 512 * 1024 * 1024 or self.file_bytes > FILE_BYTES:
            raise ValueError("injected limits cannot enlarge v2 bounds")


@dataclass
class Counters:
    # Routing has its OWN allowance, once across the whole pass, not per v2 boundary.
    routing_reads: int = 0
    routing_bytes: int = 0
    routing_parses: int = 0
    discriminator_reads: int = 0
    discriminator_bytes: int = 0
    discriminator_parses: int = 0
    validation_passes: int = 0
    # Sums of per-pass unique reservations; not global unique bytes or a RAM limit.
    validation_reserved_files: int = 0
    validation_reserved_bytes: int = 0
    validation_reads: int = 0
    validation_bytes: int = 0
    validation_read_calls: int = 0
    validation_requested_bytes: int = 0
    validation_parses: int = 0
    memo_hits: int = 0
    legacy_reads: int = 0
    legacy_bytes: int = 0
    legacy_parses: int = 0
    # Store owns barrier IO. These count attempts/bound bytes, NOT completed read syscalls.
    barrier_attempts: int = 0
    barrier_bound_bytes: int = 0


def absolute(path):
    # Normalize spelling, not symlinks. Private-directory checks reject symlink ancestry.
    original = Path(path).absolute()
    if ".." in original.parts:
        # Do not collapse a symlink/.. traversal into an apparently safe different path.
        private_directory(original.parent, create=False)
    return str(Path(os.path.abspath(original)))


def same(a, b):
    return digest(a) == digest(b)  # Do not let bool/int/float alias identity fields.


def pin_valid(pin):
    if not isinstance(pin, dict) or set(pin) not in (set(RAW_FIELDS), {*RAW_FIELDS, "digest"}):
        raise ValueError("invalid dependency binding")
    if not isinstance(pin["path"], str) or not Path(pin["path"]).is_absolute():
        raise ValueError("absolute dependency path required")
    directory = pin["directory"]
    if not isinstance(directory, dict) or set(directory) != {"device", "inode"}:
        raise ValueError("invalid dependency directory binding")
    if any(
        type(n) is not int or n < 0
        for n in (
            pin["device"],
            pin["inode"],
            pin["length"],
            directory["device"],
            directory["inode"],
        )
    ) or any(
        not isinstance(pin[k], str) or not HEX.fullmatch(pin[k])
        for k in ("sha256", "digest")
        if k in pin
    ):
        raise ValueError("invalid dependency identity or digest")


def matches(actual, expected):
    # Check all common bindings BEFORE path dedup; a raw reader need not decode JSON.
    if any(not same(actual[k], v) for k, v in expected.items() if k in actual):
        raise ValueError("conflicting dependency raw bytes or identity")


def _guarded(method):
    """All public pass operations retire on ANY failure, preserving the same exception."""

    @wraps(method)
    def call(self, *args, **kwargs):
        try:
            self.check()
            return method(self, *args, **kwargs)
        except BaseException as primary:
            release(primary, [self.close])
            raise

    return call


class DependencyReader:
    """One validation pass only. Every unseen path reserves stat size BEFORE read/parse.

    Parsed memo entries never cross a barrier/pass. The reader proves IO bindings/bounds,
    not reference completeness, backward history semantics, or family eligibility.
    """

    def __init__(self, *, limits=None, counters=None):
        self.limits = limits if limits is not None else Limits()
        self.counters = counters if counters is not None else Counters()
        self.counters.validation_passes += 1
        self.reservations, self.bindings, self.cache, self.parsed = {}, {}, {}, {}
        self.unique_bytes = 0
        self.closed = False
        self.expected = {}

    def check(self):
        if self.closed:
            raise ValueError("dependency pass is closed; fresh validation required")

    def close(self):
        if self.closed:
            return
        self.closed = True
        release(None, [self.cache.clear, self.parsed.clear])

    @_guarded
    def capacity(self, count, size):
        if count > self.limits.files or size > self.limits.raw_bytes:
            self.close()
            raise ValueError("v2 dependency budget exceeded")

    @_guarded
    def expect(self, pins):
        # Assertions for a NEW pass, not discovery or reservations of future references.
        # A fixed-prefix pass may consume only a subset of a whole-history interval's pins.
        for pin in pins:
            pin_valid(pin)
            pin = {**pin, "path": absolute(pin["path"])}
            path = pin["path"]
            for known in (self.expected.get(path), self.bindings.get(path)):
                if known is not None:
                    matches(known, pin)
            self.expected[path] = {**self.expected.get(path, {}), **pin}

    @_guarded
    def reserve(self, path, *, expected=None):
        return self._reserve(path, expected=expected)

    def _reserve(self, path, *, expected):
        path = absolute(path)
        seeded = self.expected.get(path)
        if seeded is not None:
            if expected is not None:
                pin_valid(expected)
                matches(seeded, {**expected, "path": absolute(expected["path"])})
            expected = {**seeded, **(expected or {}), "path": path}
        if expected is not None:
            pin_valid(expected)
            expected = {**expected, "path": absolute(expected["path"])}
            if expected["path"] != path:
                raise ValueError("dependency path differs from binding")
            if path in self.bindings:
                matches(self.bindings[path], expected)
        signature = identity(path)
        info, parent = signature
        size = info[2]
        if size > self.limits.file_bytes:
            raise ValueError("v2 dependency file budget exceeded")
        if expected is not None:
            matches(
                {
                    "path": path,
                    "device": info[0],
                    "inode": info[1],
                    "length": size,
                    "directory": dict(zip(("device", "inode"), parent, strict=True)),
                },
                expected,
            )
        if path in self.reservations:
            if signature != self.reservations[path]:
                raise ValueError("dependency changed after reservation")
        else:
            self.capacity(len(self.reservations) + 1, self.unique_bytes + size)
            self.reservations[path] = signature
            self.unique_bytes += size
            self.counters.validation_reserved_files += 1
            self.counters.validation_reserved_bytes += size
        if expected is not None:
            self.bindings[path] = {**self.bindings.get(path, {}), **expected}
        return path

    @_guarded
    def reserve_pins(self, pins):
        for pin in pins:
            self.reserve(pin["path"], expected=pin)

    @_guarded
    def raw(self, path, *, expected=None):
        path = self.reserve(path, expected=expected)
        if path in self.cache:
            self.counters.memo_hits += 1
        else:
            self.counters.validation_reads += 1
            data, pin = bounded.raw(path, self.reservations[path], self.counters)
            if identity(path) != self.reservations[path]:
                raise ValueError("dependency substituted or grew during materialization")
            if path in self.bindings:
                matches(pin, self.bindings[path])
            self.bindings[path] = {**self.bindings.get(path, {}), **pin}
            self.cache[path] = (data, pin)
        data, pin = self.cache[path]
        return data, deepcopy(pin)

    @_guarded
    def evidence(self, path, *, expected=None):
        data, pin = self.raw(path, expected=expected)
        path = pin["path"]
        if path not in self.parsed:
            self.counters.validation_parses += 1
            value = retained.json_bytes(data)
            pin = {**pin, "digest": digest(value)}
            matches(pin, self.bindings[path])
            self.bindings[path] = pin
            self.parsed[path] = (value, pin)
        return deepcopy(self.parsed[path])

    @_guarded
    def artifact(self, store, kind, key):
        value, pin = self.evidence(store.path(kind, key))
        if kind != "used" and pin["digest"] != key:
            raise ValueError("dependency content address mismatch")
        return value, pin

    @_guarded
    def _bind_store(self, store):
        return store.root, store.path

    @_guarded
    def get(self, store, kind, key):
        value, _ = self.artifact(store, kind, key)
        if not isinstance(value, dict):
            raise ValueError("artifact must be an object")
        return value

    @_guarded
    def manifest(self):
        self.check()
        if set(self.reservations) != set(self.cache):
            raise ValueError("unread reserved dependencies are not validated evidence")
        return [deepcopy(self.bindings[p]) for p in sorted(self.bindings)]

    @_guarded
    def barriers(self):
        """Retire this memo even on failure. Return bindings, never admission authority.

        Caller must perform a NEW semantic validation pass with a NEW reader, bound to
        these pins, after successful barriers. No parsed object from this pass is reusable.
        """
        pins = self.manifest()
        self.close()
        for pin in pins:
            self.counters.barrier_attempts += 1
            self.counters.barrier_bound_bytes += pin["length"]
            sync_artifact(pin)
        return pins

    @_guarded
    def reserve_commit(self, artifacts, *, history_count, record_limit=4096):
        """Check caller-supplied complete prospective bytes; no consume/write/capability.

        Despite the compatibility name, this is a capacity CHECK, not a retained reservation.
        The v2 lifecycle supplies the complete remaining future set after binding existing
        artifacts, and repeats the check LAST with no expanded dependencies before consumption.
        This primitive alone cannot certify completeness or reserve future space.
        """
        self.check()
        if (
            type(history_count) is not int
            or history_count < 0
            or type(record_limit) is not int
            or not 0 < record_limit <= 4096
            or history_count + 1 > record_limit
        ):
            self.close()
            raise ValueError("no prospective canonical record slot")
        prospective = {}
        for path, data in artifacts:
            path = absolute(path)
            private_directory(Path(path).parent, create=False)
            if not isinstance(data, bytes) or len(data) > self.limits.file_bytes:
                self.close()
                raise ValueError("prospective artifact exceeds file budget")
            if path in prospective and prospective[path] != data:
                raise ValueError("conflicting prospective path bytes")
            prospective[path] = data
        for path, data in prospective.items():
            if os.path.lexists(path):
                actual, _ = self.raw(path)
                if actual != data:
                    raise ValueError("prospective artifact conflicts with retained bytes")
        sizes = {p: s[0][2] for p, s in self.reservations.items()}
        sizes.update({p: len(data) for p, data in prospective.items() if p not in sizes})
        self.capacity(len(sizes), sum(sizes.values()))
        return {
            "unique_files": len(sizes),
            "unique_bytes": sum(sizes.values()),
            "canonical_records": history_count + 1,
        }


class ReaderStore:
    """Budgeted Store view; disposition_dependencies also mediates legacy file helpers."""

    def __init__(self, store, reader):
        self.reader = reader
        self.root, self.path = reader._bind_store(store)

    def get(self, kind, key):
        return self.reader.get(self, kind, key)
