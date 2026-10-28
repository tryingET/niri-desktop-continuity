---
summary: "Why hosted CI failed 287 tests since 2026-10-06, what the workflow now provides, and why native jail tests skip there."
read_when:
  - "GitHub CI fails while the local full gate passes."
  - "Changing the CI or release workflow, or the native jail helper."
type: "diary"
---

# CI runner environment

Every CI run on main since 2026-10-06 failed 287 tests while the local full gate passed. None of
the failures were in the code; the runner lacked what the suite assumes:

- `TMPDIR` was unset, and four test drivers read it directly to bind short AF_UNIX sockets.
- Ubuntu's AppArmor blocks the unprivileged user namespaces that the jail tests create.
- Ubuntu 24.04's headers lack the pidfd namespace ioctls that one test checks against the
  system's `linux/pidfd.h`.
- `uv sync` caches wheels but not index entries, so an installed-wheel test's offline
  `uv pip install pytest==9.1.1` could not resolve.

The CI and release workflows now run on `ubuntu-26.04` (kernel 7.0, Python 3.14 under `/usr`) with
a private `TMPDIR` under the runner's home (the product refuses socket paths below a group- or
world-writable directory such as `/tmp`), the system interpreter, user namespaces allowed, the dev
group's index entries cached and umask 022. That left 204 failures, all in the native exited-shell
tests: the jailed product code refuses kernels below 7.2.6 by design, and no hosted runner has one
yet.

`isolated_namespace` now skips, with the platform check's own reason, when the running kernel
fails `restore_exited_syscalls.profile()`. On a supported kernel nothing changes, and the full
local gate still runs these tests. The workflow also keeps `cc` (an `/etc/alternatives` link on
Ubuntu) and `uv` inside `/usr`, the only system tree the jail binds; this takes effect once a
hosted kernel reaches 7.2.6 and the jail tests run there.
