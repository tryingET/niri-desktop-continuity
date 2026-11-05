---
summary: "The 0.3.2 snapshot, OS-update and reboot tour, and how to render it with Director."
read_when:
  - "You make or update an announcement video for a release."
---

# Announcement video

[`niri-desktop-continuity-0.3.2.mp4`](niri-desktop-continuity-0.3.2.mp4) is the 52-second tour:
1920x1080, 30 fps, H.264 in standard video range, no audio. Its story is **Save your place. Update
your OS. Reboot. Reopen.** An alternative **unexpected power cut** interrupts the desktop with a
single abrupt cut to black and “POWER OUT.”, not repeated flashing. Every window, title, session id
and command is fabricated. No real capture, OS update, power cut or desktop action runs.

| Time | Scene |
|---|---|
| 0–5 s | The desktop you built |
| 5–11 s | `capture` saves layout and reopen recipes; opt-in automatic snapshots are explained |
| 11–16 s | Planned: you install OS updates with your own tools and reboot into the new kernel |
| 16–20 s | “Or, without warning…” stays on screen for a four-second setup before the cut |
| 20–24 s | “POWER OUT.” and the saved-snapshot/unsaved-work caveat hold for four seconds |
| 24–30 s | After a successful boot, reopening needs a usable saved snapshot; unsaved drafts/jobs are not restored; stay idle |
| 30–36 s | Known agent conversations resume by ID |
| 36–43 s | The fabricated result page shows 20 of 23 back and explains the three misses |
| 43–47 s | Protected-window and no-prompt-replay boundaries |
| 47–52 s | The 0.3.2 end card |

A desktop snapshot is not an OS image or a memory backup. The update scene assigns the update to
the operator, not this tool, and contrasts a new-kernel boot with hibernation's old-system resume.
The blackout is a separate alternative, not an illustration of OS-update failure or repair. Recovery
requires the OS to boot and a usable pre-loss snapshot to survive; there is no promise to recover
unsaved work. Completed hibernation and hybrid sleep can also survive power loss.
The original [0.3.1 announcement](niri-desktop-continuity-0.3.1.mp4) is retained unchanged.

[`build.py`](build.py) writes the film as an HTML composition for
[Director](https://github.com/stepupgaming/director), which renders HTML and CSS to video
without a browser. The windows are real layout, not screenshots, so every tile can animate.

## Render it again

From the repository root, run `python3 docs/announce/test_build.py` before rendering. The offline
timing tests require at least three fully entered seconds before the blackout covers the setup,
retain the blackout message's own reading time, and check a continuous timeline.

```sh
# 1. Build Director once (Rust, clang and the FFmpeg libraries); its target is about 2.5 GB.
cd <director-checkout>
CARGO_TARGET_DIR=<scratch>/director-target cargo build --release -p director-cli --bin director-engine
E=<scratch>/director-target/release/director-engine

# 2. Write the composition and its fonts.
python3 docs/announce/build.py <director-checkout> <out>

# 3. Check, look, render.
$E html check <out>/announce.html                         # compiles; lists unsupported markup
$E check <out>/announce.html --every 0.25 --safe-zone twitter
$E sheet <out>/announce.html -n 16 -c 4 --cell-width 480 -o <out>/sheet.png
$E still <out>/announce.html -t 8.5 -o <out>/snapshot.png
$E still <out>/announce.html -t 14.5 -o <out>/update.png
$E still <out>/announce.html -t 18.5 -o <out>/without-warning.png
$E still <out>/announce.html -t 21.5 -o <out>/blackout.png
$E still <out>/announce.html -t 41.5 -o <out>/result.png
$E render <out>/announce.html --scale 0.5 --draft-encode -o <out>/draft.mp4
$E render <out>/announce.html -o <out>/master.mp4

# 4. Director writes full-range video; convert to standard range with fast start for upload,
#    then drop every metadata tag so the repository's portability check admits the file.
ffmpeg -i <out>/master.mp4 -vf "scale=in_range=full:out_range=tv,format=yuv420p" \
  -c:v libx264 -profile:v high -preset slow -crf 16 -movflags +faststart -an <out>/x.mp4
ffmpeg -i <out>/x.mp4 -map 0:v -c copy -map_metadata -1 -fflags +bitexact -flags:v +bitexact \
  -movflags +faststart docs/announce/niri-desktop-continuity-<version>.mp4
python3 scripts/check-portability.py
```

The check admits a video only as `docs/announce/*.mp4`, at most 8 MiB, with no metadata box
beyond the empty one ffmpeg always writes and no handler name but `VideoHandler` or
`SoundHandler`.

`check` reports the rolling counter's digit strips as off canvas and clipped. It measures them
without the scroll animation that brings each digit into view, so read the still at 41.5 s
instead: it must show "20 of 23 came back".
