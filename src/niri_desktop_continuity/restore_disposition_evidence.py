"""Closed operator-imported client witness and current process checks; no action transport."""

import os
import subprocess
from contextlib import ExitStack, contextmanager
from pathlib import Path

from . import restore_host as host
from . import restore_state as states
from .model import digest
from .probe import proc_stat
from .restore_disposition_cwd import Directory
from .restore_disposition_dependencies import file
from .restore_disposition_failure import guard

TRUST = "installed-client-and-operator-controlled-original-witness-not-kernel-proof"


def witness(store, active, interrupted, result_path, exit_path):
    """Original CLI result body plus synchronously captured exit; attestation is separate."""
    receipt, receipt_pin = file(store, store.path("receipts", interrupted))
    if digest(receipt) != interrupted:
        raise ValueError("interrupted receipt digest mismatch")
    states.fields(
        receipt, "status windows effects final_observation native_session error_type error"
    )
    pending = store.get("receipts", active["retained_pending"])
    command = ["niri", "msg", "action", *pending["details"]["argv"]]
    if (
        receipt["status"] != "interrupted"
        or receipt["native_session"] != "not-proved"
        or receipt["error_type"] != "CalledProcessError"
        or receipt["error"] != str(subprocess.CalledProcessError(2, command))
        or receipt["effects"] != active["_launches"]["effects"]
        or not isinstance(receipt["final_observation"], dict)
    ):
        raise guard("ineligible-evidence", "not an exact returned exit-2 pending command")
    rows = receipt["windows"]
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("unbound interrupted accounting")
    row = rows[0]
    states.fields(
        row,
        "entry window_id status geometry_coverage process_receipt restored_window_id observed_initial_width target_workspace_id",
    )
    association = active["_launches"]["associations"][0]
    if (
        row["entry"] != active["plan"]["entries"][0]
        or row["window_id"] != row["entry"]["window_id"]
        or row["status"] != "owned-not-placed"
        or row["process_receipt"] != active["_launches"]["launches"][0]["receipt"]
        or row["restored_window_id"] != association["id"]
        or row["observed_initial_width"] != association["width"]
        or row["target_workspace_id"] != association["target"]
        or not isinstance(row["geometry_coverage"], dict)
    ):
        raise ValueError("interrupted row differs from original chain")
    result_path, exit_path = Path(result_path).absolute(), Path(exit_path).absolute()
    if result_path.parent != exit_path.parent:
        raise ValueError("original invocation witness files must share one private directory")
    result, result_pin = file(store, result_path)
    exit_bytes, exit_pin = file(store, exit_path, raw=True)
    if (
        result
        != {"snapshot_digest": active["snapshot_digest"], "receipt_digest": interrupted, **receipt}
        or exit_bytes != b"2\n"
        or result_pin["path"] == exit_pin["path"]
    ):
        raise guard(
            "ineligible-evidence", "original invocation witness does not match source/receipt/exit"
        )
    return {
        "interrupted": receipt_pin,
        "client_result": result_pin,
        "client_exit": exit_pin,
        "command_digest": digest(command),
        "trust": TRUST,
    }


def controller_pids():
    pid, result = os.getpid(), set()
    for _ in range(128):
        if pid == 1:
            return result
        if pid <= 0 or pid in result:
            raise ValueError("unknown controller ancestry")
        result.add(pid)
        pid = proc_stat(pid)["ppid"]
    raise ValueError("controller ancestry exceeds bound")


def observe():
    """No session/profile inventory: double read of bounded Niri topology only."""
    from .probe import compositor_identity
    from .restore import LiveDesktop

    desktop = LiveDesktop()
    identity = compositor_identity()

    def read():
        windows, workspaces = desktop.windows(), desktop.workspaces()
        if (
            not isinstance(windows, list)
            or len(windows) > 512
            or len({w["id"] for w in windows}) != len(windows)
        ):
            raise ValueError("invalid bounded current windows")
        return states.record(
            (
                {w["id"]: w for w in windows},
                workspaces,
                states.output_scales(desktop._query("outputs"), workspaces),
            )
        )

    first, second = read(), read()
    if first != second or identity != compositor_identity():
        raise ValueError("incoherent current disposition baseline")
    return {"identity": identity, "coherent": True, "state": second}


@contextmanager
def current(active, chain, observer=observe):
    """Hold pidfds through the caller's validation and durable accounting, never terminate."""
    value = observer()
    if (
        set(value) != {"identity", "coherent", "state"}
        or value["coherent"] is not True
        or value["identity"] != active["identity"]
    ):
        raise ValueError("fresh coherent original compositor required")
    state = states.decode(value["state"])
    tracker = active["_launches"]
    owned = tracker["associations"][0]["id"]
    launch = tracker["launches"][0]
    pid = launch["process"]["pid"]
    if (
        owned not in state[0]
        or state[0][owned]["pid"] != pid
        or [w["id"] for w in state[0].values() if w["pid"] == pid] != [owned]
        or any(w["pid"] == pid for w in tracker["baseline"][0].values())
        or pid in controller_pids()
    ):
        raise ValueError("unknown, surplus, protected or controller-overlapping ownership")
    bootstrap = chain[1][1]["details"]
    expected_argv = bootstrap["spec"]["argv"]
    with ExitStack() as stack:
        proofs = {}
        for process_id in sorted({w["pid"] for w in state[0].values()}):
            proof = stack.enter_context(host.Process(process_id))
            proofs[process_id] = proof
        owned_proof = proofs[pid]
        directory = stack.enter_context(
            Directory(bootstrap["spec"]["cwd"], bootstrap["directory"], owned_proof)
        )

        def process_valid():
            for proof in proofs.values():
                proof.live()
            if owned_proof.pin != launch["process"]:
                raise ValueError("launched process reused")
            owned_proof.validate(bootstrap["image"])
            with host.Image(expected_argv[0]) as image:
                if image.pin != bootstrap["image"]:
                    raise ValueError("original executable changed")
            if owned_proof.argv() != expected_argv:
                raise ValueError("running argv differs from launched spec")
            directory.validate()
            if pid in controller_pids():
                raise ValueError("launched host overlaps current controller")

        def validate():
            process_valid()
            if observer() != value:
                raise ValueError("current topology, focus or compositor changed")
            process_valid()

        validate()
        projected = {
            "state": value["state"],
            "owned_window_id": owned,
            "protected_window_ids": sorted(set(state[0]) - {owned}),
            "processes": [proofs[p].pin for p in sorted(proofs)],
            "running_image": bootstrap["image"],
            "argv_digest": digest(expected_argv),
            "cwd": directory.validate(),
        }
        # Callers explicitly veto BEFORE publishing authority, never at context exit.
        yield projected, validate
