---
summary: "Native check interrupted; fixed-width and error-observation corrections pass the 981-test isolated gate."
read_when:
  - "You continue native qualification or design interrupted ordinary-restore disposition."
type: "validation"
---

# Post-canary offline validation

## Native result versus source result

An explicitly approved, single-window native experiment reached a fresh Ghostty host, associated
its window and observed an owned-column placement. It then interrupted at the CLI fixed-width
argument. The requested width was not achieved. This is partial native evidence, not a successful
restore, usable-session qualification, browser proof or deployment approval.

The existing windows and new test window were left running. The native history and immutable
private artifacts remain retained. No retry, process termination, rollback, fence clearing or
manual editing of runtime receipts occurred. The installed login runtime was not changed.

Native preparation also found that a running utility's cwd was unreadable. For that experiment,
the operator explicitly chose a future launch directory using the existing process-bound declaration
CLI. The declaration was absent beforehand, checked against the captured source and cleared before
apply. This did not recover the original cwd or fix automatic restoration of unknown-cwd recipes.
Such a recipe is still refused by the candidate until an explicit policy supplies its missing intent.

## Offline corrections

- Fixed widths use Niri's positive integer fixed-size grammar, not decimal float tokens. The source
  correction checks native range/clamp/inverse-floor constraints and exact reconstruction from
  observed decorations. Nonrepresentable requests refuse rather than silently round. Already-exact
  and shared-column inherited widths retain their distinct semantics; floating coordinates keep
  their separate floating-point grammar and physical-grid policy.
- Interrupted diagnostic observations previously persisted raw Niri window dictionaries, including
  title fields. They now use the same bounded, allowlisted geometry projection and validation as
  other restore state. Malformed observations yield `unavailable`, never a raw fallback. This does
  not promote ownership, dimension coverage, success or terminal accounting after an interruption.
- Existing private error artifacts were not rewritten to conceal the privacy defect. This is not
  universal receipt sanitization: intentional workspace names, recipes and exception text remain
  private data. The new regression fixtures contain only fabricated marker strings.

## Observed validation

| Scope | Result |
| --- | --- |
| Width implementation RED | 28 failed / 23 passed, plus separate floor and inheritance RED cases |
| Width implementation targeted GREEN | 214 passed, including editable and wheel console fixtures |
| Independent width review/test | no blocking finding; 58 focused cases and five additional probes passed |
| First post-width full gate | 979 passed; superseded by the diagnostic privacy correction |
| Privacy regression RED | 2 failed, proving marker retention in both normal and malformed error observations |
| Privacy/related targeted GREEN | 46 passed |
| Independent privacy review/test | no blocking finding; exactly 2 cases passed independently |
| Final controller-run `UV_OFFLINE=1 just ci` | **981 passed in 562.77 seconds**, exit zero |

The final gate also passed lint, formatting, portability/privacy checks, wheel/sdist builds and the
installed-console wheel smoke. No skips or xfails were reported. Counts overlap and must not be
summed. No native window action was performed to obtain these offline results. The final validation
log remains an external artifact; runtime and test bytes were not changed after the gate. This diary
and the design status were finalized afterward and received a static/privacy check.

## What remains

The original native attempt is still unresolved. Correcting the source does not finish its layout,
renew its one-shot approval or grant permission to change its history. Existing ordinary restore has
no interrupted-attempt disposition API. Its fence prevents replay but can block cooperating writers
on that compositor across state roots; private Store selection does not avoid that availability cost.

The next source-owner slice is a bounded design/review for explicit append-only disposition through
the existing CLI. It must retain historical uncertainty, distinguish operator-accepted partial results
from success, bind exact history/evidence and approval, and test crash/replay/cross-root behavior.
Do not borrow reconstruction's separate authority, delete a fence or reinterpret the failed width
intent as a successful observation. Any actual disposition or subsequent live action requires new
exact operator approval.

Browser/general-application ownership, automatic unknown-cwd handling and full login/session usability
remain separate coverage work. The historical successful reboot remains positive evidence for the
existing implementation; a candidate's narrower coverage does not erase it. Focus/action is still
non-atomic, and saved height is not restored. Green synthetic/source gates are not native proof.
