---
summary: "Detach the native fixture's former root before executing its payload."
read_when:
  - "Inspecting native-test root isolation and its verification limits."
type: "reference"
---

# Native-test root isolation

The namespace fixture now lazily detaches `/old-root` and removes its mountpoint
immediately after pivoting and changing to `/`, before payload exec. Both commands
are unconditional under the existing `set -eu`: either failure aborts execution.
Private mount propagation and existing read-only bindings are unchanged.

A new native behavioral regression checks absence through direct and proc-root
routes, refusal to open a fabricated outer-only marker through those routes, and
absence of old-root mountpoints in mountinfo. It is **unexecuted**, pending an
approved separate-kernel guest. Its `NIRI_TEST_SEPARATE_KERNEL_GUEST=1` opt-in is an
operator attestation, not automatic guest detection or isolation enforcement.

Host evidence used only:

```sh
python3 -I -B tests/test_restore_namespace_safety.py -v
```

- RED against the unchanged helper: four checks, one failure identifying the
  missing detach/removal before exec; exit 1.
- GREEN after correction: all four checks passed; exit 0.

This standalone standard-library unittest reads and parses source with AST; it
checks teardown ordering, errexit wiring, namespace argv and read-only bindings.
It imports neither product nor native-test code and executes no shell or native
payload. This is static source-contract evidence, not observed kernel isolation.
No pytest collection, native execution or full CI was performed. Runtime/kernel
verification and full CI remain pending the separate-kernel guest.

## Host verification (2026-10-28)

With this fixture, every exited-shell jail test file and the source checks ran under pytest in a
clean clone on a supported host kernel: 824 passed, and the guest-only behavioral test stayed
skipped without the attestation. The two installed-wheel jail cases failed the same way with and
without the change, because the offline cache held only a yanked build-backend release; they are
unrelated to the fixture. The old-root behavioral regression itself still awaits a separate-kernel
guest.
