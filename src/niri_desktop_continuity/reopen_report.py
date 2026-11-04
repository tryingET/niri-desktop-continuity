"""Offline result page of one `restore --apply` run: what came back, what did not and why.

Rendering reads only the stored receipt and the snapshot it reopened: no launch, network or desktop
access. `open_report` is the one effect: at the end of a run it asks Niri to open the page.
"""

from __future__ import annotations

import shlex
import shutil
from datetime import datetime
from pathlib import Path

from .map_preview import NOT_REOPENED, escape, groups, label, page_css
from .reopen import RESTORE_SCHEMA
from .store import HEX

# A window counts as back when Niri reported it during the run: placed, or open before it.
BACK = {"placed", "already-running", "already-open"}
WHY = {
    "not-detected": "launched, but no new window of this application appeared in time",
    "no-route": "no way to launch it was found",
    "not-attempted": "the run stopped before reaching it",
}
CSS = """
.tile.back{border-color:var(--colors-success);border-left:4px solid var(--colors-success)}
.back .outcome,.outcome.back,.summary .back{color:var(--colors-success)}
.tile.missed{border-color:var(--colors-error);border-left:4px solid var(--colors-error)}
.missed .outcome,.outcome.missed,.summary .missed,.why{color:var(--colors-error)}
.outcome{display:block;margin-top:8px;font-family:var(--typography-label-caps-font-family);font-size:12px}
#did-not-come-back td:first-child{white-space:nowrap}#did-not-come-back td code{font-size:13px}
.summary{font-family:var(--typography-display-font-family);font-size:40px;line-height:1.2;margin:32px 0 16px}
.summary strong{font-weight:400}.legend{display:flex;flex-wrap:wrap;gap:8px 24px;padding:0;margin:0 0 8px;list-style:none}
.legend li{border-left:4px solid var(--colors-muted);padding:2px 0 2px 12px;color:var(--colors-secondary)}
.legend li.back{border-color:var(--colors-success)}.legend li.missed{border-color:var(--colors-error)}
.legend b{font-family:var(--typography-label-caps-font-family);font-size:12px;font-weight:400;margin-right:8px}
.legend .back b{color:var(--colors-success)}.legend .missed b{color:var(--colors-error)}
"""
LEGEND = (
    '<ul class="legend">'
    '<li class="back"><b>BACK</b>reopened and moved to its saved place</li>'
    '<li class="back"><b>ALREADY OPEN</b>open before the run, left as it was</li>'
    '<li class="missed"><b>NOT BACK</b>did not come back; the list below says why</li></ul>'
)


def local_time(value) -> str:
    """A stored UTC timestamp in this machine's time zone, to the minute; else as stored."""
    try:
        moment = datetime.fromisoformat(str(value)).astimezone()
    except ValueError:
        return str(value)
    return moment.isoformat(sep=" ", timespec="minutes")


def came_back(row: dict) -> bool:
    return row.get("status") in BACK


def code(row: dict) -> str:
    return str(row.get("reason") or row.get("status"))


def badge(row: dict) -> str:
    status = row.get("status")
    if status == "placed":
        return f"BACK as window {escape(row.get('restored_window_id'))}"
    if status in BACK:
        return "ALREADY OPEN"
    return f"NOT BACK ({escape(code(row))})"


def why(row: dict) -> str:
    if row.get("status") != "not-reopened":
        return WHY.get(str(row.get("status")), "it did not come back")
    reason = str(row.get("reason") or "")
    if reason.startswith("unsupported-kind:"):
        return "this kind of saved window cannot be reopened"
    return NOT_REOPENED.get(reason, "no launch command was recorded")


def window_cell(snapshot: dict, windows: dict, row: dict) -> str:
    if row.get("extra_of") is not None:
        return (
            f"Session in a terminal tab<br><small>TAB OF WINDOW {escape(row['extra_of'])}</small>"
        )
    window = windows.get(row.get("window_id"))
    shown = label(snapshot, window) if window else "unknown window"
    return f"{escape(shown)}<br><small>WINDOW {escape(row.get('window_id'))}</small>"


def place_cell(row: dict) -> str:
    name = f" · {row['saved_workspace_name']}" if row.get("saved_workspace_name") else ""
    where = "floating" if row.get("floating") else f"column {row.get('column')}"
    return (
        f"<td>workspace {escape(row.get('saved_workspace_idx'))}{escape(name)}"
        f"<br><small>{escape(where)}</small></td>"
    )


def missed_html(snapshot: dict, windows: dict, rows: list[dict]) -> str:
    missed = [row for row in rows if not came_back(row)]
    head = (
        '<section class="workspace" id="did-not-come-back" aria-labelledby="missed-title">'
        f'<h2 id="missed-title">01 / Did not come back ({len(missed)})</h2>'
    )
    if not missed:
        return head + "<p>Nothing was left out.</p></section>"
    body = []
    for row in missed:
        argv = row.get("argv")
        command = (
            f"<td><code>{escape(shlex.join(map(str, argv)))}</code></td>"
            if argv and row.get("status") != "not-reopened"
            else '<td class="muted">nothing was launched</td>'
        )
        body.append(
            f"<tr>{place_cell(row)}<td>{window_cell(snapshot, windows, row)}</td>"
            f'<td class="why">Not back<br><small>{escape(why(row))}</small> '
            f"<code>{escape(code(row))}</code></td>{command}</tr>"
        )
    return (
        f"{head}"
        '<div class="table-scroll"><table><thead><tr><th>Saved place</th><th>Window</th>'
        f"<th>Why</th><th>Command</th></tr></thead><tbody>{''.join(body)}</tbody></table></div>"
        "</section>"
    )


