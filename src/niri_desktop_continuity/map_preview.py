"""Isolated offline incident map. No launch, approval, network or process-control path."""

from __future__ import annotations

import html
import re
import shlex
from collections import Counter, defaultdict
from pathlib import Path

from .model import readiness, require_snapshot
from .recovery_projection import REASONS
from .recovery_protocol import ADDITIVE

ASSETS = Path(__file__).resolve().parent / "assets"
LIMITATIONS = (
    "Schematic layout, not a desktop screenshot. Hidden application tabs/splits, drafts and "
    "process memory are NOT captured. Restart/migration is blocked. This page grants no approval."
)
# How `restore --apply` reopens each recipe kind (see launch.py), and why some windows cannot be.
REOPENS_AS = {
    "claude": "Claude Code session, resumed by id",
    "pi": "Pi session, resumed",
    "declared": "your declared command (declare)",
    "app": "application, relaunched from its command line",
    "command": "terminal running its last command again",
    "shell": "terminal in the same directory",
}
NOT_REOPENED = {
    "xwayland-client": "X11 window: Niri reports the xwayland-satellite bridge, not the application",
    "claude-session-unregistered": "Claude process without a session registry entry; "
    "its command line would start the work over",
    "appimage-mount-unresolved": "AppImage temporary mount not traced to its image file",
    "process-title-unresolved": "the program rewrote its command line and no program file "
    "matches it",
    "process-unavailable": "the window's process was not observed",
    "cmdline-unavailable": "the process command line was unreadable",
    "no-recipe": "captured without a reopen recipe",
}


def escape(value) -> str:
    # XML 1.0 excludes control characters and surrogate codepoints even in escaped text.
    text = str(value if value is not None else "unknown")
    text = "".join(
        c
        for c in text
        if c in "\t\n\r"
        or 0x20 <= ord(c) <= 0xD7FF
        or 0xE000 <= ord(c) <= 0xFFFD
        or 0x10000 <= ord(c) <= 0x10FFFF
    )
    return html.escape(text, quote=True)


def label(snapshot, window):
    if snapshot.get("privacy", {}).get("titles_included") is True:
        return str(window.get("title") or window.get("app_id") or "unknown")
    return f"{window.get('app_id') or 'unknown'} · {window['id']}"


def groups(snapshot):
    require_snapshot(snapshot)
    workspaces = sorted(
        snapshot["workspaces"], key=lambda w: (w.get("output") or "", w.get("idx", 0))
    )
    known = {w["id"] for w in workspaces}
    orphaned = sorted(
        {w.get("workspace_id") for w in snapshot["windows"] if w.get("workspace_id") not in known},
        key=str,
    )
    workspaces += [
        {"id": wid, "idx": "?", "output": "unavailable", "name": "Unresolved workspace"}
        for wid in orphaned
    ]
    for workspace in workspaces:
        columns = defaultdict(list)
        for window in snapshot["windows"]:
            if window.get("workspace_id") != workspace["id"]:
                continue
            pos = window.get("layout", {}).get("pos_in_scrolling_layout")
            col = (
                "Floating"
                if window.get("is_floating")
                else (str(pos[0]) if isinstance(pos, list) and len(pos) == 2 else "Unknown")
            )
            columns[col].append(window)
        ordered = sorted(columns, key=lambda c: (not c.isdecimal(), int(c) if c.isdecimal() else c))
        yield (
            workspace,
            [
                (
                    col,
                    sorted(
                        columns[col],
                        key=lambda w: (
                            (w.get("layout", {}).get("pos_in_scrolling_layout") or [0, 0])[1],
                            w["id"],
                        ),
                    ),
                )
                for col in ordered
            ],
        )


def workspace_label(workspace):
    return f"{workspace.get('output', 'unknown')} / workspace {workspace.get('idx', '?')} · id {workspace['id']} · {workspace.get('name') or 'unnamed'}"


def recipe_of(window) -> dict:
    """The saved reopen recipe; like restore, a window without one has nothing to launch."""
    recipe = window.get("reopen")
    return recipe if isinstance(recipe, dict) else {"kind": "unknown", "reason": "no-recipe"}


def reopen_badge(recipe) -> str:
    if recipe.get("argv"):
        return f'<small class="reopen">reopens as {escape(recipe.get("kind"))}</small>'
    reason = recipe.get("reason") or "no-launch-command"
    return f'<small class="reopen not-reopened">not reopened ({escape(reason)})</small>'


