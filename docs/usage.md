---
summary: "CLI usage, privacy and experimental layout-action safety."
read_when:
  - "You capture a desktop or consider approving a layout change."
---

# Usage and safety

## Read-only commands

`capture` observes Niri outputs, workspaces, windows and layer surfaces, plus same-user process
identity metadata. It samples twice and rejects coherence if topology, focus, active workspace,
layer list or window-host process identity changes. The `capture` command then reads again after
1 s, or after 10 s when a Niri query failed or timed out, up to three readings in all. It saves the
first coherent reading, else the last one that succeeded, and fails only when every reading failed;
its output reports `samples` when it read more than once. Exact-output consumers must allow that
conditional field; retries can also change the saved content, timestamps and digest. Incoherence can result from
changes or process-probe warnings; it does not establish that a focus switch caused an incident.
This is bounded observation, not an atomic snapshot across processes. It never reads terminal
contents or browser profiles, and never executes a discovered application binary. Session identity comes from Claude Code's per-PID
registry, Pi's presence files and nodecode's shell records; a Claude transcript is scanned only for its title records, to
match sessions to windows. Niri IPC is the only invoked runtime CLI.

`capture --include-titles` stores private window labels and session titles. Default labels
identify applications and window IDs only, and reopen recipes carry no session title. Other
process metadata, including recipe command lines, can still be sensitive. Keep captures private.

### Save selected windows

`capture --window-id INT [--window-id INT ...]` saves exactly the named windows from that
same capture. IDs must be nonnegative integers, unique and present in that observation; invalid,
duplicate or absent selections fail before any snapshot or pointer is written. IDs are local to
that compositor observation, not persistent application identities. No app/title guessing occurs.
Without the flag, full-capture snapshot and result semantics are unchanged.

Selection preserves source window order, complete selected recipes (including `reopen.extra`),
and **all** supporting outputs, workspaces, layers, identities, process observations, inventory,
warnings and capture timestamps. Readiness is recomputed for the saved windows; source coherence
is retained. Selected snapshots and capture results add exactly this metadata object:
`"capture_selection": {"kind": "window-ids", "window_ids": [30], "observed_window_count": 3}`
(fabricated IDs/count). IDs in this field are sorted; window records remain in source order.
The immutable snapshot digest binds this provenance and the saved content. It does not reference
an unsaved full snapshot or claim complete desktop coverage. Even selecting every observed ID
explicitly retains this provenance. The ordinary model, Store and restore planner consume it;
full-desktop `verify` still compares all windows and can report unselected live windows as extras.

**Selection is not selective probing.** Capture still reads whole-desktop/process/session metadata,
including potential Claude transcript-title reads before redaction. Unselected process metadata
remains in the saved snapshot. `--include-titles` controls retention, not those reads. Selection is
neither a privacy sandbox nor resource/lock isolation.

These are ordinary Store snapshots: they promote `latest-observed` and, when ready,
`last-display-valid`. Default preview/restore in that Store will therefore use the selected snapshot.
Use an explicitly reviewed private Store for qualification, not the login capture Store; never
hand-edit generated snapshots or receipts. A different `--state-root` does **not** bypass the
canonical compositor fence on apply or resolve an earlier ambiguous attempt.

One selected window may carry extra-tab recipes and produce multiple planned entries. Before any
one-window canary, review the exact saved recipes and immutable dry-run receipt: require **exactly
one planned entry, no extras**, a harmless admitted Ghostty recipe and the intended destination.
Dry-run records placement only; it does not certify admission, executable availability or safety.
Do not drop extras to manufacture a one-launch plan. The proposed sequence, not permission to run it:

1. With separately authorized whole-desktop read access, use the existing candidate CLI:
   `niri-desktop-continuity --state-root <private-store> capture --window-id <observed-id>`.
2. Retain its exact `snapshot_digest`; run
   `niri-desktop-continuity --state-root <same-store> restore <snapshot-digest>` without `--apply`.
   Review the returned `receipt_digest` and immutable `receipts/<receipt-digest>.json`, the saved
   recipe (including extras), protected baseline, compacted workspace/name intent and host admission.
3. Stop for separate explicit operator approval of any effectful canary. Neither capture nor dry-run
   grants it. No canary, native qualification, login deployment or retry is authorized here.

