# Rebuild contract

Product: **Big-Chicken Houdini Studio**. New folder and new Git history; original HIA stays intact.
Source diagnosis: [the user's complete Pro diagnosis](pro-diagnosis.md). Do not lose its execution semantics while redesigning the UI.
The [authoring review](authoring-review.md) established the execution and input foundation. PR #5 implemented native ChatGPT onboarding, HIP targets, native model/effort settings and the required storage/output boundaries. The [approved presentation specification](ui-presentation-brief.md) now requires a staged Launcher and integrated Panel while freezing those backend contracts. Continue in PR #5; its real official-login and Houdini user-flow acceptance cannot be transferred to a later PR.

The [latest closure decision](pr5-closure-brief.md) freezes further PR #5 features and UI redesign. Finish one compact ordinary-user workflow and fix only defects it exposes. Cross-monitor DPI is recorded separately; lack of a full matrix alone does not block merging. After #5 merges, the sole next direction is maintainable procedural editing in an existing HIP, with bounded improvements to the existing lookup. Do not start that implementation on the UI branch.

The approved Lucide Outline 0.468.0 subset is the only product icon source. Keep its original geometry and license notices; no graphic logo, QStyle product icons, emoji or substitute artwork. Use text for unapproved uses and missing resources. The specification fixes page actions, component layout and visual roles; do not invent alternatives or restore a legacy-context/profile-switching UI. Existing data remains preserved in place. No new rendering capabilities, MCP tools or Houdini animation/simulation features.

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

Use authenticated Qt network calls through `ui.shared.Api`. Bridge URL is in `sessions/<BCS_SESSION_ID>/bridge.json` beneath the selected persistent data root; token is only in BCS_SESSION_TOKEN environment. Do not block Qt's main thread.

GET `/state`: workspace, thread_id, turn_id, codex {state, alive, stop_requested}, runtime {connection, scene, main_thread_busy, active_operation_id, queue_depth}, pending_requests, thread_settings, turn_settings, account_revision and scene_context. File state follows confirmed HIP events; Save As preserves execution identity.
GET `/events?after=N`: native Codex projections, monotonic sequence, cursor, resync_required. No separate durable chat history. GET `/thread` rehydrates native thread history.
Before a new native thread has a rollout, `/thread` can return `history_available: false` with native metadata. Preserve existing rendered items; this is not evidence of empty history.
POST `/threads/select` {thread_id?}; GET `/threads`; POST `/turn` {text, attachments: [attachment_id], model?, effort?, expected_thread_id?, settings_revision?}; POST `/stop` {}. The Panel binds submitted settings to the selected native thread revision; requested and natively rerouted current-turn models stay separate from the next-turn choice.
POST `/reconcile` reads native state without inferring Houdini outcomes. POST `/selection` submits one queued context read, returning nodes and epoch or an operation ID to query. This Panel read does not bind the MCP adapter's observation.
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
