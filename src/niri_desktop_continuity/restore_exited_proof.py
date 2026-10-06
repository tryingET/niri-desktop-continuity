"""Actual current v3 proof. No observer shortcut, actions, launch or termination API."""

import os
import time
from contextlib import contextmanager
from copy import deepcopy

from . import restore_exited_scope as native
from . import restore_exited_values as v
from .restore_exited_image import image as peer_image
from .restore_exited_resources import resources
from .restore_exited_transport import Transport
from .restore_reader import same
from .restore_wire import remaining


def stable(current):
    return {k: value for k, value in current.items() if k != "caller"}


@contextmanager
def current(source, launched, associated, *, expires, expected=None):
    v.source_valid(source, source["identity"])
    v.process(launched, source["identity"]["boot_id"])

    def deadline():
        left = expires - time.time()
        if left <= 0:
            raise ValueError("expired exited-host proof")
        return time.monotonic() + min(10, left)

    if os.getpid() == launched["pid"]:
        raise ValueError("original absent PID overlaps current caller")
    with resources() as stack:
        scope = native.Scope(deadline())
        stack.callback(scope.close)
        if scope.boot != source["identity"]["boot_id"]:
            raise ValueError("original source boot differs from current scope")
        transport = Transport(source["identity"], scope.deadline)
        stack.callback(transport.close)
        peer_pid = transport.credentials["pid"]
        # ubs:ignore[python.ctcompare.secret_eq] -- PID overlap check, not secret.
        if peer_pid == launched["pid"]:
            raise ValueError("original absent PID overlaps current peer")
        peer = native.Generation(scope, peer_pid)
        stack.callback(peer.close)
        bridge = v.inventory(source, peer.row["process"])
        image = peer_image(scope, peer)
        stack.callback(image.close)
        peer.check()
        version = transport.query("Version")
        v.version(source, version)
        discovery = transport.topology()
        protected = {w["pid"] for w in discovery["windows"]}
        cohort = native.Cohort(
            scope, stack, protected | {scope.caller_pid, peer_pid}, launched["pid"], peer
        )
        caller = native.ancestry(scope, cohort.ancestor)
        cohort.sealed = True
        generations = cohort.generations
        projection = {
            "method": v.METHOD,
            "state": discovery,
            "owned_window_ids": [],
            "protected_window_ids": sorted(w["id"] for w in discovery["windows"]),
            "processes": [
                generations[p].row["process"]
                for p in sorted({w["pid"] for w in discovery["windows"]})
            ],
            "peer": {
                "process": peer.row["process"],
                "credentials": transport.credentials,
                "endpoint": transport.endpoint,
                "inventory": bridge,
                "version": version,
                "running_image": image.pin,
            },
            "scope": scope.value,
            "absence": {
                "process": launched,
                "primitive": "linux-pidfd-open",
                "flags": 0,
                "errno": "ESRCH",
            },
            "caller": caller,
        }
        v.current(projection, source, launched, associated)
        if expected is not None and not same(stable(projection), stable(expected)):
            raise ValueError("current proof differs from approved baseline")
        frozen = deepcopy(projection)

        def checks():
            scope.check()
            transport.check()
            for generation in generations.values():
                generation.check()
            image.deadline = scope.deadline
            image.validate()
            with resources() as images:
                fresh = peer_image(scope, peer)
                images.callback(fresh.close)
                if not same(fresh.pin, image.pin):
                    raise ValueError("current peer executable changed")
            for generation in generations.values():
                generation.check()
            if not same(native.ancestry(scope, cohort.ancestor), caller):
                raise ValueError("caller ancestry drift")
            remaining(scope.deadline)

        def validate():
            scope.deadline = transport.deadline = deadline()
            checks()
            if transport.query("Version") != version:
                raise ValueError("authenticated version drift")
            a = transport.topology()
            native.absence(launched)
            b = transport.topology()
            native.absence(launched)
            checks()
            if not same(a, b) or not same(a, frozen["state"]):
                raise ValueError("split or changed current topology/focus")
            v.current(frozen, source, launched, associated)
            remaining(scope.deadline)
            if time.time() >= expires:
                raise ValueError("proof completed after expiry")

        validate()  # Discovery grants no proof; complete A/ESRCH/B/ESRCH cycle is mandatory.
        yield frozen, validate
        # Exit releases FDs only. Never introduce a veto after canonical publication.
