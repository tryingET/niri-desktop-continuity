#!/usr/bin/env python3
"""Generate the niri-desktop-continuity 0.3.2 tour as a Director HTML composition.

Usage: build.py DIRECTOR_CHECKOUT OUTPUT_DIRECTORY
Writes OUTPUT_DIRECTORY/announce.html and copies its four SIL Open Font License fonts beside it.
Every window, title, session id and command is fabricated. No desktop capture or OS update runs.
"""

from __future__ import annotations

import html
import shutil
import sys
from pathlib import Path

VIDEO_VERSION = "0.3.2"
W, H, FPS, DURATION = 1920, 1080, 30, 52
FONTS = {
    "Inter-Regular.ttf": "crates/director-core/assets/fonts/Inter-Regular.ttf",
    "Inter-Bold.ttf": "crates/director-core/assets/fonts/Inter-Bold.ttf",
    "InstrumentSerif-Italic.ttf": "examples/assets/fonts/InstrumentSerif-Italic.ttf",
    "JetBrainsMono-Regular.ttf": "examples/assets/fonts/JetBrainsMono-Regular.ttf",
}
# The fabricated README desktop's first workspace, grouped into columns.
COLUMNS = [
    [
        ("Fix flaky login test", "com.mitchellh.ghostty", "back", "claude --resume 7c1e2f0a"),
        ("Draft release notes", "com.mitchellh.ghostty", "missed", "no session to resume"),
    ],
    [
        ("pi · rate-limiter refactor", "com.mitchellh.ghostty", "back", "pi --session 3f9a1c7e"),
        ("/work/garden-api", "com.mitchellh.ghostty", "back", "shell in /work/garden-api"),
    ],
    [
        ("npm run dev", "com.mitchellh.ghostty", "back", "npm run dev"),
        ("Audit-log migration", "com.mitchellh.ghostty", "back", "claude --resume 5d2b8e41"),
    ],
    [("garden-api – IntelliJ IDEA", "jetbrains-idea", "missed", "X11 window")],
]

