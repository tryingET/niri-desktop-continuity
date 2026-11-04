#!/usr/bin/env python3
"""Generate the niri-desktop-continuity 0.3.1 announcement film as a Director HTML composition.

Usage: build.py DIRECTOR_CHECKOUT OUTPUT_DIRECTORY
Writes OUTPUT_DIRECTORY/announce.html and copies the four fonts it uses from the Director checkout
(Inter, Instrument Serif, JetBrains Mono; all under the SIL Open Font License) beside it.
See README.md here for rendering. Every window, title, session id and command below is fabricated
(the README's demo desktop); nothing comes from a real capture.
"""

from __future__ import annotations

import html
import shutil
import sys
from pathlib import Path

FONTS = {
    "Inter-Regular.ttf": "crates/director-core/assets/fonts/Inter-Regular.ttf",
    "Inter-Bold.ttf": "crates/director-core/assets/fonts/Inter-Bold.ttf",
    "InstrumentSerif-Italic.ttf": "examples/assets/fonts/InstrumentSerif-Italic.ttf",
    "JetBrainsMono-Regular.ttf": "examples/assets/fonts/JetBrainsMono-Regular.ttf",
}
W, H, FPS, DURATION = 1920, 1080, 30, 39

# The demo desktop's first workspace: columns of (title, app id, status, detail).
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
@font-face { font-family:"Instrument Serif"; src:url("assets/fonts/InstrumentSerif-Italic.ttf"); font-weight:400; font-style:italic; }
@font-face { font-family:"JetBrains Mono"; src:url("assets/fonts/JetBrainsMono-Regular.ttf"); font-weight:400; }
html, body { margin:0; background:#0b1418; }
* { box-sizing:border-box; margin:0; padding:0; }
#film { position:relative; width:1920px; height:1080px; overflow:hidden; background:#0b1418; font-family:Inter; color:#eaf0e8; }
.scene { position:absolute; left:0; top:0; width:1920px; height:1080px; overflow:hidden;
  background:radial-gradient(circle at 78% 18%, #1d3a40 0%, #101d22 46%, #0b1418 100%); }
.fade { animation:fadein .4s ease-out both; }
.tag { position:absolute; left:120px; top:84px; font-family:"JetBrains Mono"; font-size:22px; letter-spacing:5px; color:#8ed7c3; text-transform:uppercase; }
.num { position:absolute; right:120px; top:84px; font-family:"JetBrains Mono"; font-size:22px; letter-spacing:5px; color:#456268; }
.title { position:absolute; left:120px; top:136px; font-family:"Instrument Serif"; font-style:italic; font-size:104px; line-height:1.05; color:#eaf0e8; }
.sub { position:absolute; left:124px; font-family:"JetBrains Mono"; font-size:26px; color:#a8bab5; }
.mint { color:#8ed7c3; } .coral { color:#ffafa9; } .amber { color:#f5c875; }

.desk { position:absolute; left:120px; top:316px; width:1680px; height:676px; border-radius:18px;
  background:#0f1c21; border:1px solid #2b444b; box-shadow:0 40px 90px rgba(0,0,0,.45); padding:26px 30px; }
.desk .ws { font-family:"JetBrains Mono"; font-size:20px; letter-spacing:3px; color:#6f8c91; margin-bottom:18px; }
.cols { display:flex; gap:22px; }
.col { width:383px; display:flex; flex-direction:column; gap:18px; }
.tile { position:relative; height:262px; border-radius:10px; background:#192c32; border:1px solid #2f4a51; padding:24px 26px; overflow:hidden; }
.tile .t { font-size:30px; font-weight:700; color:#eaf0e8; line-height:1.15; }
.tile .a { font-family:"JetBrains Mono"; font-size:20px; color:#6f8c91; margin-top:8px; }
.tile .d { font-family:"JetBrains Mono"; font-size:22px; color:#a8bab5; margin-top:14px; }
.tile .badge { position:absolute; left:26px; bottom:20px; font-family:"JetBrains Mono"; font-size:26px; letter-spacing:3px; }
.edge { position:absolute; left:0; top:0; width:8px; height:262px; }
.edge.back { background:#8ed7c3; } .edge.missed { background:#ffafa9; }

.cards { position:absolute; left:120px; top:360px; width:1680px; display:flex; flex-wrap:wrap; gap:28px; }
.card { width:826px; height:214px; border-radius:16px; background:#192c32; border:1px solid #2f4a51; padding:34px 40px; position:relative; overflow:hidden; }
.card .n { font-size:50px; font-weight:700; color:#eaf0e8; }
.card .c { font-family:"JetBrains Mono"; font-size:30px; color:#8ed7c3; margin-top:26px; }
.card .h { position:absolute; right:40px; top:44px; font-family:"JetBrains Mono"; font-size:22px; letter-spacing:2px; color:#6f8c91; }
.card .bar { position:absolute; left:0; top:0; width:6px; height:214px; background:#8ed7c3; }

.pill { position:absolute; left:120px; top:78px; font-family:"JetBrains Mono"; font-size:22px; letter-spacing:4px; color:#0b1418;
  background:#8ed7c3; padding:8px 18px; border-radius:8px; }
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
.miss { display:flex; align-items:center; gap:30px; height:88px; border-top:1px solid #2b444b; margin-top:0px; }
.miss:first-of-type { margin-top:26px; }
.miss .w { width:480px; flex-shrink:0; font-size:32px; font-weight:700; color:#eaf0e8; }
.miss .r { width:660px; flex-shrink:0; font-size:27px; color:#ffafa9; }
.miss .code { font-family:"JetBrains Mono"; font-size:22px; color:#ffafa9; }

.rules { position:absolute; left:120px; top:360px; width:1680px; display:flex; flex-direction:column; gap:30px; }
.rule { display:flex; align-items:center; gap:30px; font-size:52px; font-weight:700; color:#eaf0e8; }
.rule .m { width:16px; height:56px; border-radius:4px; background:#8ed7c3; }
.rule .s { font-weight:400; color:#a8bab5; font-size:40px; }

.end { position:absolute; left:0; top:0; width:1920px; height:1080px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:30px; }
.end .logo { font-family:"Instrument Serif"; font-style:italic; font-size:150px; line-height:1; letter-spacing:-2px; color:#eaf0e8; }
.end .ver { font-family:"JetBrains Mono"; font-size:30px; letter-spacing:6px; color:#0b1418; background:#8ed7c3; padding:10px 22px; border-radius:10px; }
.end .cmd { font-family:"JetBrains Mono"; font-size:40px; color:#eaf0e8; background:#192c32; border:1px solid #2f4a51; padding:22px 40px; border-radius:14px; }
.end .url { font-family:"JetBrains Mono"; font-size:28px; color:#8ed7c3; }
.end .cr { font-size:24px; color:#6f8c91; margin-top:24px; }
.halo { position:absolute; left:460px; top:250px; width:1000px; height:560px; border-radius:280px;
  background:linear-gradient(90deg, #8ed7c3, #2f6f74, #ffafa9); filter:blur(150px); opacity:.0; }

@keyframes fadein { from { opacity:0; } to { opacity:1; } }
@keyframes fadeout { from { opacity:1; } to { opacity:0; } }
@keyframes fadeup { from { opacity:0; transform:translateY(34px); } to { opacity:1; transform:translateY(0px); } }
@keyframes slidein { from { opacity:0; transform:translateX(110px); } to { opacity:1; transform:translateX(0px); } }
@keyframes rise { from { opacity:0; transform:translateY(90px); } to { opacity:1; transform:translateY(0px); } }
@keyframes fall { from { opacity:1; transform:translateY(0px) rotate(0deg); } to { opacity:0; transform:translateY(420px) rotate(9deg); } }
@keyframes fallb { from { opacity:1; transform:translateY(0px) rotate(0deg); } to { opacity:0; transform:translateY(460px) rotate(-8deg); } }
@keyframes dim { from { opacity:1; } to { opacity:.18; } }
@keyframes fly { from { opacity:0; transform:translateY(-120px) scale(.72); } to { opacity:1; transform:translateY(0px) scale(1); } }
@keyframes ghost { from { opacity:0; transform:scale(.94); } to { opacity:.55; transform:scale(1); } }
@keyframes pop { from { opacity:0; transform:scale(.6); } to { opacity:1; transform:scale(1); } }
@keyframes glow { from { opacity:0; } to { opacity:.32; } }
"""


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def anim(*parts: str) -> str:
    return f' style="animation:{", ".join(parts)}"'


def desk(mode: str, t0: float) -> str:
    """One workspace. mode: 'build' (tiles slide in), 'fall' (tiles drop away), 'back' (return)."""
    dims = f", dim .7s ease-in {t0 + 1.5:.2f}s both" if mode == "fall" else ""
    out = [
        f'<div class="desk"{anim(f"fadeup .7s cubic-bezier(.2,.9,.2,1) {t0:.2f}s both{dims}")}>',
        '<div class="ws">DP-1 / WORKSPACE 1 · GARDEN-API</div><div class="cols">',
    ]
    k = 0
    for column in COLUMNS:
        out.append('<div class="col">')
        for title, app, status, detail in column:
            if mode == "build":
                style = anim(
                    f"slidein .6s cubic-bezier(.2,.9,.2,1) {t0 + 0.35 + 0.16 * k:.2f}s both"
                )
                inner = f'<div class="d">{esc(detail if status == "back" else "")}</div>'
            elif mode == "fall":
                name = "fall" if k % 2 == 0 else "fallb"
                style = anim(
                    f"{name} .75s cubic-bezier(.55,0,.8,.4) {t0 + 0.9 + 0.09 * k:.2f}s both"
                )
                inner = f'<div class="d">{esc(detail if status == "back" else "")}</div>'
            else:
                start = t0 + 0.9 + 0.28 * k
                if status == "back":
                    style = anim(f"fly .55s cubic-bezier(.18,1.35,.4,1) {start:.2f}s both")
                    inner = (
                        f'<div class="edge back"{anim(f"fadein .25s ease-out {start + 0.45:.2f}s both")}></div>'
                        f'<div class="d">{esc(detail)}</div>'
                        f'<div class="badge mint"{anim(f"pop .35s cubic-bezier(.2,1.6,.4,1) {start + 0.5:.2f}s both")}>'
                        "BACK</div>"
                    )
                else:
                    style = anim(f"ghost .6s ease-out {start:.2f}s both")
                    inner = (
                        f'<div class="edge missed"{anim(f"fadein .25s ease-out {start + 0.45:.2f}s both")}></div>'
                        f'<div class="d coral">{esc(detail)}</div>'
                        f'<div class="badge coral"{anim(f"pop .35s ease-out {start + 0.5:.2f}s both")}>'
                        "NOT REOPENED</div>"
                    )
            out.append(
                f'<div class="tile"{style}><div class="t">{esc(title)}</div>'
                f'<div class="a">{esc(app)}</div>{inner}</div>'
            )
            k += 1
        out.append("</div>")
    out.append("</div></div>")
    return "".join(out)


def scene(sid: str, start: float, duration: float, body: str, number: str) -> str:
    fade = "" if start == 0 else f' class="scene fade" style="animation-delay:{start:.2f}s"'
    head = fade or ' class="scene"'
    return (
        f'<div id="{sid}"{head} data-start="{start:.2f}" data-duration="{duration:.2f}">'
        f'<div class="num">{number} / 07</div>{body}</div>'
    )


def build() -> str:
    s = []
    # 1. The desktop you built.
    s.append(
        scene(
            "s1",
            0,
            4.4,
            '<div class="tag"'
            + anim("fadein .5s ease-out .15s both")
            + ">niri desktop continuity</div>"
            '<div class="title"'
            + anim("fadeup .8s cubic-bezier(.2,.9,.2,1) .25s both")
            + ">You built this desktop.</div>"
            + desk("build", 0.7),
            "01",
        )
    )
    # 2. Then you reboot.
    s.append(
        scene(
            "s2",
            4.4,
            3.2,
            '<div class="tag coral">reboot</div>'
            '<div class="title"'
            + anim("fadeup .6s cubic-bezier(.2,.9,.2,1) 4.5s both")
            + ">Then you reboot.</div>"
            '<div class="title coral" style="top:470px; left:0px; width:1920px; text-align:center; font-size:140px;'
            ' animation:fadeup .6s cubic-bezier(.2,.9,.2,1) 6.0s both">Everything is gone.</div>'
            + desk("fall", 4.4),
            "02",
        )
    )
    # 3. Log in. It comes back.
    s.append(
        scene(
            "s3",
            7.6,
            6.0,
            '<div class="tag">log in</div>'
            '<div class="title"'
            + anim("fadeup .6s cubic-bezier(.2,.9,.2,1) 7.7s both")
            + '>Log in. <span class="mint">It comes back.</span></div>'
            '<div class="sub" style="top:268px; animation:fadein .6s ease-out 10.9s both">'
            "each window on its workspace, in its column, at its width</div>" + desk("back", 7.6),
            "03",
        )
    )
    # 4. Agent sessions resume by id.
    agents = [
        ("Claude Code", "claude --resume 7c1e2f0a-3b5d", "session registry"),
        ("Pi", "pi --session …/3f9a1c7e.jsonl", "presence file"),
        ("nodecode", "nodecode -p main resume s-4KX2QW7M", "shell record"),
        ("Codex", "codex resume 0199a1f2-b8e4", "SessionStart hook"),
    ]
    cards = "".join(
        f'<div class="card"{anim(f"rise .6s cubic-bezier(.2,.9,.2,1) {14.3 + 0.22 * i:.2f}s both")}>'
        f'<div class="bar"></div><div class="h">{esc(how)}</div><div class="n">{esc(name)}</div>'
        f'<div class="c">{esc(cmd)}</div></div>'
        for i, (name, cmd, how) in enumerate(agents)
    )
    s.append(
        scene(
            "s4",
            13.6,
            6.0,
            '<div class="tag">agents</div>'
            '<div class="title"'
            + anim("fadeup .6s cubic-bezier(.2,.9,.2,1) 13.75s both")
            + '>Agent sessions <span class="mint">resume by id.</span></div>'
            f'<div class="cards">{cards}</div>'
            '<div class="sub" style="top:850px; animation:fadein .6s ease-out 16.2s both">'
            "An agent it cannot resume is never relaunched with its opening prompt.</div>",
            "04",
        )
    )
    # 5. New in 0.3: the result page.
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
        f'<div class="miss"{anim(f"slidein .55s cubic-bezier(.2,.9,.2,1) {23.2 + 0.5 * i:.2f}s both")}>'
        f'<div class="w">{esc(w)}</div><div class="r">{esc(r)}</div><div class="code">{esc(c)}</div></div>'
        for i, (w, r, c) in enumerate(misses)
    )
    legend = "".join(
        f'<div class="li{x}"{anim(f"fadein .4s ease-out {22.1 + 0.18 * i:.2f}s both")}><div class="lk">{esc(k)}</div><div>{esc(v)}</div></div>'
        for i, (k, v, x) in enumerate(
            [
                ("BACK", "reopened and moved to its saved place", ""),
                ("ALREADY OPEN", "this session was open already", ""),
                ("APP ALREADY RUNNING", "not launched a second time", ""),
                ("NOT BACK", "listed below with the reason", " x"),
            ]
        )
    )
    s.append(
        scene(
            "s5",
            19.6,
            9.0,
            '<div class="pill"'
            + anim("pop .45s cubic-bezier(.2,1.6,.4,1) 19.75s both")
            + ">NEW IN 0.3</div>"
            '<div class="title" style="top:136px; font-size:96px; animation:fadeup .6s cubic-bezier(.2,.9,.2,1) 19.9s both">'
            'Then it tells you <span class="mint">what came back.</span></div>'
            '<div class="page"' + anim("rise .8s cubic-bezier(.2,.9,.2,1) 20.4s both") + ">"
            '<div class="k">NIRI / DESKTOP CONTINUITY</div><div class="h1">What came back</div>'
            '<div class="sum"><span class="mint"><span id="nback" data-reel data-reel-start="1.3" data-reel-duration="1.4"'
            ' data-reel-stagger="0.15" data-reel-spins="1">20</span> of 23 came back</span>'
            ' · <span class="coral">3 did not</span></div>'
            f'<div class="legend">{legend}</div>{rows}</div>'
            '<div class="sub" style="top:258px; font-size:28px; animation:fadein .6s ease-out 25.2s both">'
            "It opens by itself when the reopen is over.</div>",
            "05",
        )
    )
    # 6. What it never does.
    rules = [
        ("Never closes a window.", ""),
        ("Never moves one that was already open.", ""),
        ("Never replays an agent it cannot resume.", ""),
        ("No daemon. No network.", "Nothing runs at login unless you opt in."),
    ]
    lines = "".join(
        f'<div class="rule"{anim(f"slidein .55s cubic-bezier(.2,.9,.2,1) {29.3 + 0.5 * i:.2f}s both")}>'
        f'<div class="m"></div><div>{esc(a)}</div>'
        + (f'<div class="s">{esc(b)}</div>' if b else "")
        + "</div>"
        for i, (a, b) in enumerate(rules)
    )
    s.append(
        scene(
            "s6",
            28.6,
            5.4,
            '<div class="tag">guarantees</div>'
            '<div class="title"'
            + anim("fadeup .6s cubic-bezier(.2,.9,.2,1) 28.75s both")
            + ">What it never does.</div>"
            f'<div class="rules">{lines}</div>',
            "06",
        )
    )
    # 7. End card.
    s.append(
        scene(
            "s7",
            34.0,
            5.0,
            '<div class="halo"' + anim("glow 1.4s ease-out 34.1s both") + '></div><div class="end">'
            '<div class="logo"'
            + anim("fadeup .9s cubic-bezier(.2,.9,.2,1) 34.2s both")
            + ">niri-desktop-continuity</div>"
            '<div class="ver"'
            + anim("pop .45s cubic-bezier(.2,1.6,.4,1) 34.75s both")
            + ">v0.3.1</div>"
            '<div class="cmd"'
            + anim("fadeup .6s cubic-bezier(.2,.9,.2,1) 35.1s both")
            + ">pipx install niri-desktop-continuity</div>"
            '<div class="url"'
            + anim("fadein .6s ease-out 35.5s both")
            + ">github.com/tryingET/niri-desktop-continuity</div>"
            '<div class="cr"'
            + anim("fadein .6s ease-out 35.9s both")
            + ">for niri, the scrollable-tiling Wayland compositor by YaLTeR</div>"
            "</div>",
            "07",
        )
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>' + CSS + "</style></head><body>"
        f'<div id="film" data-composition-id="ndc-031" data-no-timeline data-width="{W}" data-height="{H}"'
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
