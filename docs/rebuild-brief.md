# Rebuild contract

Current release blocker: [R4-HELP-1 approval](r4-help-review.md). The owner has
authorized investigation of blank native Houdini help after Studio launch.
Keep PR #14 Draft; pause automatic Ready/merge/Public RC. Start with an audited
read-only inspection of the actual GUI help object and a same-installation
native/Studio comparison, with the owner's availability. Preserve the previous
invalid probes and all user environment/data boundaries. No speculative
environment rewrite, Qt replacement or unrelated feature work. The current
status and bounded evidence procedure are in [R4-HELP-1 validation](r4-help-validation.md).
The latest [environment-key review](r4-help-environment-case-review.md) supersedes
the private Qt PATH-removal experiment. The bounded candidate re-spells only
`Path`, `SystemRoot`, `SystemDrive` in the ordinary dict passed directly to the
final Houdini `Popen`; no value or directory changes. Thirty focused checks pass,
including real Windows serialization, both bootstraps and the final spawn.
The diagnostic reads those raw names with the read-only own-process Win32 API.
Real help recovery and actual payload GUI verification remain pending; the
observed `0xC0000135` does not identify a particular missing DLL.

**Owner artwork correction (2026-09-10):** The owner explicitly requested the supplied Downloads illustration as the static Launcher background, a youthful white/blue palette, readable translucent nodes and the girl portrait as the Studio.exe icon. This overrides earlier Launcher pink/dark and no-brand-art restrictions. Use redesign-existing-projects only to improve this approved presentation. Keep the five-node topology, Changa hero, Lucide functional icons, native Qt, Panel presentation and execution architecture. Resources are bundled under src/studio/ui/assets/launcher-artwork; no runtime download.


The [fixed node-flow Launcher approval](launcher-node-flow-brief.md) is the latest
Launcher-only scope: Account -> three scene-source branches -> Launch. Selection
is transient and cannot admit a workspace or start services; only the sink
enters the existing request/prepare/launch/query lifecycle. This replaces the
earlier staged Launcher UI, not its identity, uncertainty or process ownership
contracts. Panel and runtime architecture remain frozen.

The user's 2026-09-10 correction restores native Houdini user preferences for
normal Studio launches, including an existing `HOUDINI_USER_PREF_DIR` override.
Studio must not copy or rewrite preferences; project-local preferences remain
the explicit test default. The single `Studio.exe` entry applies to both source
and installed use. These user-authorized launch corrections require a new RC;
earlier isolation/frozen-candidate wording below is historical.

Current bounded follow-up: [RC trial scope and direct user correction](rc-trial-scope.md),
with the [full Pro audit](rc-trial-review.md). Shared Houdini trial policy and
read-only identity details require a new RC; `991cbce` stays preserved. Clash is
the external-network prerequisite with each user's own settings; no Clash-off
test or global network change is authorized. Existing execution/UI architecture
remains frozen; Owner trials and named-tester distribution can precede the still
required external standard-user acceptance and final Pro Go.

The [final release approval](final-release-brief.md) is the current stage entry.
It approves PANEL-STEER-1 for first release and fixes the order within PR #14:
R4-NET-1 correction, pinned native steer, final package and standard-user installed
acceptance, then merge/release the same accepted installer bytes. Earlier record-only
or deferred-steer wording below is historical. Preserve the three explicit gates;
Dynamic Artwork stays post-release and no other feature/benchmark gate is added.

The [Release Readiness approval](release-readiness-brief.md) established the prior
stages. It permitted PR #10's technical merge (completed at `890284b`) while
retaining all frozen [model results](model-acceptance-results.md). R1 merged as PR
#11 at `fe57c7a`; its native-message/history fixes passed the [real Panel gate](r1-validation.md).
[R2](r2-validation.md), merged as PR #12 at `2b180da`, simplifies scene instructions,
gives field-level schema errors and removes measured request-local metadata/result
overhead. It preserves general HOM, optional verification and durable step gates.
These limited corrections supersede the earlier record-only/UI-freeze statements
below; they describe prior scope. [R3](r3-validation.md), merged as PR #13 at
`b48ceae`, covers approved native conversation/activity/progress presentation and
its real-host checks. R4 has integrated R3 and remains draft PR #14; see
[the package preparation record](r4-validation.md). The user currently lacks a clean Windows 11 non-administrator
test environment and asked to complete other preparation. That environment and
the full installed-package authoring flow remain mandatory release gates.
The integrated package reproduced [R4-NET-1](acceptance-issues.md), an
intermittent native reply failure that prevented reliable history display.
The local HTTP correction at `a5731cf` passed the [NET-1 gate](r4-net-validation.md)
in two fresh actual-package Houdini processes. Earlier R1/R3 checks and the old
failed package remain historical. Native steer and the final-package regression
now pass in [frozen candidate `991cbce`](r4-final-candidate.md); only the actual
standard-user installed workflow remains untested. Preserve the candidate bytes
and keep PR #14 Draft while that environment is unavailable.
No new tool capability, second chat store or rendering expansion is approved.

