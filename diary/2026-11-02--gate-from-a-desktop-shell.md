---
summary: "just check gives the same result in a desktop terminal as on a runner; the offline-cache tests skip with a reason."
read_when:
  - "A test passes on the runner but fails in a desktop terminal, or the reverse."
  - "Changing tests/conftest.py or the installed-wheel jail tests."
type: "diary"
---

# The gate no longer depends on the terminal it runs in

Run from a terminal inside Niri, `just check` failed 61 native resource tests: their jail workers
assert that no display variable reaches them, and the conftest removed only `NIRI_SOCKET`. It now
removes `WAYLAND_DISPLAY`, `WAYLAND_SOCKET` and `DISPLAY` as well, for every test.

The two installed-wheel jail tests failed outright without `UV_CACHE_DIR`, because they copy that
cache into the jail to build the wheel offline. They now skip with a reason that points to
`docs/engineering.local.md`, which describes the whole local test environment: display variables,
`umask 022`, a `/usr`-based `.venv`, a short real `TMPDIR` and how to fill a private cache.

Proof: from a desktop shell, the 64 resource tests pass and the two installed-wheel tests skip with
the stated reason; before the change the same command failed. umask handling was not added: the
fixtures' umask need is documented, and nothing failed for it on this workstation.