CSS = """
@font-face { font-family:Inter; src:url("assets/fonts/Inter-Regular.ttf"); font-weight:400; }
@font-face { font-family:Inter; src:url("assets/fonts/Inter-Bold.ttf"); font-weight:700; }
@font-face { font-family:"Instrument Serif"; src:url("assets/fonts/InstrumentSerif-Italic.ttf"); font-style:italic; }
@font-face { font-family:"JetBrains Mono"; src:url("assets/fonts/JetBrainsMono-Regular.ttf"); }
html, body { margin:0; background:#0b1418; }
* { box-sizing:border-box; margin:0; padding:0; }
#film { position:relative; width:1920px; height:1080px; overflow:hidden; background:#0b1418; font-family:Inter; color:#eaf0e8; }
.scene { position:absolute; left:0; top:0; width:1920px; height:1080px; overflow:hidden;
  background:radial-gradient(circle at 78% 18%, #1d3a40 0%, #101d22 46%, #0b1418 100%); }
.fade { animation:fadein .4s ease-out both; }
.tag { position:absolute; left:120px; top:84px; font-family:"JetBrains Mono"; font-size:22px; letter-spacing:5px; color:#8ed7c3; text-transform:uppercase; }
.num { position:absolute; right:120px; top:84px; font-family:"JetBrains Mono"; font-size:22px; letter-spacing:5px; color:#456268; }
.title { position:absolute; left:120px; top:136px; font-family:"Instrument Serif"; font-style:italic; font-size:104px; line-height:1.05; }
.sub { position:absolute; left:124px; top:268px; font-family:"JetBrains Mono"; font-size:26px; color:#a8bab5; }
.mint { color:#8ed7c3; } .coral { color:#ffafa9; }

.desk { position:absolute; left:120px; top:316px; width:1680px; height:676px; border-radius:18px;
  background:#0f1c21; border:1px solid #2b444b; box-shadow:0 40px 90px rgba(0,0,0,.45); padding:26px 30px; }
.desk .ws { font-family:"JetBrains Mono"; font-size:20px; letter-spacing:3px; color:#6f8c91; margin-bottom:18px; }
.cols { display:flex; gap:22px; }
.col { width:383px; display:flex; flex-direction:column; gap:18px; }
.tile { position:relative; height:262px; border-radius:10px; background:#192c32; border:1px solid #2f4a51; padding:24px 26px; overflow:hidden; }
.tile .t { font-size:30px; font-weight:700; line-height:1.15; }
.tile .a { font-family:"JetBrains Mono"; font-size:20px; color:#6f8c91; margin-top:8px; }
.tile .d { font-family:"JetBrains Mono"; font-size:22px; color:#a8bab5; margin-top:14px; }
.tile .badge { position:absolute; left:26px; bottom:20px; font-family:"JetBrains Mono"; font-size:26px; letter-spacing:3px; }
.edge { position:absolute; left:0; top:0; width:8px; height:262px; }
.edge.back { background:#8ed7c3; } .edge.missed { background:#ffafa9; }

.capture { position:absolute; left:120px; top:352px; width:1680px; display:flex; gap:48px; }
.blueprint { width:620px; height:480px; border:2px solid #8ed7c3; border-radius:16px; padding:32px; background:#101d22; }
.blueprint .label { font-family:"JetBrains Mono"; font-size:26px; color:#8ed7c3; margin-bottom:28px; }
.bpcols { display:flex; gap:18px; }
.bpcol { width:170px; display:flex; flex-direction:column; gap:18px; }
.bptile { height:132px; border:2px solid #456268; background:#192c32; border-radius:8px; }
.bptile.short { height:90px; }
.savecard { width:1012px; height:480px; border:1px solid #2f4a51; border-left:8px solid #8ed7c3; border-radius:16px; background:#192c32; padding:36px 40px; }
.savecard .cmd { font-family:"JetBrains Mono"; font-size:32px; color:#8ed7c3; margin-bottom:32px; }
.snaprow { font-size:34px; margin-top:20px; color:#eaf0e8; }
.snaprow.muted { font-size:28px; color:#a8bab5; }
.saved { margin-top:30px; font-family:"JetBrains Mono"; font-size:26px; letter-spacing:3px; color:#8ed7c3; }

.update-track { position:absolute; left:120px; top:360px; display:flex; gap:30px; }
.step { position:relative; width:540px; height:420px; border:1px solid #2f4a51; border-radius:16px; background:#192c32; padding:36px; }
.step .label { font-family:"JetBrains Mono"; font-size:26px; color:#8ed7c3; letter-spacing:2px; }
.step .big { font-size:54px; line-height:1.15; font-weight:700; margin-top:32px; }
.step .detail { font-size:30px; color:#a8bab5; margin-top:26px; }
.step .bar { position:absolute; left:36px; bottom:40px; width:468px; height:8px; background:#456268; }
.step .progress { height:8px; background:#8ed7c3; width:468px; }

.cards { position:absolute; left:120px; top:360px; width:1680px; display:flex; flex-wrap:wrap; gap:28px; }
.card { width:826px; height:214px; border-radius:16px; background:#192c32; border:1px solid #2f4a51; padding:34px 40px; position:relative; overflow:hidden; }
.card .n { font-size:50px; font-weight:700; }
.card .c { font-family:"JetBrains Mono"; font-size:30px; color:#8ed7c3; margin-top:26px; }
.card .h { position:absolute; right:40px; top:44px; font-family:"JetBrains Mono"; font-size:22px; letter-spacing:2px; color:#6f8c91; }
.card .bar { position:absolute; left:0; top:0; width:6px; height:214px; background:#8ed7c3; }

.page { position:absolute; left:120px; top:322px; width:1680px; height:710px; border-radius:18px; background:#101d22;
  border:1px solid #2b444b; box-shadow:0 40px 90px rgba(0,0,0,.5); padding:40px 54px; overflow:hidden; }
.page .k { font-family:"JetBrains Mono"; font-size:18px; letter-spacing:4px; color:#8ed7c3; }
.page .h1 { font-family:"Instrument Serif"; font-style:italic; font-size:46px; color:#a8bab5; margin-top:6px; }
.page .sum { font-family:"Instrument Serif"; font-style:italic; font-size:100px; line-height:1.1; margin-top:6px; }
.legend { display:flex; flex-wrap:wrap; gap:12px 40px; margin-top:18px; width:1560px; }
.legend .li { width:740px; display:flex; align-items:center; gap:14px; border-left:6px solid #8ed7c3; padding:4px 0 4px 16px; font-size:26px; color:#a8bab5; }
.legend .li.x { border-left:6px solid #ffafa9; }
.legend .lk { font-family:"JetBrains Mono"; font-size:22px; color:#8ed7c3; }
.legend .x .lk { color:#ffafa9; }
.miss { display:flex; align-items:center; gap:30px; height:88px; border-top:1px solid #2b444b; }
.miss .w { width:480px; flex-shrink:0; font-size:32px; font-weight:700; }
.miss .r { width:660px; flex-shrink:0; font-size:27px; color:#ffafa9; }
.miss .code { font-family:"JetBrains Mono"; font-size:22px; color:#ffafa9; }

.rules { position:absolute; left:120px; top:360px; width:1680px; display:flex; flex-direction:column; gap:30px; }
.rule { display:flex; align-items:center; gap:30px; font-size:52px; font-weight:700; }
.rule .m { width:16px; height:56px; border-radius:4px; background:#8ed7c3; }
.end { position:absolute; left:0; top:0; width:1920px; height:1080px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:30px; }
.end .logo { font-family:"Instrument Serif"; font-style:italic; font-size:150px; line-height:1; letter-spacing:-2px; }
.end .ver { font-family:"JetBrains Mono"; font-size:30px; letter-spacing:6px; color:#0b1418; background:#8ed7c3; padding:10px 22px; border-radius:10px; }
.end .promise { font-size:44px; color:#8ed7c3; }
.end .cmd { font-family:"JetBrains Mono"; font-size:40px; background:#192c32; border:1px solid #2f4a51; padding:22px 40px; border-radius:14px; }
.end .url { font-family:"JetBrains Mono"; font-size:28px; color:#8ed7c3; }
.end .cr { font-size:24px; color:#6f8c91; }
.blackout { position:absolute; left:0; top:0; width:1920px; height:1080px; background:#000000; }
.blackout .shout { position:absolute; left:120px; top:380px; font-family:Inter; font-weight:700; font-size:160px; color:#ffafa9; }
.blackout .hope { position:absolute; left:124px; top:600px; font-size:42px; color:#8ed7c3; }
.blackout .loss { position:absolute; left:124px; top:680px; font-family:"JetBrains Mono"; font-size:32px; color:#a8bab5; }

@keyframes fadein { from { opacity:0; } to { opacity:1; } }
@keyframes fadeup { from { opacity:0; transform:translateY(34px); } to { opacity:1; transform:translateY(0px); } }
@keyframes slidein { from { opacity:0; transform:translateX(110px); } to { opacity:1; transform:translateX(0px); } }
@keyframes rise { from { opacity:0; transform:translateY(90px); } to { opacity:1; transform:translateY(0px); } }
@keyframes fly { from { opacity:0; transform:translateY(-120px) scale(.72); } to { opacity:1; transform:translateY(0px) scale(1); } }
@keyframes ghost { from { opacity:0; transform:scale(.94); } to { opacity:.55; transform:scale(1); } }
@keyframes pop { from { opacity:0; transform:scale(.6); } to { opacity:1; transform:scale(1); } }
@keyframes fill { from { width:0px; } to { width:468px; } }
"""


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def anim(*parts: str) -> str:
    return f' style="animation:{", ".join(parts)}"'


