"""V2 stage IO using existing Store serialization/O_EXCL and held interval bindings."""

import json

from . import restore_history as history
from .model import digest
from .restore_disposition_dependencies import Bindings
from .restore_disposition_failure import release
from .restore_reader import DependencyReader, ReaderStore, same
from .store import Store


def encoded(value, *, kind):
    options = (
        {"indent": 2, "sort_keys": True, "allow_nan": False}
        if kind == "artifact"
        else {"sort_keys": True, "allow_nan": False}
        if kind == "canonical"
        else {}
    )
    return (json.dumps(value, **options) + "\n").encode()


def put(store, reader, kind, value):
    key = digest(value)
    try:
        store._create(store.path(kind, key), encoded(value, kind="artifact"))
    except FileExistsError:
        # Latest unpinned semantic equivalence MAY accept before first observation. Existing
        # interval/persisted pins are still enforced by the reader; never overwrite/repair.
        pass
    actual, _ = reader.artifact(store, kind, key)
    if not same(actual, value):
        raise ValueError("generated disposition artifact differs")
    return key


class WriterView(ReaderStore):
    """Only the existing one-use consume writer; its internal approval read is mediated."""

    def __init__(self, store, reader):
        super().__init__(store, reader)
        self._create = store._create

    consume = Store.consume


def fresh_chain(identity, chain, pins, *, staged=None):
    """Post-barrier NEW raw and semantic pass, including an explicitly known staged ending.

    Pins here come from the operation's already derived closure plus artifacts it just created,
    NEVER from walking operator-supplied manifest paths. Staging changes no authority yet.
    """
    reader = DependencyReader()
    try:
        reader.reserve_pins(pins)
        for pin in pins:
            (reader.evidence if "digest" in pin else reader.raw)(pin["path"], expected=pin)
        fresh = []
        for _, _, store, refs in chain:
            record, rp = reader.evidence(refs[0]["path"], expected=refs[0])
            view = ReaderStore(store, reader)
            payload, pp = reader.artifact(view, "receipts", record["receipt"])
            fresh.append((record, payload, view, [rp, pp]))
        if staged is not None:
            store, path = staged
            record, rp = reader.evidence(path)
            view = ReaderStore(store, reader)
            payload, pp = reader.artifact(view, "receipts", record["receipt"])
            fresh.append((record, payload, view, [rp, pp]))
        # Without a staged ending, caller-created plan/approval are known additional references,
        # not members of the historical prefix's manifest. With it, the complete closure closes.
        result = history.validate(identity, fresh, reader=reader if staged else None)
        Bindings(reader.manifest()).require(pins)
        return reader, fresh, result
    except BaseException as primary:
        release(primary, [reader.close])
        raise
