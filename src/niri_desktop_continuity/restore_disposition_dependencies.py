"""Closed-history dependency bindings; readers mediate IO, never a supplied manifest."""

from pathlib import Path

from . import restore_retained as retained
from .restore_reader import absolute, matches, pin_valid, same


def file(store, path, *, raw=False):
    reader = getattr(store, "reader", None)
    value, pin = (
        (reader.raw(path) if raw else reader.evidence(path))
        if reader
        else (retained.raw(path) if raw else retained.evidence(path))
    )
    # V1 persisted the original absolute spelling; keep that historical grammar unchanged.
    return value, {**pin, "path": str(Path(path).absolute())}


def artifact(store, kind, key):
    value, pin = file(store, store.path(kind, key))
    if not isinstance(value, dict) or (kind != "used" and pin["digest"] != key):
        raise ValueError("invalid disposition dependency content address")
    return value, pin


class Bindings:
    def __init__(self, pins=()):
        self.values = {}
        self.extend(pins)

    def add(self, pin):
        pin_valid(pin)
        pin = {**pin, "path": absolute(pin["path"])}
        previous = self.values.get(pin["path"])
        if previous is not None:
            matches(previous, pin)  # BEFORE path dedup; never dedup different Stores by digest.
            pin = {**previous, **pin}
        self.values[pin["path"]] = pin

    def extend(self, pins):
        for pin in pins:
            self.add(pin)

    def manifest(self):
        return [self.values[p] for p in sorted(self.values)]

    def require(self, pins):
        # Supplied pins are assertions, not a discovery mechanism or authority to open paths.
        actual = Bindings(pins)
        for path, pin in actual.values.items():
            if path not in self.values:
                raise ValueError("unreferenced or missing expected dependency")
            matches(self.values[path], pin)

    def exact(self, pins):
        if not same(self.manifest(), pins):
            raise ValueError("manifest is not the exact derived dependency closure")