def map_html(snapshot, title, selected, *, reopen=False):
    rows = [f"<h2>{escape(title)}</h2>"]
    for workspace, columns in groups(snapshot):
        rows.append(
            f'<section class="workspace"><h3>{escape(workspace_label(workspace))}</h3><div class="columns">'
        )
        if not columns:
            rows.append('<p class="muted">Empty workspace</p>')
        for col, windows in columns:
            rows.append(f'<div class="column"><p class="coordinate">Column {escape(col)}</p>')
            for window in windows:
                cls = "tile selected" if window["id"] in selected else "tile"
                rows.append(
                    f'<article class="{cls}"><small>WINDOW {window["id"]} / PID {escape(window.get("pid"))}</small>'
                    f"<p>{escape(label(snapshot, window))}</p>"
                    f"<small>{escape(window.get('app_id'))} · {'focused' if window.get('is_focused') else 'unfocused'}</small>"
                    f"{reopen_badge(recipe_of(window)) if reopen else ''}</article>"
                )
            rows.append("</div>")
        rows.append("</div></section>")
    return "".join(rows)


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def reopen_html(snapshot):
    """What `restore --apply` would launch from this capture: every window, in map order."""
    titles = snapshot.get("privacy", {}).get("titles_included") is True
    rows, kinds, missing, extras = [], Counter(), 0, 0
    for workspace, columns in groups(snapshot):
        name = f" · {workspace['name']}" if workspace.get("name") else ""
        for col, windows in columns:
            where = (
                f"<td>workspace {escape(workspace.get('idx', '?'))}{escape(name)}<br>"
                f"<small>{escape(workspace.get('output'))} · column {escape(col)}</small></td>"
            )
            for window in windows:
                recipe = recipe_of(window)
                shown = label(snapshot, window)
                session = recipe.get("label") if titles else None
                who = escape(shown) + (
                    f"<br><small>session: {escape(session)}</small>"
                    if session and session not in shown
                    else ""
                )
                tabs = [(recipe, f"{who}<br><small>WINDOW {window['id']}</small>")]
                for extra in recipe.get("extra") or []:
                    extras += 1
                    session = extra.get("label") if titles else None
                    tabs.append(
                        (
                            extra,
                            f"{escape(session or 'Session in a terminal tab')}<br>"
                            f"<small>TAB OF WINDOW {window['id']} · reopens as its own window</small>",
                        )
                    )
                for item, who_cell in tabs:
                    if item.get("argv"):
                        kind = str(item.get("kind"))
                        kinds[kind] += 1
                        status = f"<td>Reopens<br><small>{escape(REOPENS_AS.get(kind, kind))}</small></td>"
                        where_run = (
                            f"<br><small>in {escape(item['cwd'])}</small>"
                            if item.get("cwd")
                            else ""
                        )
                        if item.get("argv_from_process_title"):
                            where_run += (
                                "<br><small>arguments split from the process title; "
                                "check any that contained spaces</small>"
                            )
                        command = (
                            f"<td><code>{escape(shlex.join(map(str, item['argv'])))}</code>"
                            f"{where_run}</td>"
                        )
                    else:
                        missing += 1
                        reason = item.get("reason") or "no-launch-command"
                        status = (
                            f'<td class="not-reopened">Not reopened<br><small>'
                            f"{escape(NOT_REOPENED.get(reason, 'no launch command recorded'))}"
                            f"</small> <code>{escape(reason)}</code></td>"
                        )
                        command = '<td class="muted">nothing is launched</td>'
                    rows.append(f"<tr>{where}<td>{who_cell}</td>{status}{command}</tr>")
    total = len(rows)
    by_kind = " · ".join(f"{kind} {kinds[kind]}" for kind in REOPENS_AS if kinds[kind])
    by_kind += "".join(
        f" · {kind} {n}" for kind, n in sorted(kinds.items()) if kind not in REOPENS_AS
    )
    saved = plural(len(snapshot["windows"]), "window")
    if extras:
        saved += f" + {plural(extras, 'session')} found in terminal tabs, which reopen as separate windows"
    return (
        '<section class="workspace" id="after-reboot" aria-labelledby="after-reboot-title">'
        '<h2 id="after-reboot-title">02 / After a reboot</h2>'
        f'<p class="reopen-summary"><strong>{total - missing} of {total} reopen after a reboot</strong>'
        f" · {f'{missing} will not' if missing else 'none left out'}</p>"
        f'<p class="muted">{escape(by_kind or "nothing to reopen")}</p>'
        f'<p class="note">Saved: {escape(saved)}. This is what <code>restore --apply</code> would '
        "launch from this capture: each command is spawned through Niri, and the new window is "
        "moved to its saved workspace and column. Windows already open are never moved or closed, "
        "and a Claude or Pi session that is already open is skipped. Applications restore their "
        "own content; unsaved drafts, scrollback and hidden tab order are not recovered.</p>"
        '<div class="table-scroll"><table><thead><tr><th>Saved place</th><th>Window</th>'
        "<th>After a reboot</th><th>Command</th></tr></thead><tbody>"
        f"{''.join(rows)}</tbody></table></div></section>"
    )


