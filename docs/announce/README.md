---
summary: "The 0.3.1 announcement video and how to render it again with Director."
read_when:
  - "You make or update an announcement video for a release."
---

# Announcement video

[`niri-desktop-continuity-0.3.1.mp4`](niri-desktop-continuity-0.3.1.mp4) is the 39-second
announcement of 0.3.1: 1920x1080, 30 fps, H.264 in standard video range, no audio, ready for X.
Every window, title, session id and command in it is fabricated, taken from the README's demo
desktop. No real capture went into it.

[`build.py`](build.py) writes the film as an HTML composition for
[Director](https://github.com/stepupgaming/director), which renders HTML and CSS to video
without a browser. The windows are real layout, not screenshots, so every tile can animate.

## Render it again

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
$E still <out>/announce.html -t 25.5 -o <out>/still.png
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
without the scroll animation that brings each digit into view, so read the still at 25.5 s
instead: it must show "20 of 23 came back".
