"""Present-tense topology/process proof; explicitly NOT a historical association."""

from contextlib import ExitStack, contextmanager

from . import restore_disposition_evidence as proof
from . import restore_disposition_v2_model as model
from . import restore_host as host
from . import restore_state as states
from .model import digest
from .restore_reader import same


@contextmanager
def current(active, chain, observer, *, recorded_controllers=None):
    def read():
        value = observer()
        states.fields(value, "identity coherent state")
        if value["coherent"] is not True or not same(value["identity"], active["identity"]):
            raise ValueError("coherent original compositor required")
        states.decode(value["state"])
        return value

    value = read()
    if not same(value, read()):
        raise ValueError("incoherent current topology")
    state = states.decode(value["state"])
    launch = active["_launches"]["launches"][0]
    pid = launch["process"]["pid"]
    owned = [w["id"] for w in state[0].values() if w["pid"] == pid]
    controllers = sorted(proof.controller_pids())
    if len(owned) != 1 or not controllers or pid in controllers:
        raise ValueError("absent, surplus or controller-overlapping launched host")
    bootstrap = chain[active["_start"] + 1][1]["details"]
    with ExitStack() as stack:
        processes = {
            p: stack.enter_context(host.Process(p))
            for p in sorted({w["pid"] for w in state[0].values()})
        }
        process = processes[pid]
        directory = stack.enter_context(
            proof.Directory(bootstrap["spec"]["cwd"], bootstrap["directory"], process)
        )

        def process_valid():
            for item in processes.values():
                item.live()
            if not same(process.pin, launch["process"]):
                raise ValueError("original launched process reused")
            process.validate(bootstrap["image"])
            with host.Image(bootstrap["spec"]["argv"][0]) as image:
                if not same(image.pin, bootstrap["image"]):
                    raise ValueError("running/original image mismatch")
            if not same(process.argv(), bootstrap["spec"]["argv"]):
                raise ValueError("original argv changed")
            directory.validate()
            if pid in proof.controller_pids():
                raise ValueError("owned process overlaps current controller")

        def validate():
            process_valid()
            if not same(read(), value) or not same(read(), value):
                raise ValueError("current topology, focus or compositor drift")
            process_valid()

        validate()
        projected = {
            "state": value["state"],
            "owned_window_id": owned[0],
            "protected_window_ids": sorted(set(state[0]) - set(owned)),
            "processes": [processes[p].pin for p in sorted(processes)],
            "running_image": bootstrap["image"],
            "argv_digest": digest(bootstrap["spec"]["argv"]),
            "cwd": directory.validate(),
            # Historical proposal evidence; separate fresh ancestry veto runs at EVERY stage.
            # Different CLI invocations need not have identical controller process IDs.
            "controller_pids": controllers
            if recorded_controllers is None
            else recorded_controllers,
        }
        model.partition(projected, active, chain)
        yield projected, validate  # Resource cleanup only, no veto after publication.