def desk(mode: str, t0: float) -> str:
    """Animate the fabricated desktop arriving, or reopening with explicit misses."""
    label = (
        "DP-1 / WORKSPACE 1 · GARDEN-API"
        if mode == "build"
        else "STAY IDLE UNTIL REOPENING FINISHES · DEMO WORKSPACE 1"
    )
    out = [
        f'<div class="desk"{anim(f"fadeup .7s ease-out {t0:.2f}s both")}>',
        f'<div class="ws">{label}</div><div class="cols">',
    ]
    k = 0
    for column in COLUMNS:
        out.append('<div class="col">')
        for title, app, status, detail in column:
            start = t0 + 0.35 + 0.20 * k
            if mode == "build":
                style = anim(f"slidein .6s ease-out {start:.2f}s both")
                inner = f'<div class="d">{esc(detail if status == "back" else "")}</div>'
            else:
                name = "fly" if status == "back" else "ghost"
                style = anim(f"{name} .6s ease-out {start:.2f}s both")
                label = "BACK" if status == "back" else "NOT REOPENED"
                color = "mint" if status == "back" else "coral"
                inner = (
                    f'<div class="edge {status}"></div><div class="d {color}">{esc(detail)}</div>'
                    f'<div class="badge {color}"'
                    + anim(f"pop .35s ease-out {start + 0.5:.2f}s both")
                    + f">{label}</div>"
                )
            out.append(
                f'<div class="tile"{style}><div class="t">{esc(title)}</div>'
                f'<div class="a">{esc(app)}</div>{inner}</div>'
            )
            k += 1
        out.append("</div>")
    return "".join(out) + "</div></div>"


