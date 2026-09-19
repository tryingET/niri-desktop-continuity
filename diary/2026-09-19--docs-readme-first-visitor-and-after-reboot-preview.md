---
summary: "First-visitor README, an after-reboot ledger in preview, fabricated screenshots, session titles redacted from recipes, and app recipes that actually respawn."
read_when:
  - "You change the README, the preview's reopen ledger, docs screenshots or which binaries the portability check admits."
---

# 2026-09-19 — First-visitor README and the after-reboot preview

## What I Did

- Rewrote the README for someone arriving from a link: pitch, hero screenshot, why, a quickstart
  from install to `declare`, what the tool never does, honest limits. The recovery,
  reconstruction and resolution protocol prose moved verbatim to `docs/recovery.md` (now in the
  sdist allowlist, as the README it came from is).
- `preview` of a snapshot now answers "what comes back after a reboot": each tile states
  `reopens as <kind>` or `not reopened (<reason>)`, and an **After a reboot** ledger lists every
  window and extra tab session with the exact recorded command, directory and a plain reason for
  each miss. It reads the saved recipes the same way `restore` does (no argv, nothing launched),
  without importing `restore`. Plan previews are unchanged. `preview` without a digest uses the
  latest capture, as `restore` already did.
- Privacy fix found while checking the README's guarantees: a Claude recipe label is the session's
  AI title, which is also its terminal's window title, and it was stored even in redacted captures
  (Pi session names too). `normalized_snapshot` now clears recipe labels unless titles are
  included; nothing downstream reads them. `usage.md` also claimed capture never reads session
  logs, but the Claude title lookup scans the transcript for title records; the sentence now says so.
- Screenshots come only from `scripts/demo-desktop.py` (fabricated, `/work/...` paths) via
  `just screenshots` (headless Chromium, ImageMagick palette reduction). The portability check
  rejected every binary; it now admits PNGs directly under `docs/assets/`, well-formed, at most
  512 KiB, with only pixel/colour chunks (no text, EXIF, ICC or time chunks).
- Two restore bugs found while moving an Electron app from X11 to Wayland: niri spawns from its
  own working directory, so an `app` recipe like `electron .` started in the wrong place; `restore`
  now starts `app` recipes in their saved directory (`sh -c 'cd … && exec …'`, falling back when
  it is gone). And Chromium/Electron rewrite `/proc/PID/cmdline` into one space-joined title, so
  such a recipe was a single unrunnable argument; capture now splits it at a real program file,
  marks it for the preview, or records `process-title-unresolved`.

## What Surprised Me

- The honest "never" list was the best audit: two of the claims the old docs made were not true
  of the code.
- Headless Chromium's `--screenshot` of `page.html#fragment` produced a blank frame; hiding the
  other sections with one injected rule was simpler and deterministic.
- A real `/proc/PID/cmdline` can be a single NUL-terminated string: the argument boundaries are
  simply gone. A recipe that looked fine in a dry run would still have failed to spawn.
- An X11 window missed at login was easy to explain from the private receipt (`no-launch-command`)
  and the saved recipe (`xwayland-client`). The preview now shows that before the reboot.

## Patterns

- Tests with handwritten oracles first: counts in the ledger, a PNG assembled by hand for the
  checker, exact redaction before/after.
- Any page that shows a recipe must follow title privacy, not just the window tile.

## Crystallization Candidates

- → docs/learnings: write the "what it never does" list against the code, not against older
  docs; it finds stale guarantees.
- → possible feature: an operator-declared recipe for X11 windows keyed by app id, since
  `declare` is pinned to a terminal process and every X11 window shares the bridge's PID.