def saved_projection_html(observed):
    """Display only explicitly projected grouping/diagnostics, never private manifests."""
    rows = []
    grouping = observed.get("grouping")
    if grouping is not None:
        rows += [
            "<h3>Desired shared-window groups</h3>",
            '<p class="note">Reviewed grouping intent, not captured native topology. '
            "Sequence is desired creation order, not verified original tab order. "
            "Existing windows remain protected; this is not a tab-transfer operation.</p>",
            '<div class="table-scroll"><table><thead><tr><th>Desired group</th>'
            "<th>Reviewed provenance</th><th>Saved references in creation sequence</th>"
            "</tr></thead><tbody>",
        ]
        for index, group in enumerate(grouping["groups"], start=1):
            refs = "".join(f"<li><code>{escape(ref)}</code></li>" for ref in group["session_refs"])
            rows.append(
                f'<tr><th scope="row">Group {index}</th><td>{escape(group["provenance"])}</td>'
                f"<td><ol>{refs}</ol></td></tr>"
            )
        rows.append("</tbody></table></div>")
    else:
        rows.append(
            '<p class="note">Grouping not supplied by this historical/standalone '
            "observation; no grouping is inferred.</p>"
        )
    diagnostics = observed.get("diagnostics")
    if diagnostics is not None:
        rows.append(
            f"<h3>Admission diagnostics</h3><p>Private-store capacity: "
            f"{escape(diagnostics['capacity'])}</p><ul>"
        )
        for row in diagnostics["reasons"]:
            reason = REASONS.get(row["code"], "Unrecognized reason; admission unverified.")
            rows.append(
                f"<li><code>{escape(row['session_ref'])}</code>: "
                f"{escape(reason)} <code>{escape(row['code'])}</code></li>"
            )
        rows.append("</ul>")
    return "".join(rows)


def saved_scope_html(plan):
    """Show only opaque admitted scope, never adapter-private manifests or native data."""
    recovery = (plan or {}).get("recovery", {})
    if recovery.get("schema") != ADDITIVE:
        return ""
    observed = recovery["observation"]
    selection = observed["saved_selection"]
    rows = [
        '<section class="workspace" aria-labelledby="saved-set-scope">'
        '<h2 id="saved-set-scope">Additive saved-session scope</h2>',
        f"<p>Saved-set digest: <code>{escape(recovery['saved_set'])}</code></p>",
        f"<p>Selected saved conversations: {len(observed['session_refs'])}. "
        "All current windows are protected; this preview grants no approval.</p>",
        '<div class="table-scroll"><table><thead><tr><th>Disposition</th>'
        "<th>Count</th><th>Exact saved references</th></tr></thead><tbody>",
    ]
    for name, title in (
        ("missing_refs", "Missing (to reopen)"),
        ("present_refs", "Already present (preserved)"),
        ("unresolved_refs", "Unresolved (blocks approval)"),
    ):
        refs = selection[name]
        rendered = "<br>".join(f"<code>{escape(ref)}</code>" for ref in refs) or "None"
        rows.append(
            f'<tr><th scope="row">{escape(title)}</th><td>{len(refs)}</td><td>{rendered}</td></tr>'
        )
    rows.append("</tbody></table></div>")
    if selection["unresolved_refs"]:
        summary = "Unresolved references block approval of this exact saved set."
    elif not observed["session_refs"]:
        summary = "No saved references selected; approval is blocked."
    elif not selection["missing_refs"]:
        summary = "No launches planned: all selected references are already present."
    else:
        summary = "Only the listed missing references may be reopened after exact approval."
    rows.append(saved_projection_html(observed))
    rows.append(
        f'<p class="note">{escape(summary)} Layout and hidden tabs are not reconstructed.</p></section>'
    )
    return "".join(rows)


