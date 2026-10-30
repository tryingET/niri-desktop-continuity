---
summary: "One incoherent capture before a reboot blocked the login restore; capture now reads again and selection falls back within the same Niri instance."
read_when:
  - "Changing capture coherence, the capture command's retry or default restore snapshot selection."
type: "diary"
---

# An incoherent last capture must not cost the whole desktop

A login restore refused to reopen anything. The last periodic capture before the reboot was
incoherent (the desktop changed between capture's two readings; a focus switch is enough), and
default selection treated incoherence as a hard refusal, although a display-valid capture of the
same session from one timer interval earlier was available. About 1% of stored captures were
incoherent; the refusal only matters when one happens to be the last before a reboot.

Two changes, both read-only:

- The `capture` command takes up to three readings, 1 s apart, and saves the first coherent one or
  else the last. Only this command retries: approve, verify, reconcile and recovery still use a
  single `probe.capture`, so their admission is unchanged. Output gains `samples` only when more
  than one reading was taken, so existing exact-output callers are unaffected.
- An incoherent `latest-observed` selects `last-display-valid` when both carry the same compositor
  identity (boot ID, socket path, inode, device). A different identity refuses: the latest
  session's desktop is unknown, and an earlier session's desktop must not stand in for it. The
  workspace-reference check and the same-instance login skip apply as for the display fallback.

Tests: the selection oracle names the fallback digest, the window and argv expected from the
fabricated fixture, the `latest-incoherent` diagnostic, refusal for a different boot ID or socket
inode, the login skip in the running instance and refusal without a valid fallback. The retry
oracle lists the coherence sequence, the sample returned and the pauses taken.