def header(tag: str, title: str, subtitle: str, t0: float) -> str:
    return (
        f'<div class="tag">{esc(tag)}</div><div class="title"'
        + anim(f"fadeup .6s ease-out {t0 + 0.15:.2f}s both")
        + f'>{title}</div><div class="sub">{esc(subtitle)}</div>'
    )


def scene(sid: str, start: float, duration: float, body: str, number: str) -> str:
    fade = "" if start == 0 else f' class="scene fade" style="animation-delay:{start:.2f}s"'
    head = fade or ' class="scene"'
    return (
        f'<div id="{sid}"{head}'
        f' data-start="{start:.2f}" data-duration="{duration:.2f}">'
        f'<div class="num">{number} / 09</div>{body}</div>'
    )


def build() -> str:
    s = [
        scene(
            "desktop",
            0,
            5,
            header("fabricated demo · niri desktop continuity", "You built this desktop.", "", 0)
            + desk("build", 0.7),
            "01",
        )
    ]
    # Snapshot the desktop, never imply a disk image or running-process checkpoint.
    blueprint = "".join(
        '<div class="bpcol">'
        + "".join(
            f'<div class="bptile{" short" if i == 2 else ""}"'
            + anim(f"pop .4s ease-out {5.6 + 0.18 * i + 0.1 * j:.2f}s both")
            + "></div>"
            for j in range(2 if i < 2 else 1)
        )
        + "</div>"
        for i in range(3)
    )
    saved = (
        '<div class="capture"><div class="blueprint"'
        + anim("rise .6s ease-out 5.3s both")
        + '><div class="label">YOUR DESKTOP → SNAPSHOT</div><div class="bpcols">'
        + blueprint
        + '</div></div><div class="savecard"'
        + anim("slidein .7s ease-out 5.7s both")
        + '><div class="cmd">niri-desktop-continuity capture</div>'
        '<div class="snaprow">Workspaces · columns · widths</div>'
        '<div class="snaprow">Reopen recipes · known agent session IDs</div>'
        '<div class="snaprow muted">A map back to your work, saved to disk.</div>'
        '<div class="saved"'
        + anim("pop .4s ease-out 7.8s both")
        + ">DEMO SNAPSHOT SAVED</div></div></div>"
        '<div class="sub" style="top:900px">Automatic snapshots every 15 min after you opt in.</div>'
    )
    s.append(
        scene(
            "snapshot",
            5,
            6,
            header(
                "01 / save",
                "Save your place.",
                "Desktop layout + reopen recipes. Not an OS or memory backup.",
                5,
            )
            + saved,
            "02",
        )
    )
    steps = [
        ("YOUR UPDATE TOOL", "Install OS updates.", "You do this."),
        ("YOUR REBOOT", "Start the new kernel.", "The old processes end."),
        ("SAVED DESKTOP", "Your map stays on disk.", "Ready for the next login."),
    ]
    update = (
        '<div class="update-track">'
        + "".join(
            '<div class="step"'
            + anim(f"rise .6s ease-out {11.5 + 0.5 * i:.2f}s both")
            + f'><div class="label">{esc(label)}</div><div class="big">{esc(title)}</div>'
            f'<div class="detail">{esc(detail)}</div><div class="bar"><div class="progress"'
            + anim(f"fill 1.2s ease-out {12 + 0.5 * i:.2f}s both")
            + "></div></div></div>"
            for i, (label, title, detail) in enumerate(steps)
        )
        + "</div>"
    )
    s.append(
        scene(
            "update",
            11,
            5,
            header(
                "planned / update + reboot",
                "Update the OS. Reboot.",
                "You install updates. This tool reopens your desktop afterward.",
                11,
            )
            + update
            + '<div class="sub" style="top:900px">Hibernate resumes the old system. This is a fresh start.</div>',
            "03",
        )
    )
    # A separate alternative, not a power failure during the illustrated OS update.
    # Four seconds of setup, then four seconds of blackout. Keep the reading pause
    # instead of covering the title while its entrance animation is still running.
    # One abrupt cut to black; no flashing or repeated glitch/strobe effects.
    outage = (
        header("or / unexpected shutdown", "Or, without warning…", "While you are working.", 16)
        + desk("build", 13)
        + '<div class="blackout"'
        + anim("fadein .01s steps(1,end) 20s both")
        + '><div class="tag coral">OR / AN UNEXPECTED SHUTDOWN</div>'
        '<div class="shout">POWER OUT.</div>'
        '<div class="hope">A saved snapshot may survive.</div>'
        '<div class="loss">Unsaved work does not.</div></div>'
    )
    s.append(scene("blackout", 16, 8, outage, "04"))
    s.append(
        scene(
            "reopen",
            24,
            6,
            header(
                "after a successful boot / log in",
                'Fresh session. <span class="mint">Familiar places.</span>',
                "Needs a usable saved snapshot. Unsaved drafts and running jobs are not restored.",
                24,
            )
            + desk("back", 24.3),
            "05",
        )
    )
    agents = [
        ("Claude Code", "claude --resume 7c1e2f0a-3b5d", "session registry"),
        ("Pi", "pi --session …/3f9a1c7e.jsonl", "presence file"),
        ("nodecode", "nodecode -p main resume s-4KX2QW7M", "shell record"),
        ("Codex", "codex resume 0199a1f2-b8e4", "SessionStart hook"),
    ]
    cards = "".join(
        '<div class="card"'
        + anim(f"rise .6s ease-out {30.6 + 0.22 * i:.2f}s both")
        + f'><div class="bar"></div><div class="h">{esc(how)}</div><div class="n">{esc(name)}</div>'
        f'<div class="c">{esc(cmd)}</div></div>'
        for i, (name, cmd, how) in enumerate(agents)
    )
    s.append(
        scene(
            "agents",
            30,
            6,
            header(
                "conversations",
                'Same conversation. <span class="mint">New process.</span>',
                "Known sessions resume by ID, rather than replaying the opening prompt.",
                30,
            )
            + f'<div class="cards">{cards}</div>',
            "06",
        )
    )
    misses = [
        (
            "Draft release notes",
            "Claude process without a session registry entry",
            "claude-session-unregistered",
        ),
        (
            "garden-api – IntelliJ IDEA",
            "X11 window: niri reports only the bridge",
            "xwayland-client",
        ),
        (
            "Grafana: API latency — Brave",
            "launched, but no new window appeared in time",
            "not-detected",
        ),
    ]
    rows = "".join(
        '<div class="miss"'
        + anim(f"slidein .55s ease-out {39.2 + 0.5 * i:.2f}s both")
        + f'><div class="w">{esc(w)}</div><div class="r">{esc(r)}</div><div class="code">{esc(c)}</div></div>'
        for i, (w, r, c) in enumerate(misses)
    )
    legend = "".join(
        f'<div class="li{x}"><div class="lk">{esc(k)}</div><div>{esc(v)}</div></div>'
        for k, v, x in [
            ("BACK", "reopened and moved to its saved place", ""),
            ("ALREADY OPEN", "this session was open already", ""),
            ("APP ALREADY RUNNING", "not launched a second time", ""),
            ("NOT BACK", "listed below with the reason", " x"),
        ]
    )
    result = (
        '<div class="page"' + anim("rise .8s ease-out 36.5s both") + ">"
        '<div class="k">NIRI / DESKTOP CONTINUITY</div><div class="h1">What came back</div>'
        '<div class="sum"><span class="mint"><span id="nback" data-reel data-reel-start="1.3"'
        ' data-reel-duration="1.4" data-reel-stagger="0.15" data-reel-spins="1">20</span>'
        ' of 23 came back</span> · <span class="coral">3 did not</span></div>'
        f'<div class="legend">{legend}</div>{rows}</div>'
    )
    s.append(
        scene(
            "results",
            36,
            7,
            header(
                "results · fabricated demo",
                'See <span class="mint">what came back.</span>',
                "The result page opens when the reopen is over. Misses have reasons.",
                36,
            )
            + result,
            "07",
        )
    )
    rules = [
        "Never closes a window.",
        "Never moves one that was already open.",
        "Never replays an agent it cannot resume.",
    ]
    lines = "".join(
        '<div class="rule"'
        + anim(f"slidein .45s ease-out {43.4 + 0.3 * i:.2f}s both")
        + f'><div class="m"></div><div>{esc(text)}</div></div>'
        for i, text in enumerate(rules)
    )
    s.append(
        scene(
            "limits",
            43,
            4,
            header(
                "boundaries",
                "Reopen work. Respect what's running.",
                "No daemon. No network. Login restore is opt-in.",
                43,
            )
            + f'<div class="rules">{lines}</div>',
            "08",
        )
    )
    end = (
        '<div class="end"><div class="logo"'
        + anim("fadeup .7s ease-out 47.2s both")
        + '>niri-desktop-continuity</div><div class="ver"'
        + anim("pop .4s ease-out 47.6s both")
        + f">v{VIDEO_VERSION}</div>"
        '<div class="promise">Save your place. Find your way back.</div><div class="cmd"'
        + anim("fadeup .6s ease-out 47.9s both")
        + ">pipx install niri-desktop-continuity</div>"
        '<div class="url">github.com/tryingET/niri-desktop-continuity</div>'
        '<div class="cr">for niri, the scrollable-tiling Wayland compositor by YaLTeR</div></div>'
    )
    s.append(scene("end", 47, 5, end, "09"))
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>' + CSS + "</style></head><body>"
        f'<div id="film" data-composition-id="ndc-032" data-no-timeline data-width="{W}" data-height="{H}"'
        f' data-fps="{FPS}" data-duration="{DURATION}" data-motion-blur="4">'
        + "".join(s)
        + "</div></body></html>"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    director, out = Path(sys.argv[1]), Path(sys.argv[2])
    (out / "assets/fonts").mkdir(parents=True, exist_ok=True)
    for name, source in FONTS.items():
        shutil.copyfile(director / source, out / "assets/fonts" / name)
    (out / "announce.html").write_text(build())
    print(out / "announce.html")