def map_html(snapshot: dict, rows: list[dict]) -> str:
    main = {row["window_id"]: row for row in rows if row.get("window_id") is not None}
    tabs: dict = {}
    for row in rows:
        if row.get("extra_of") is not None:
            tabs.setdefault(row["extra_of"], []).append(row)
    out = ["<h2>02 / Your saved desktop, as it came back</h2>"]
    for workspace, columns in groups(snapshot):
        name = f" · {workspace['name']}" if workspace.get("name") else ""
        out.append(
            f'<section class="workspace"><h3>workspace {escape(workspace.get("idx", "?"))}'
            f'{escape(name)}</h3><div class="columns">'
        )
        if not columns:
            out.append('<p class="muted">Empty workspace</p>')
        for col, windows in columns:
            out.append(f'<div class="column"><p class="coordinate">Column {escape(col)}</p>')
            for window in windows:
                row = main.get(window["id"])
                state = "" if row is None else (" back" if came_back(row) else " missed")
                outcome = badge(row) if row else "NOT IN THIS RUN"
                lines = "".join(
                    f'<small class="outcome {"back" if came_back(t) else "missed"}">'
                    f"tab session: {badge(t)}</small>"
                    for t in tabs.get(window["id"], [])
                )
                out.append(
                    f'<article class="tile{state}"><small>WINDOW {window["id"]} / PID '
                    f"{escape(window.get('pid'))}</small><p>{escape(label(snapshot, window))}</p>"
                    f"<small>{escape(window.get('app_id'))}</small>"
                    f'<span class="outcome">{outcome}</span>{lines}</article>'
                )
            out.append("</div>")
        out.append("</div></section>")
    return "".join(out)


def render_report(receipt: dict, snapshot: dict, *, key: str | None = None) -> str:
    rows = list(receipt.get("windows") or [])
    windows = {w["id"]: w for w in snapshot["windows"]}
    back = sum(1 for row in rows if came_back(row))
    missed = len(rows) - back
    titles = snapshot.get("privacy", {}).get("titles_included") is True
    body = [
        '<p class="kicker">NIRI / DESKTOP CONTINUITY</p><h1>What came back</h1>'
        f'<p class="muted">Reopened {escape(local_time(receipt.get("started_at")))} from the '
        f"capture of {escape(local_time(snapshot.get('captured_at')))} · run status "
        f"{escape(receipt.get('status'))} · "
        f"{'private titles included' if titles else 'window titles redacted'}"
        + (f"<br>Receipt <code>{escape(key)}</code>" if key else "")
        + "</p>",
        f'<p class="summary"><strong class="back">{back} of {len(rows)} came back</strong> · '
        + (f'<span class="missed">{missed} did not</span>' if missed else "nothing was left out")
        + "</p>",
        LEGEND,
    ]
    if receipt.get("status") == "interrupted":
        body.append(
            '<aside class="warning"><strong>The run was interrupted.</strong><p>'
            f"{escape(receipt.get('error_type'))}: {escape(receipt.get('error'))}. Windows it had "
            "not reached are marked not attempted; nothing was retried.</p></aside>"
        )
    body.append(missed_html(snapshot, windows, rows))
    body.append(map_html(snapshot, rows))
    body.append(
        '<footer class="muted">Offline · no network · this page changes nothing. BACK means Niri '
        "reported a new window of that application during the run and it was moved to its saved "
        "place; applications restore their own content.</footer>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src '
        "'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'\">"
        f"<title>What came back · niri desktop continuity</title><style>{page_css()}{CSS}</style>"
        f"</head><body><main>{''.join(body)}</main></body></html>"
    )


def write_report(store, key: str) -> Path:
    """Render one stored `restore --apply` receipt to previews/<receipt digest>.html."""
    receipt = store.get("receipts", key)
    if receipt.get("schema") != RESTORE_SCHEMA or receipt.get("apply") is not True:
        raise ValueError("not a restore --apply run; its receipt has no result to show")
    snapshot = store.get("snapshots", receipt["snapshot_digest"])
    return store.write_preview(key, "html", render_report(receipt, snapshot, key=key))


def latest_run(store) -> str:
    """The newest stored `restore --apply` receipt, by file time."""
    folder = store.root / "receipts"
    found = []
    if folder.is_dir():
        for path in folder.iterdir():
            if path.suffix == ".json" and HEX.fullmatch(path.stem) and not path.is_symlink():
                found.append((path.stat().st_mtime_ns, path.stem))
    for _, key in sorted(found, reverse=True):
        receipt = store.get("receipts", key)
        if receipt.get("schema") == RESTORE_SCHEMA and receipt.get("apply") is True:
            return key
    raise ValueError("no restore --apply run yet; nothing to show")


def open_report(desktop, page: Path) -> dict:
    """Ask Niri to open the page with xdg-open, as the run's last step; report what happened."""
    opener = shutil.which("xdg-open")
    if opener is None:
        return {"report_open_error": "xdg-open not found"}
    try:
        desktop.spawn([opener, str(page)])
    except (OSError, ValueError) as exc:
        return {"report_open_error": str(exc)}
    return {"report_open": "requested"}