def render_html(snapshot, *, plan=None, plan_digest=None):
    require_snapshot(snapshot)
    selected = set((plan or {}).get("selection", {}).get("window_ids", []))
    admission = (plan or {}).get(
        "admission", {"status": "review-only", "blockers": [], "warnings": []}
    )
    status = readiness(snapshot)
    css = (ASSETS / "tokens.css").read_text()
    css += """
*{box-sizing:border-box}body{margin:0;background:var(--colors-neutral);color:var(--colors-on-surface);font-family:var(--typography-body-md-font-family);line-height:1.5}
main{padding:var(--spacing-xl);max-width:1800px;margin:auto}h1,h2{font-family:var(--typography-display-font-family);font-weight:400}h1{font-size:clamp(32px,5vw,48px);margin:8px 0}h2{font-size:32px;margin-top:40px}h3{font-size:16px;font-weight:400}
.kicker,small,.coordinate,code{font-family:var(--typography-label-caps-font-family)}.kicker{color:var(--colors-success);letter-spacing:.12em}.muted,small{color:var(--colors-secondary)}.warning{color:var(--colors-warning);border-left:4px solid var(--colors-warning);padding:16px;background:var(--colors-surface)}
.workspace{border-top:1px solid var(--colors-muted);padding:8px 0 24px}.columns{display:flex;gap:16px;overflow:auto;padding-bottom:8px}.column{flex:0 0 240px}.coordinate{color:var(--colors-secondary);font-size:12px}.tile{padding:16px;background:var(--colors-surface);border:1px solid var(--colors-muted);border-radius:var(--rounded-sm);margin-bottom:8px;overflow-wrap:anywhere}.selected{border-color:var(--colors-success)}.tile p{margin:8px 0}small{font-size:11px}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:8px 16px;border-bottom:1px solid var(--colors-muted);text-align:left;vertical-align:top}td{overflow-wrap:anywhere}code{overflow-wrap:anywhere}.note{max-width:90ch}.reopen{display:block;margin-top:8px;color:var(--colors-primary)}.not-reopened{color:var(--colors-warning)}.reopen-summary{font-size:20px}#after-reboot td:first-child{white-space:nowrap}#after-reboot td code{font-size:13px}footer{margin-top:40px;border-top:1px solid var(--colors-muted);padding-top:16px}@media(max-width:600px){main{padding:16px}.column{flex-basis:210px}}
"""
    body = [
        f'<p class="kicker">NIRI / DESKTOP CONTINUITY</p><h1>Your work, where you left it.</h1>'
        f'<p class="muted">Captured {escape(snapshot.get("captured_at"))} · {len(snapshot["windows"])} windows · '
        f"{'private titles included' if snapshot.get('privacy', {}).get('titles_included') else 'window titles redacted'}</p>",
        f'<aside class="warning"><strong>{escape(admission["status"]).upper()} — NO RESTART AUTHORIZED</strong>'
        f'<p class="note">{escape(LIMITATIONS)}</p><p>Display observation: {"ready" if status["ready"] else "not ready"}</p><ul>',
    ]
    for reason in status["reasons"] + admission.get("blockers", []) + admission.get("warnings", []):
        body.append(f"<li>{escape(reason)}</li>")
    body.append("</ul></aside>")
    if plan_digest and plan is not None:
        body.append(
            f"<p>Exact proposal digest: <code>{escape(plan_digest)}</code><br>Expires {escape(plan.get('expires_at'))}</p>"
        )
        affected = plan.get("affected", {})
        body.append(
            f"<p>Selected windows: {escape(sorted(selected))} · Affected windows: {escape(affected.get('window_ids', []))} · "
            f"Dependent processes: {len(affected.get('pids', []))}</p>"
        )
    body.append(saved_scope_html(plan))
    body.append(map_html(snapshot, "01 / Current observation", selected, reopen=plan is None))
    if plan:
        body.append(map_html(plan["desired"], "02 / Desired topology (proposal only)", selected))
    else:
        body.append(reopen_html(snapshot))
    body.append(
        '<h2>Process &amp; capability ledger</h2><div class="table-scroll"><table><thead><tr><th>PID</th><th>Executable / version</th><th>Identity</th><th>Continuity</th></tr></thead><tbody>'
    )
    for process in snapshot["processes"]:
        body.append(
            f"<tr><td>{escape(process.get('pid'))}</td><td>{escape(process.get('exe'))}<br>{escape(process.get('version'))}</td>"
            f"<td>start {escape(process.get('start_ticks'))}<br><code>{escape(process.get('exe_sha256'))}</code></td>"
            "<td>Layout: same instance<br>Native state: unverified<br>Restart: blocked</td></tr>"
        )
    body.append("</tbody></table></div><h2>Layer surfaces</h2><ul>")
    for layer in snapshot["layers"]:
        body.append(
            f"<li>{escape(layer.get('namespace'))} · {escape(layer.get('output'))} · {escape(layer.get('layer'))}</li>"
        )
    body.append(
        '</ul><footer class="muted">Offline · no network · no interactive approval controls · private recovery data, not restart permission</footer>'
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'\">"
        f"<title>Niri desktop continuity</title><style>{css}</style></head><body><main>{''.join(body)}</main></body></html>"
    )


