---
summary: "Offline fixed-width CLI correction; exact representability and retained-history refusal."
type: "diary"
---

# Fixed-width CLI serialization — offline correction

The parent reports that the separately retained native attempt failed at fixed-width CLI parsing;
it did not pass and remains unresolved. The prior reviewed **926-test** source gate is superseded
by this correction. No native command, actual history/profile/state inspection, settlement, retry,
cleanup, deployment or canonical installation change was performed here. Capture selection and
cwd handling are unchanged; capture's unknown-cwd utility case needs its separate owner decision.

## Source facts and implementation

Public Niri pin `62c230a662ac913a54fc49c86fda0406da3f3ba9` was read, not executed:

- [`niri-ipc/src/lib.rs` 948–974, 1784–1862](https://github.com/YaLTeR/niri/blob/62c230a662ac913a54fc49c86fda0406da3f3ba9/niri-ipc/src/lib.rs#L1784-L1862):
  fixed width is `i32`; fixed position is `f64`. `800` sets a width; `800.0` is invalid.
  Signed widths are native adjustments, not admitted fixed requests. Positions retain float grammar.
- [`scrolling.rs` 4990–5042](https://github.com/YaLTeR/niri/blob/62c230a662ac913a54fc49c86fda0406da3f3ba9/src/layout/scrolling.rs#L4990-L5042):
  fixed sizing adds decorations then clamps tile width to 1–100000.
- [`tile.rs` 938–984](https://github.com/YaLTeR/niri/blob/62c230a662ac913a54fc49c86fda0406da3f3ba9/src/layout/tile.rs#L938-L984):
  native size requests subtract borders and floor to Wayland integers. Addition can reconstruct a
  float exactly while inverse subtraction falls below the integer and loses a pixel.

The width helper selects a positive i32 candidate and requires exact reconstructed tile equality,
the native tile range and an unchanged inverse floor. Candidate selection is not permission to
round or truncate requested geometry. Seed preflight occurs after association and before its
placement actions; refusal does not undo launch or authorize cleanup. Already-exact widths need
no resize; shared-column donors inherit seed geometry without a separate resize requirement.
Offline history uses the same token and prediction rules. Invalid old decimal-token intents stay
blocked; no migration or history rewriting was implemented. Physical-grid position policy is unchanged.

The independent handwritten oracle no longer accepts arbitrary `float()` width tokens. Editable
and wheel console tests now send layout actions through the real subprocess transport to fabricated
CLI/socket fixtures, with invalid width arguments returning exit 2 before model effects. Size and
position parser fixtures are compiler-free; console host integration still requires a C compiler.

## Observed validation

- Initial RED, original runtime: **28 failed, 23 passed** (12.15s). Both installed consoles and
  the integral-float resize outcome fail; rehashed decimal-token history was incorrectly accepted.
- Additional native-floor RED: **1 failed, 27 passed** (10.76s).
- Inheritance regression RED after strict sizing: **3 failed, 28 deselected** (1.25s).
- Final targeted GREEN: **214 passed**, no skips (81.15s), including both installed consoles,
  fractional/nonrepresentable geometry, inheritance, exact no-resize, semantic rehash attacks,
  floating pixel-grid behavior, reopen and unchanged capture-selection tests.
- Ruff check and formatting check passed for all eight changed Python files.

Targeted command (not the full repository gate):

```sh
UV_OFFLINE=1 .venv/bin/pytest -q tests/test_restore_width.py tests/test_restore_cli_grammar.py \
  tests/test_restore_console.py tests/test_restore_dimensions.py tests/test_restore_bounded.py \
  tests/test_restore_lifecycle.py tests/test_restore_semantics.py tests/test_restore_integration.py \
  tests/test_reopen.py tests/test_restore_capture_selection.py
```

## Limits and next gate

This is source/synthetic evidence, not a native pass. Measured decoration is not complete native
state: client constraints and scale-dependent window-size quantization (`tile.rs` 803–845) can
still fail exact postconditions. Earlier hosts may already have effects before a later host's
measured-width refusal; no all-host prelaunch geometry proof is claimed. No tolerance or retry follows.
Parent review and full CI remain pending, followed by independent history disposition before any
separately approved native operation. The interrupted attempt must not be altered to fit new code.
