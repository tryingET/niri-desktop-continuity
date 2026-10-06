"""Independent fabricated transcript assembly across Stores; never a product planner/executor."""

import json
from copy import deepcopy
from types import SimpleNamespace

from test_restore_disposition_handwritten import sha

from niri_desktop_continuity.store import Store


def append(seed, store, attempt, rows):
    paths = sorted(seed.directory.glob("*.json"))
    previous = sha(json.loads(paths[-1].read_text())) if paths else None
    origin = {
        "root": str(store.root),
        "pin": {"device": store.root.stat().st_dev, "inode": store.root.stat().st_ino},
    }
    for seq, (kind, payload) in enumerate(rows, len(paths)):
        key = store.put("receipts", payload)
        assert key == sha(payload)
        record = {
            "schema": "desktop-continuity.restore-history.v3",
            "seq": seq,
            "previous": previous,
            "type": kind,
            "attempt": attempt,
            "receipt": key,
            "origin": origin,
        }
        path = seed.directory / f"{seq:08d}.json"
        path.write_text(json.dumps(record, sort_keys=True) + "\n")
        path.chmod(0o600)
        previous = sha(record)


def next_attempt(
    seed, root, number, *, ordinary=False, pid=None, start_ticks=1, attempt=None, snapshot=None
):
    store = Store(root)
    original = []
    for seq in range(5):
        record = json.loads((seed.directory / f"{seq:08d}.json").read_text())
        original.append((record["type"], seed.store.get("receipts", record["receipt"])))
    prepared = deepcopy(original[0][1])
    if snapshot is None:
        snapshot = deepcopy(seed.store.get("snapshots", prepared["snapshot_digest"]))
        snapshot["windows"][0]["id"] = 1 + number
    source = store.put("snapshots", snapshot)
    prepared["snapshot_digest"] = source
    plan = prepared["plan"]
    baseline = seed.observe()["state"]
    ids = sorted(w["id"] for w in baseline["windows"])
    plan["baseline"] = deepcopy(baseline)
    plan["baseline_recipes"] = [{"id": wid, "recipe": None} for wid in ids]
    for container in (plan, plan["source_plan"]):
        container["protected_window_ids"] = ids
        container["entries"][0]["window_id"] = snapshot["windows"][0]["id"]
    entry = plan["entries"][0]
    attempt = attempt or sha({"attempt": number})
    if ordinary:
        plan["entries"] = deepcopy(plan["source_plan"]["entries"])
        entry = plan["entries"][0]
        rows = [
            {
                "entry": entry,
                "window_id": entry["window_id"],
                "status": "unsupported",
                "reason": "fabricated pre-effect unsupported classification",
            }
        ]
        plan["initial_accounting"] = rows
        terminal = {
            "status": "partial",
            "windows": rows,
            "effects": [],
            "final_observation": baseline,
            "native_session": "not-proved",
        }
        append(
            seed,
            store,
            attempt,
            [
                ("prepared", prepared),
                ("final-observed", {"state": baseline}),
                ("terminal", terminal),
            ],
        )
        return SimpleNamespace(
            store=store,
            source=source,
            identity=seed.identity,
            attempt=attempt,
            directory=seed.directory,
            observe=seed.observe,
        )
    plan["initial_accounting"] = [
        {"entry": entry, "window_id": entry["window_id"], "status": "unprocessed"}
    ]
    process = {
        "boot_id": seed.identity["boot_id"],
        "pid": pid or 2000 + number,
        "start_ticks": start_ticks,
    }
    bootstrap, execute = deepcopy(original[1][1]), deepcopy(original[3][1])
    bootstrap["details"]["nonce"] = sha({"nonce": number})
    execute["details"]["process"] = process
    observed = deepcopy(original[4][1]["evidence"])
    observed["process"] = process
    process_key = store.put("receipts", observed)
    append(
        seed,
        store,
        attempt,
        [
            ("prepared", prepared),
            ("intent", bootstrap),
            (
                "observed",
                {"intent": sha(bootstrap), "evidence": {"bootstrap": process, "binding": "c" * 64}},
            ),
            ("intent", execute),
            ("observed", {"intent": sha(execute), "evidence": observed}),
        ],
    )
    receipt = {
        "status": "interrupted",
        "windows": [
            {
                "entry": entry,
                "window_id": entry["window_id"],
                "status": "launch-indeterminate",
                "geometry_coverage": {"width": "requested-pending", "position": "not-recorded"},
                "process_receipt": process_key,
            }
        ],
        "effects": [],
        "final_observation": {"unavailable": True},
        "native_session": "not-proved",
        "error_type": "ValueError",
        "error": "foreign active window",
    }
    interrupted = store.put("receipts", receipt)
    result, exit_file = store.root / "original-result.json", store.root / "original-exit.txt"
    result.write_text(
        json.dumps({"snapshot_digest": source, "receipt_digest": interrupted, **receipt})
    )
    exit_file.write_text("2\n")
    result.chmod(0o600)
    exit_file.chmod(0o600)
    current = deepcopy(baseline)
    window = deepcopy(current["windows"][-1])
    window.update(id=12000 + number, pid=process["pid"], is_focused=False)
    window["layout"]["pos_in_scrolling_layout"] = [len(current["windows"]) + 1, 1]
    current["windows"].append(window)
    return SimpleNamespace(
        store=store,
        source=source,
        identity=seed.identity,
        attempt=attempt,
        directory=seed.directory,
        interrupted=interrupted,
        result=result,
        exit_file=exit_file,
        observe=lambda: {"identity": seed.identity, "coherent": True, "state": deepcopy(current)},
    )