def render_svg(snapshot, *, plan=None, plan_digest=None):
    require_snapshot(snapshot)
    tokens = dict(
        re.findall(r"--colors-([\w-]+):\s*(#[0-9A-Fa-f]{6});", (ASSETS / "tokens.css").read_text())
    )
    views = [("Current observation", snapshot)]
    if plan:
        views.append(("Desired topology — proposal only", plan["desired"]))
    selected = set((plan or {}).get("selection", {}).get("window_ids", []))
    content, y, width = [], 150, 1200

    def text(x, y, value, *, size=14, color="on-surface"):
        return f'<text x="{x}" y="{y}" fill="{tokens[color]}" font-size="{size}">{escape(value)}</text>'

    for title, view in views:
        content.append(text(32, y, title, size=28))
        y += 40
        for workspace, columns in groups(view):
            content.append(text(32, y, workspace_label(workspace), color="secondary"))
            y += 24
            x, height = 32, 50
            for col, windows in columns:
                content.append(text(x, y, f"Column {col}", color="secondary"))
                tile_y = y + 12
                for window in windows:
                    border = tokens["success" if window["id"] in selected else "muted"]
                    content.append(
                        f'<g><title>{escape(label(view, window))}</title><rect x="{x}" y="{tile_y}" width="236" height="90" rx="4" fill="{tokens["surface"]}" stroke="{border}"/>'
                    )
                    content.append(
                        text(
                            x + 12,
                            tile_y + 22,
                            f"WINDOW {window['id']} / PID {window.get('pid')}",
                            size=11,
                            color="secondary",
                        )
                    )
                    title_label = label(view, window)
                    content.append(
                        text(
                            x + 12,
                            tile_y + 46,
                            title_label[:26] + ("…" if len(title_label) > 26 else ""),
                            size=13,
                        )
                    )
                    app = str(window.get("app_id") or "unknown")
                    content.append(
                        text(x + 12, tile_y + 70, app[:28], size=11, color="secondary") + "</g>"
                    )
                    tile_y += 100
                height = max(height, tile_y - y)
                x += 252
            width = max(width, x + 16)
            y += height + 40
    admission = (plan or {}).get("admission", {}).get("status", "review-only")
    heading = text(32, 42, "NIRI / DESKTOP CONTINUITY", size=28)
    heading += text(
        32,
        72,
        f"{snapshot.get('captured_at')} · {len(snapshot['windows'])} windows · schematic, not a screenshot",
        color="secondary",
    )
    heading += text(
        32,
        100,
        f"{admission.upper()} · Native state unverified · NO RESTART AUTHORIZED",
        color="warning",
    )
    footer = text(
        32,
        y,
        "Hidden tabs, drafts and process memory are not captured. See HTML for complete admission and process details.",
        size=12,
        color="warning",
    )
    if plan_digest:
        footer += text(32, y + 24, f"Plan: {plan_digest}", size=12)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{y + 70}" viewBox="0 0 {width} {y + 70}" role="img" aria-label="Desktop spatial ledger">'
        f'<rect width="100%" height="100%" fill="{tokens["neutral"]}"/>'
        f'<g font-family="DejaVu Sans Mono, monospace">{heading}{"".join(content)}{footer}</g></svg>'
    )