### Preview and verification

`preview [digest]` renders a stored snapshot offline (default: the latest capture); `--kind receipts`
renders the result page of a `restore --apply` run (see [Save and reopen](#save-and-reopen)); `--kind plans`
renders current and desired maps plus admission blockers and always needs a digest. A snapshot
preview labels every tile with how it reopens and adds an **After a reboot** ledger: per window
(and per extra tab session) whether `restore --apply` would reopen it, its kind, exact command and
directory, or the reason it will not. Recipes are shown as recorded, not re-verified. HTML and SVG escape all observed strings and contain no scripts,
network assets or working approval buttons. Preview has no application-control backend.

`verify <desired-snapshot-digest>` compares against a fresh live observation. Exit 0 means its
observable layout predicates match. Exit 2 means mismatch, unavailable output, invalid identity
or another refusal. Focus is reported separately. Native application state stays unverified.
`history --kind snapshots|plans|receipts --limit 20` lists artifact identities, not private labels.

## Save and reopen

`capture` attaches a reopen recipe to every window (`reopen`): kind `app` (process argv and cwd),
`claude` (`claude --resume <id>` inside the same terminal, from `~/.claude/sessions/<pid>.json`),
`pi` (the presence file's `resumeArgv`, written by the `session-presence` extension of
`@tryinget/pi-little-helpers`), `command` (the job in the tab's foreground, as it
was started: `just dev`, `bash start.sh`; a helper it detached or a background job is ignored),
`shell` (terminal in the same directory) or `unknown` with a reason. Only Ghostty is read as a terminal:
the terminal recipes use its `--working-directory` and `-e`, so other terminals are recorded as
`app` (their own command line, nothing that ran inside). Titles are used only to match a
session to its window when one terminal process owns several windows; they, and the session
titles used for matching, are not stored unless `--include-titles` is given. Sessions found in extra tabs of a window become `extra` recipes.

`restore [digest]` prints the plan: every saved window with its group, route (`terminal`,
`desktop:<entry>`, `argv` or `user`), exact launch command and status (`planned`, `already-open`,
`already-running`, `not-reopened` with a reason). `--apply` carries it out:

1. One lock per compositor serializes continuity writers. A record left by the earlier strict
   engine, for the running compositor or for the one the source came from, refuses `--apply` until
   that compositor restarts. No released version wrote such records.
2. Groups launch one after another. An app group is every saved window of one process; it is spawned
   **once** through Niri. New windows whose app ID equals the group's are adopted, in arrival order,
   into the saved places, until the saved number arrived, none arrived for 5 s, or `--spawn-timeout`
   (default 25 s) passed. Windows of other apps are never adopted. Fewer windows leave the remaining
   places `not-detected`; there is no second launch. Extra windows stay where the app put them and
   cannot be taken by a later group.
3. An app with any window already open is not launched and its windows are not touched
   (`already-running`). A Claude, Pi or declared session whose resume command is already open is
   `already-open`.
4. Each saved Ghostty window is its own launch: `--gtk-single-instance=false`, the saved directory and
   `-e` command, with your normal configuration (`--config-default-files=false` from earlier controlled
   restores is dropped).
5. Adopted windows move to their saved workspace (saved workspaces compact to consecutive indices;
   windows without a known place go to one new last workspace), then columns are rebuilt after the
   windows that were already open, with saved widths, stacked tiles and floating positions. Workspace
   names are restored, and focus returns to the window that had it.

Niri launches nothing while the session is locked, so `--apply` refuses a locked session (logind
`LockedHint`) before launching anything, and `--at-login` waits up to 10 minutes for the unlock. If the
lock state cannot be read, the session counts as unlocked.

A run that reaches the reopen engine writes one receipt (`reopened`, `reopened-partially`,
`interrupted` or `dry-run`); an early refusal or a same-instance skip writes none. Exit 2 means some
window did not come back, or the run was refused or interrupted. `last-reopened` points at the last
snapshot reopened fully or partially. Each `--apply` receipt also gets an offline result page,
`previews/<receipt-digest>.html`, returned as `report` in the output (`report_error` if it could
not be written; the run's result and receipt are unchanged). It marks each saved window and tab
session `BACK as window <id>`, `ALREADY OPEN` (its session's resume command was open),
`APP ALREADY RUNNING` (the app had a window, so none of its saved windows was launched) or
`NOT BACK (<reason>)` and lists the misses with a
plain-language reason. As the run's last step, after the layout and focus are restored, it asks Niri
to open the page with `xdg-open` (`report_open: requested`); `--no-open` skips that
(`report_open: skipped`), and a missing `xdg-open` or failed spawn becomes `report_open_error`
without changing the run's result. `preview --kind receipts [digest]` writes that page again for a stored
`--apply` receipt, by default the newest; a dry-run receipt is refused.
Reopening is not recovered memory: applications restore their own content. **Stay idle** while it
arranges columns; niri has no atomic focus-and-move.

### Default restore snapshot selection

Manual and login restore without a digest prefer a readiness-valid `latest-observed` snapshot. If
that coherent observation has no usable output, no active workspace, or windows on unavailable
workspaces, they select the preserved `last-display-valid` snapshot, checking its readiness again. A
genuinely absent latest pointer also permits this fallback. The incoherent fallback requires
`coherent: false` explicitly on the latest observation; missing or nonboolean coherence refuses.
Both identities must contain nonblank, NUL-free strings for `boot_id` and `niri_socket`, and actual
nonnegative integers for `socket_inode` and `socket_device` (not booleans or floats). Complete
identities, including any extra metadata, must match exactly without numeric type coercion or
path normalization. No historical socket is reopened or checked on disk. Otherwise restore
refuses, so a desktop of an earlier session never stands in for a later one. Corrupt pointers,
missing artifacts, invalid digests, unsafe private files and unsupported schemas fail closed and never trigger another selection. An
explicit `restore <digest>` never falls back. On fallback, both manual and login restore skip when
either the latest observation or the selected snapshot belongs to the running compositor, so
turning off a display never reopens an old desktop; the CLI then prints one JSON line on stderr with
`source_pointer`, `snapshot_digest` and `fallback_reason` (`latest-display-unavailable`,
`latest-incoherent` or `latest-pointer-missing`).

### Routes: where an app is launched from

1. A user route in `$XDG_CONFIG_HOME/niri-desktop-continuity/routes.json` (your own file, not
   writable by others): `{"routes": {APP_ID: {"desktop": "x.desktop"} | {"argv": [...], "cwd": "/dir"}}}`.
2. The desktop entry (XDG data directories, yours first) whose file name or `StartupWMClass` equals the
   app ID, case-insensitive, or whose `Exec` program is the captured executable. `Exec` is parsed by
   the Desktop Entry Specification's quoting rules; field codes such as `%U` are dropped, so no file or
   URL is passed. Hidden, `Terminal=true` and failing `TryExec` entries are skipped.
3. The captured command line, without operands that contain `://` (sign-in links, deep links).

Rule 2 applies only when the snapshot has a single instance of that app. Two instances (two browser
profiles, two processes of one app) each keep their own command line, launched one after another.

### Agent sessions

An agent process (`claude`, `codex`, `pi`, `angel`/`angelx`, `aider`, `gemini`, `opencode`, `goose`,
`crush`, `qwen`, `grok`, `cursor-agent`) is never relaunched from its command line. It comes back
from Claude Code's session registry, Pi's presence file, a `declare`, or a session it announced.
A terminal other than Ghostty (kitty, foot, Alacritty, WezTerm, Konsole and others) reopens from
its own command line; when any word of that line, including the text of an `sh -c` argument,
names such an agent, the window is refused as `agent-in-other-terminal` instead. A word that only
looks like an agent's name, such as a title, refuses too: refusing is the safe mistake.

An agent announces its session through its `SessionStart` hook:

```sh
# an agent's SessionStart hook; reads {"session_id": ..., "cwd": ...} on stdin
niri-desktop-continuity hook claude                         # claude --resume {id}
niri-desktop-continuity hook codex                          # codex resume {id}
niri-desktop-continuity hook myagent -- myagent --resume {id}
```

`hook` finds the nearest ancestor process with the agent's name and declares the resume command for
it, pinned to that process's start time (a reused PID never matches). A later `SessionStart` (a new
session or thread switch) replaces the declaration. The program is resolved to an absolute path,
because Niri's `PATH` can differ from the agent's. `hook` prints nothing on stdout (agents feed a
`SessionStart` hook's stdout into their context) and exits 0 or 1, never 2. If the agent is not inside
a terminal, nothing is declared and one line on stderr says so. Without an announced session, the tab
is reported `agent-session-unannounced` (Claude: `claude-session-unregistered`); an agent running in
its own window is refused the same way rather than relaunched with its opening prompt.

Where the hook line goes:

- **Claude Code:** `~/.claude/settings.json`, under `hooks.SessionStart`. Claude's own session
  registry already covers most sessions; the hook also covers sessions without a registry entry.
- **Codex:** `~/.codex/hooks.json`, same nested shape, under `SessionStart` (feature `hooks`). Codex
  skips a new hook until you trust it once with `/hooks`. By default Codex runs sessions in a shared
  app-server daemon outside the terminal; such sessions cannot be tied to a tab, so start Codex with
  `--no-daemon` where a tab should come back.
- **angelX:** releases before [angelX#22](https://github.com/newjordan/angelX/pull/22) (merged
  2 November 2026) have tool hooks only (`PreToolUse`/`PostToolUse`, no session ID) and cannot
  announce a session; their tabs are refused, never replayed. #22 adds a `SessionStart` hook in
  `~/.angelX/hooks.json`; `hook angelx` (resume command `angelx --resume {id}`) is meant for it but
  is untested with it. `declare` on its PID works either way.

A nodecode shell is not an agent in this sense (it takes no opening prompt). When its record in
`$XDG_RUNTIME_DIR/nodecode/shells/<pid>.json` (version 1, written by nodecode itself) names this
exact process (pid and start time), the tab reopens with the recorded `resume_argv`, which must
name the recorded session, in the recorded directory. Otherwise the tab reopens as its shell in the
same profile, as before.

### Restore read-query policy

Windows, Workspaces and Version reads retry only `Popen` construction raising exact
`BlockingIOError` with `EAGAIN`: at most three constructions per read, with 0.05/0.10-second
backoffs. Communication, decoding, spawn and layout actions are never retried, and IPC clients are
never timeout-killed or implicitly cleaned up. Each read has one ten-second budget that construction,
backoff and decoding all count against. This rejects late observations; it is not a hard wall-clock
return bound. Exhaustion leaves the original error, not a new launch or permission to retry effects.

### At login, autostart and what is never replayed

`restore --at-login` first waits up to 60 s for Niri and does nothing when the saved identity
matches the running compositor instance. `autostart --enable [--interval-minutes N]
[--keep-days N]` installs `niri-desktop-continuity-capture.timer` and
`niri-desktop-continuity-restore.service` (wanted by `graphical-session.target`); `autostart
--disable` removes them; `autostart` alone reports status. `capture --keep-days N` then deletes
snapshots saved before the N most recent days that have captures (a day without captures does not
count). A snapshot that a pointer, receipt, plan, approval, preview, recovery marker or the restore
history names is always kept; without the option nothing is deleted.
Recipes are launch commands, not process memory: unsaved drafts, scrollback and hidden tab order
are not recovered, and applications restore their own content.

What is never replayed: a Claude process without a registry entry (for example one started from
inside another Claude session, which inherits its child-session environment and keeps no
transcript) is `unknown` (`claude-session-unregistered`); its command line is often an opening
prompt, and running it again would start the same work over. A window reported by the X11 bridge
`xwayland-satellite` is `unknown` (`xwayland-client`). An AppImage program running from its
temporary `.mount_*` directory is recorded as the AppImage file that serves the mount (the
runtime's own launch path when absolute), or `unknown` (`appimage-mount-unresolved`).
Chromium and Electron overwrite their command line with one space-joined process title. It is
split where a leading part names a real program file (arguments that contained spaces cannot be
recovered; the preview marks such commands), otherwise `unknown` (`process-title-unresolved`).

`declare --pid PID [--cwd DIR] [--label TEXT] -- COMMAND [ARG...]` tells the next captures how to
reopen the terminal surface that runs PID when nothing can resume it, e.g. a fresh session started
from a handoff: `declare --pid 4242 -- claude "Continue from docs/handoff.md"`. The declaration
lives in the per-boot runtime directory (`/run/user/<uid>/niri-desktop-continuity-declared`, 0600),
is pinned to the process start time so a reused pid never matches, applies only when no native
Claude or Pi session is found, and becomes kind `declared`. `declare --pid PID --clear` removes it.

## Planning

`plan <snapshot-digest>` defaults to review-only inspection. Optional `--window-id`, `--pid`,
`--app-id` and `--version` filters intersect. Unknown or conflicting selectors fail closed.
`--intent restart|migrate` always yields a blocked proposal. `--replacement` hashes an exact
executable but does not run it. Observed descendant/cgroup impact is not a promise of exhaustive
kill scope or process recoverability. Plans expire after 300 seconds by default (`--ttl 1..900`).
Historical previews remain readable after expiry; their presence is not renewed authority.

## Experimental layout-only actions

**Not a frozen-terminal recovery procedure. Not proven by a read-only map.** The first effect
model supports only same-workspace single-tile column reorder on one output, preserving the
focus at admission. It does not restore historical focus from a different checkpoint.

```sh
niri-desktop-continuity plan <current-snapshot> --intent reconcile --desired <desired-snapshot>
niri-desktop-continuity preview <plan-digest> --kind plans
# Only after the operator reviews the exact plan and agrees to the limitations:
niri-desktop-continuity approve <plan-digest> --confirm <same-full-plan-digest>
niri-desktop-continuity reconcile <approval-digest> --apply --acknowledge-non-atomic-focus
```

The operator must remain idle during the operation. Niri has no atomic focus-plus-move/CAS
transaction: external input in the final IPC gap can move an unintended column. This is a real
residual risk, not eliminated by the acknowledgment flag. Unsupported topology is blocked before
any action. An already-matching plan performs no IPC effects.

All cooperating tool instances share an exclusive nonblocking lock under `/run/user/<uid>`,
keyed by boot and compositor socket device/inode, independent of `--state-root`. This does not
lock out other Niri clients or the user. Validation occurs inside the lock, approval is consumed
once, expiry is checked before each dispatch, and each effect intent is durably recorded first.
A no-effect acknowledgment is not success. Observed drift or a timeout stops without replay or
rollback. A crash may leave only an effect-indeterminate intent and consumed marker. Re-observe
and make a new decision; never delete the marker to replay an unknown operation.

No live mutation canary is implied by the synthetic test suite. The public tool makes no claim
of tested cross-version app restart, guaranteed focus safety, or restoration on another machine.

## Loss-bounded reconstruction (separate from exact restart)

The existing CLI implements orchestration for `saved-conversations-v1` over exact protocol v1/v2; **no real machine adapter
ships with this package and no live reconstruction is certified by its tests**. The machine owner
must first establish and independently review a pinned profile/internal endpoint according to the
[protocol](project/2026-09-06-integrated-reconstruction-protocol.md). An absent profile reports
`reconstruction-adapter-unavailable`; an absent explicit config reports
`reconstruction-adapter-config-required`. Other untrusted adapter/config/protocol diagnostics are
suppressed in favor of a static refusal. No shell/argv, native payload or environment is exported.

```sh
niri-desktop-continuity plan <snapshot> --intent reconstruct --adapter-config <private-config>
niri-desktop-continuity preview <plan> --kind plans
# Only after reviewing the exact plan and accepting the named losses:
niri-desktop-continuity approve <plan> --confirm <plan> --accept-losses saved-conversations-v1
niri-desktop-continuity reconstruct <approval> --apply --acknowledge-non-atomic-focus
# The returned attempt_digest is the approval digest, not the receipt digest:
niri-desktop-continuity inspect <attempt> --kind reconstruction
niri-desktop-continuity verify <attempt> --kind reconstruction
```

These commands describe the interface, **not permission to run a live operation**. Plan and approve
perform fresh read-only observations. Capture/preview remain inert with respect to adapter effects.
The preview's desired map is explicitly the original target topology; replacement window identities,
native surfaces and recovery groups are not predicted by this renderer. Its admission warnings show
sanitized native coverage, losses and any required omission digests. Read the typed plan/proof rather
than interpreting the schematic as native recovery evidence.

Memory, drafts, scrollback, shell state and hidden-tab order are unsupported losses. Unknown ownership,
unknown native process identity or controller/protected overlap always blocks. The only image
unobservability exception is the separately typed v2 btop utility below. An otherwise fully
identified owned process without a native session association also blocks by default. If the operator
separately chooses to omit **only that exact association**, make a fresh proposal with
`plan ... --omit-association <process-pin-digest>` (candidate digests are returned by planning), then
repeat each with `approve ... --accept-omission <same-process-pin-digest>` in addition to the exact
plan and baseline loss contract. No specific omission has been accepted by this documentation.
Boot/birth/image drift invalidates the typed decision; generic loss acceptance never substitutes.

### Conversation/tool coverage and evidence limits

Pi, Claude and Codex saved conversations use the **same existing CLI and opaque `session_refs`**;
btop is a separate v2 utility, never a conversation. No public v3, app-name field, second CLI,
machine import or new runtime dependency is needed. The separately owned private `machine.v3`
implementation uses unchanged public v1/v2. Interface capacity alone is not native compatibility.

| Surface | Current evidence / status | Not established |
|---|---|---|
| Generic public v1/v2 contract | Fabricated three-reference workflows; distinct refs stay distinct, same-ref processes deduplicate, consistent renaming preserves results; every native predicate and malformed/missing proof tested; installed CLI/socket subprocess smoke | Which tool produced a ref, app-kind namespacing, native identity semantics or live recovery |
| Pi machine integration | Separately owned implementation/review and isolated installed-CLI tests; owner-reported real Pi resume with fabricated sessions in a filesystem/network sandbox | Ghostty/service/provider/live layout proof or production qualification |
| btop machine integration | Separately owned observed-image/capability-limit implementation and isolated machine-boundary tests | Native btop/Ghostty reconstruction or live effects |
| Claude + Codex machine integration | **Implemented and independently reviewed with isolated integration tests; native desktop qualification unperformed**. App-kind-scoped equal-ID separation, same-kind deduplication and actual native-shape callback/log fixtures verified | Permanent real-native opt-in tests, clean Claude compatibility, full native/runtime certification or production qualification |

The machine implementation's isolated tests verify tool-kind-scoped identities, same-app
deduplication and distinct-app separation, including equal native IDs across apps. Independent
file/cwd/runtime/bootstrap/surface/causal-window evidence remains mandatory for each admitted ref.
Public tests deliberately do not implement or certify that producer mapping. They cannot infer
semantic conversation identity, completeness or provider usability from a digest or six booleans.
Unknown or unproved helpers remain blockers. No native/full-coverage or live-effect approval follows.

### Recorded validation and qualification limits

The following supplied review/validation results are separate evidence sets, not additive totals:

- Independent public review accepted the bounded fixture/documentation slice: 161 tests, including
  70 new cases, and eight installed-console smoke cases. The parent actual checkout subsequently
  passed `UV_OFFLINE=1 just ci`: 343 tests, a new build and installed-console smoke.
- Independent machine final review accepted six native fixes after 187 application tests and eight
  independent cases. Recorded machine source/full validation passed 686 tests with five native Pi
  skips. The later combined parent run was still running at this documentation update; no newer
  total or completion is claimed.
- Real Claude/Codex sandbox prototypes supplied genuine callback, file-descriptor and initialization
  evidence. The Claude prototype could not exit cleanly because of a faulty harness; one isolated
  sandbox remains held pending operator cleanup approval. No cleanup is authorized here, and this
  is not clean Claude compatibility evidence. No permanent real Claude/Codex native opt-in tests
  were delivered.

No production profile, global installation, live Ghostty/service/layout qualification or full
native/runtime certification is established. The public package ships no machine adapter. These
results do not validate this final documentation edit; build/strict-docs validation remains with
the parent. Checkout-only chronology: `diary/2026-09-07--implementation-multitool-recovery.md`
(deliberately excluded from the sdist; not a shipped evidence dependency).

### V2 btop utilities and trusted application platform

A v2 owner profile explicitly declares an installed owner-trusted application platform and critical
file pins. The Python recovery-control implementation stays closed/source checked; exhaustive
OS/ELF/Pi/Jiti dependency closure is not required. This is neither a sandbox nor native proof.

V2 plans separately list btop utilities and `owned_utilities` / `image_unobservable_utilities`
coverage. An ordinary observed image requires a real running-process Pin. A capability-btop identity
must explicitly use a null image Pin, retained installed-file/capabilities/birth/parent/argv/cgroup
corroboration and a sole owned leaf; unknown ownership or overlap still blocks. It is not a Pi
session and must never be represented by a fabricated conversation or association omission.

For each capability-btop utility_ref shown by the plan warning, approval additionally requires
`--accept-utility-limit <utility_ref>`. Repeat this flag for each exact limit. Missing, duplicate,
extra or wrong-branch limits refuse. Baseline losses and any native omissions must also be accepted
separately. No specific limit is accepted by these instructions.

All utility proof predicates remain mandatory. Limits cap success at
`verified-with-accepted-limitations`, even when native omissions also exist. Receipts retain both
decisions, expose `overall_image_coverage_complete=false` and `image_coverage=observable-subset-only`,
and never claim complete overall native coverage. Image dimensions cover only observable images.
A utility-only selection can succeed with `saved_conversations_recovered=0`; it does not recover
a conversation. Interrupted history cannot be upgraded by fresh proof. Synthetic v1/v2 installed
console workflows are tested; separately owned machine integration has isolated evidence as above,
not native btop/Ghostty reconstruction or live-effect proof.

### Canonical accounting and execution

Canonical attempts live in the fixed owner's ledger, not the chosen CLI state root. Approval is
consumed once with a durable canonical prepare/consume/ready fence. Copies, different state roots
and re-approval cannot bypass it. Partial/indeterminate canonical history and incomplete legacy
accounting block new reconstruction. Historical v1 evidence stays inspectable after an owner profile
upgrade, with its original schema/profile identity and adapter accounting unknown; this does not
authorize cross-profile execution or reconcile old accounting. Do not delete markers, change profiles/ledgers or invent a nonce
to retry. A crash after intent may leave stopped processes or unresolved children; no automatic
rollback, service repair, signal, launch fallback or cleanup is authorized.

The worker receives one expiring effect permit at a time and retains the writer lock if its parent
disconnects. It must cease new effects on disconnect/lease expiry; only already-dispatched observation
and durable recording remain permitted. The CLI never timeout-kills the worker and waits for exit,
so a defective worker can block rather than silently release exclusion. Launched applications must
not inherit the lock. The operator must remain idle; Niri focus-plus-move is still non-atomic.

Final receipts separately report native file/cwd/runtime/bootstrap/surface/causal ownership, new
images, old-tree exit, services, layout/focus, labels/holds and protected preservation. Complete
mandatory proof yields `verified`; accepted association omissions cap it at
`verified-with-accepted-omissions`, always with incomplete overall native coverage. Neither means
provider usability, semantic completeness, human acceptance or memory restoration. Partial or
indeterminate execution exits 2. Fresh verification never upgrades an interrupted effect history
or modifies its canonical terminal marker. In v2, `saved_conversations_recovered` is an aggregate
complete-proof/history count: a partial attempt reports zero even if other native records pass,
not a per-conversation salvage tally. Missing native records yield partial; missing utility records
violate the exact proof set and make execution indeterminate. Inspect reports history/accounting,
not fresh native proof.
Default `verify <snapshot>` and ordinary layout reconciliation retain their existing meaning.

## Additive saved-session reopening

Use this distinct mode when the selected saved conversations remain available but their old
windows/processes are gone. It does **not** restart Ghostty, reconstruct tabs, move existing windows,
or demand invented old-process, shutdown or service proofs. The public package ships no native
adapter; its fabricated tests are not live machine qualification.

```sh
niri-desktop-continuity plan <current-snapshot> --intent reconstruct --mode additive \
  --saved-set <owner-private-saved-set-digest> --adapter-config <private-config>
niri-desktop-continuity preview <plan> --kind plans
niri-desktop-continuity approve <plan> --confirm <plan> --accept-losses saved-conversations-v1
niri-desktop-continuity reconstruct <approval> --apply --acknowledge-non-atomic-focus
niri-desktop-continuity verify <attempt> --kind reconstruction
niri-desktop-continuity inspect <attempt> --kind reconstruction
```

The existing lifecycle uses the separately versioned `desktop-continuity.saved-reopen.v1` owner
profile. `--mode replacement` remains the default and preserves v1/v2 behavior. Additive mode requires
an exact saved-set digest, never arbitrary argv, transcript content or a native path. The owner
resolves that private immutable set and proves each exact saved file/ID/cwd, native runtime/bootstrap,
and current absence or existing native association (including recovered descendants). Live-window,
PID, app/version and association-omission selectors are not accepted in this mode. All currently
observed windows are protected; no former PID or window must be fabricated.

Planning reports selected, missing, already-present and unresolved saved-conversation counts.
The offline HTML preview includes a saved-scope ledger with the complete saved-set digest, each
exact opaque ref and its disposition/count. It distinguishes a missing-session plan from a zero-launch
already-present plan without exposing native paths or adapter-private manifests. The map remains a
schematic; the scope ledger, not inferred tabs or unchanged topology, identifies planned launches.
When a reviewed owner profile projects desired grouping, the same preview shows each proposed
shared-window group, exact member creation sequence and grouping provenance. Plan JSON, receipts
and inspect retain those closed projections. **Desired creation order is not captured native tab
order**, and shared-window recovery does not certify tab-versus-split structure. Older observations
without grouping remain explicitly ungrouped/unknown; no retrospective grouping is inferred.
Privacy-safe per-ref reason codes and a separate capacity diagnostic explain refusals when supplied;
no native paths, exception text or transcripts are displayed.

Unresolved refs block that exact selection rather than silently disappear or acquire loss approval.
A revised owner-selected subset requires a new saved-set digest, plan and exact approval; it cannot
bypass unresolved effects. At execution the coordinator permits each admitted missing ref once, then
one restoration of the admitted focus. Shutdown, service, layout, duplicate launch, already-present
launch and unbound refs are refused before a permit. An already-present-only set performs **zero
effects** but still consumes its approval and receives fresh native verification. No-op evidence does
not authorize replay.

`verified` requires all selected native identities, pinned images, focus and protected preservation.
For already-present refs the ownership/image proofs concern those current processes, not fictitious
new launches. `saved_conversations_restored` counts admitted missing refs only after complete proof
and intact history; partial/indeterminate history reports zero, not a per-ref salvage tally.
`saved_conversations_already_present` and `saved_conversations_unresolved` retain admission counts;
they are not fresh success claims if overall native verification fails. Layout is explicitly not
reconstructed: normal tiling insertion can change geometry, and uncertain former tabs remain an
owner-declared loss, not guessed tab targets. Memory, drafts, scrollback and provider usability stay
unsupported/unverified. Ordinary capture/preview never launches anything.

All exact profile/source pins, native identity checks, expiry, focus revalidation, per-compositor
writer exclusion, canonical prepare/consume/ready fencing and no-retry/no-cleanup rules remain.
A correlated pending-effect heartbeat can keep a cooperative long preflight alive without granting
another effect or extending the absolute plan expiry. The five-second liveness lease still expires
on missed/late replies; disconnect or expiry cancels new effects without killing applications.

**Failed does not mean nothing happened:** partial recovery can leave new windows open and focus
changed. Inspect the canonical attempt before any separately reviewed operator reconciliation.
Never delete receipts/the ledger, change state roots or retry to hide unresolved effects. Additive
inspect includes this guidance. There is no automatic repair or cleanup. This mode cannot regroup
already-open sessions across windows; do not close them merely to make them eligible for reopening.

The portable contract permits at most 256 selected refs and 255 missing refs (one effect slot is
reserved for focus). Private adapters may have smaller persistent-store capacities; exhaustion
requires owner-managed retention/disposition, not automatic pruning. The portable tool remains
Python 3.11+; a private adapter can require a different pinned interpreter and must disclose it.
This is a bounded source-owned recovery mode, not a general application launcher or a workaround
for the independent requirements of destructive reconstruction. Native qualification is separate.

## Privacy and trust model

Private files are content-addressed and integrity checked, with distinct latest-observed,
last-display-valid and last-layout-verified pointers. Headless observations cannot promote a
stronger pointer. Existing permissive/symlink state roots are refused, not silently repaired.
Same-user malicious code can author local plans and approvals; these are accidental-use safety
gates, not authentication against an attacker who already controls your user account.