The independent [native conversation lifecycle approval](native-conversations-brief.md)
adds native title search/pagination, rename/archive/restore/delete and a compact
Panel menu entry. Keep native history, workspace scope, draft ownership, explicit
deletion confirmation and receipt-based safety. [PANEL-1](acceptance-issues.md)
remains record-only. This approval does not expand the scene execution kernel.

Product: **Big-Chicken Houdini Studio**. New folder and new Git history; original HIA stays intact.
Source diagnosis: [the user's complete Pro diagnosis](pro-diagnosis.md). Do not lose its execution semantics while redesigning the UI.
The [authoring review](authoring-review.md) established the execution and input foundation. PR #5 implemented native ChatGPT onboarding, HIP targets, native model/effort settings and the required storage/output boundaries, and merged at `1e9f0f4`. The [approved presentation specification](ui-presentation-brief.md) remains the visual boundary; its acceptance is recorded in [authoring results](authoring-results.md).

The [latest TC-3 decision](tc3-brief.md) authorizes bounded staged HOM authoring on `codex/staged-authoring` from TC-2 merge `1734b08`. Use one operation/queue entry with separately dispatched main-thread steps, durable start/result records, bounded JSON handoff and explicit failed gates/Stop/context-change boundaries. Reuse TC-1/TC-2 instead of expanding lookup or capture. Rendering expansion is withdrawn. Scoped-consent usability and native conversation lifecycle are separate small PRs. [PANEL-1](acceptance-issues.md) remains a user-reported issue for Pro review, not an authorized repair. Existing frozen [TC1-A1/TC2-A1](deferred-acceptance.md) remain independent and pending; real GUI reliability checks cannot be replaced with model or CI claims. Thread requirements remain deferred.

The approved Lucide Outline 0.468.0 subset is the only product icon source. Keep its original geometry and license notices; no graphic logo, QStyle product icons, emoji or substitute artwork. Use text for unapproved uses and missing resources. The specification fixes page actions, component layout and visual roles; do not invent alternatives or restore a legacy-context/profile-switching UI. Existing data remains preserved in place. Targeted viewport capture is limited to the TC-2 brief; no render scheduling, new MCP tools or simulation framework.

## Required outcomes

1. Runtime alone owns scene identity, a bounded main-thread queue and durable operation receipts. HIP load/clear advances scene_epoch; check it inside the same main-thread callback that executes HOM. Query by operation_id never runs a script. Payload identity guards different scripts sharing one ID. Crashes between side effect and commit remain explicitly unknown.
2. Ordinary edits take one meaningful batch with optional targeted observations/checks. No default full snapshots, mandatory knowledge search, repeated validations or automatic capture. Keep general HOM and installed metadata; do not invent a node allowlist or Python sandbox.
3. Optional knowledge cannot block launcher, bridge or memory. FTS is opt-in, memory is workspace-scoped and explicitly written. No embedding installer or importer in the launch path.
4. Native Launcher stages: Checking, Setup, Authentication, Home and Launching/Attention. Each page has stable actions; Home directly opens HIP/Empty through one activation guard. Potentially active launches retain priority until authoritative state resolves them. Panel: compact scene/conversation header, a single Composer with visible model/effort popup, local per-thread documents, safe result images and a fixed Send/Stop position. Keep Codex stopping and running/unknown Houdini facts distinct, with raw technical information in details.
5. Preserve Codex App Server, native Thread/Turn persistence, native MCP images, loopback authentication and user work. Separate installation resources, persistent user state and disposable cache, with containment per root and checkout-local development fixtures. No auto recovery/reload, no second reasoning service, no legacy B2/FX startup contracts.

## Current implementation map

- `common.py`, `workspace.py`: app storage and workspace identity, explicit memory/FTS.
- `ledger.py`, `runtime.py`, `scene.py`, `runtime_server.py`: authoritative receipts and native HOM execution.
- `mcp.py`: seven small decision tools; observation binding and result re-query.
- `bridge.py`, `codex/`: native Codex integration and event projection. Stdio client/redaction reused from old HIA at 6d9a2d7b606d699fc85bf13586d31aa27455a63b; integration policy is new.
- `launcher.py`: launch controller; `houdini/`: project-local package and runtime hooks.
- `ui/shared.py`, `ui/theme.py`, `ui/icons.py`, `ui/launcher.py`, `ui/panel.py`, `ui/conversation.py`, `ui/requests.py`: scoped Qt presentation, approved SVG resources, native conversation projection, explicit requests and runtime receipts.

## Integration/API contract for the Panel

Use authenticated asynchronous calls through `ui.shared.Api`. NET-1's local correction performs HTTP IO in Python tasks because the actual Houdini QNetworkReply binding returned aliased objects; Qt receives copied Python results after IO cleanup. See `docs/r4-net-validation.md`. Bridge URL is in `sessions/<BCS_SESSION_ID>/bridge.json` beneath the selected persistent data root; token is only in BCS_SESSION_TOKEN environment. Do not block Qt's main thread or replay requests after ambiguous completion.

GET `/state`: workspace, thread_id, turn_id, codex {state, alive, stop_requested}, runtime {connection, scene, main_thread_busy, active_operation_id, queue_depth}, pending_requests, thread_settings, turn_settings, account_revision and scene_context. File state follows confirmed HIP events; Save As preserves execution identity.
GET `/events?after=N`: native Codex projections, monotonic sequence, cursor, resync_required. No separate durable chat history. GET `/thread` rehydrates native thread history.
Before a new native thread has a rollout, `/thread` can return `history_available: false` with native metadata. Preserve existing rendered items; this is not evidence of empty history.
POST `/threads/select` {thread_id?}; GET `/threads`; POST `/turn` {text, attachments: [attachment_id], model?, effort?, expected_thread_id?, settings_revision?}; POST `/stop` {}. The Panel binds submitted settings to the selected native thread revision; requested and natively rerouted current-turn models stay separate from the next-turn choice.
POST `/reconcile` reads native state without inferring Houdini outcomes. POST `/selection` submits one queued context read, returning nodes and epoch or an operation ID to query. This Panel read does not bind the MCP adapter's observation.
The final steering approval adds independent POST `/turn/steer` with the clicked
Thread/Turn, current native connection generation and an immutable client message ID.
The Composer supplies exact identity for both `/turn` and `/turn/steer`; new starts
also bind the clicked `turn_revision`. One unresolved input blocks another send,
without a per-Turn quota or fallback start. `/state` projects input acceptance
separately from native Turn liveness. `/reconcile` may take the original client ID;
recovery verifies the original account before exposing its bounded workspace
snapshot, even when no Thread is selected. ACK never revives a stopped/completed
Turn, clears later drafts or changes accepted HOM/staged work. See
[steering validation](r4-steer-validation.md) for the fixed-version contract and gates.
GET `/operations`; GET `/operations/<id>`; GET `/operations/<id>/detail?offset=N`; POST `/operations/<id>/cancel` {}.
POST `/attachments` {path}: explicitly selected image copied into workspace, returns attachment_id, name, path.
GET `/models` aggregates native pagination and preserves native capability metadata; GET `/account`; POST `/account/login` {}, `/account/login/cancel` {}, `/account/logout` {}. Authentication URLs belong only to an explicit browser action, never diagnostics. Launcher onboarding has its own short-lived client using the production executable and native CODEX_HOME; it closes before launching the production supervisor.
POST `/requests/respond` {request_id, result}: preserve native approval/input response schema. Never automatically approve.
POST `/memory` {action: list|record|supersede|delete, body?, record_id?}. No auto memory.

## Coordination and validation

Keep changes on short-lived branches and group commits by behavior. Preserve published main history. Report actual validation and commit only owned files.
Keep test effort proportional: targeted faults (stale scene after queue, duplicate ID, response loss, oversized result, Stop while running, external effect then exception) and native UI screenshots. Do not repeatedly run full suites or perform gratuitous hash audits.
Project worktrees use `model_context_window = 400000` and `model_auto_compact_token_limit = 350000`. Bridge forwards these two project settings into native scene threads. These are configured limits, not a measurement of an already running task's effective context.

The first real Houdini node workflow and native Codex Box task are recorded in [stage readiness results](stage-readiness-results.md). Broader scene, capture, render and interruption behavior remains unverified. Fakes, generated schemas and offscreen screenshots do not extend that evidence.
