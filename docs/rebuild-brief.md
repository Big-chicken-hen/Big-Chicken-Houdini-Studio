# Rebuild contract

Product: **Big-Chicken Houdini Studio**. New folder and new Git history; original HIA stays intact.
Source diagnosis: [the user's complete Pro diagnosis](pro-diagnosis.md). Do not lose its execution semantics while redesigning the UI.
Current delivery scope: [stage readiness review](stage-readiness-review.md). Preserve the architecture; fix confirmed boundaries, establish a real GUI and natural-language task slice, and validate the launcher visually.

## Required outcomes

1. Runtime alone owns scene identity, a bounded main-thread queue and durable operation receipts. HIP load/clear advances scene_epoch; check it inside the same main-thread callback that executes HOM. Query by operation_id never runs a script. Payload identity guards different scripts sharing one ID. Crashes between side effect and commit remain explicitly unknown.
2. Ordinary edits take one meaningful batch with optional targeted observations/checks. No default full snapshots, mandatory knowledge search, repeated validations or automatic capture. Keep general HOM and installed metadata; do not invent a node allowlist or Python sandbox.
3. Optional knowledge cannot block launcher, bridge or memory. FTS is opt-in, memory is workspace-scoped and explicitly written. No embedding installer or importer in the launch path.
4. Completely new native launcher and Panel. Launcher: workspace entrance, installation selection, optional HIP, owned process lifecycle. Panel: conversation, scene state, operation receipts, images and explicit decisions. Show Codex stop request/terminal separately from running or unknown Houdini work.
5. Preserve Codex App Server, native Thread/Turn persistence, native MCP images, loopback authentication, project-local data and user work. No auto recovery/reload, no second reasoning service, no legacy B2/FX startup contracts.

## Current implementation map

- `common.py`, `workspace.py`: app storage and workspace identity, explicit memory/FTS.
- `ledger.py`, `runtime.py`, `scene.py`, `runtime_server.py`: authoritative receipts and native HOM execution.
- `mcp.py`: seven small decision tools; observation binding and result re-query.
- `bridge.py`, `codex/`: native Codex integration and event projection. Stdio client/redaction reused from old HIA at 6d9a2d7b606d699fc85bf13586d31aa27455a63b; integration policy is new.
- `launcher.py`: launch controller; `houdini/`: project-local package and runtime hooks.
- `ui/shared.py`, `ui/launcher.py`, `ui/panel.py`, `ui/conversation.py`, `ui/requests.py`: new Qt launcher, native conversation projection, explicit requests and runtime receipts.

## Integration/API contract for the Panel

Use authenticated Qt network calls through `ui.shared.Api`. Bridge URL is in `.runtime/sessions/<BCS_SESSION_ID>/bridge.json`; token is only in BCS_SESSION_TOKEN environment. Do not block Qt's main thread.

GET `/state`: workspace, thread_id, turn_id, codex {state, alive, stop_requested}, runtime {connection, scene, main_thread_busy, active_operation_id, queue_depth}, pending_requests.
GET `/events?after=N`: native Codex projections, monotonic sequence, cursor, resync_required. No separate durable chat history. GET `/thread` rehydrates native thread history.
Before a new native thread has a rollout, `/thread` can return `history_available: false` with native metadata. Preserve existing rendered items; this is not evidence of empty history.
POST `/threads/select` {thread_id?}; GET `/threads`; POST `/turn` {text, attachments: [attachment_id], model?, effort?}; POST `/stop` {}.
POST `/reconcile` reads native state without inferring Houdini outcomes. POST `/selection` submits one queued context read, returning nodes and epoch or an operation ID to query. This Panel read does not bind the MCP adapter's observation.
GET `/operations`; GET `/operations/<id>`; GET `/operations/<id>/detail?offset=N`; POST `/operations/<id>/cancel` {}.
POST `/attachments` {path}: explicitly selected image copied into workspace, returns attachment_id, name, path.
GET `/models`; GET `/account`; POST `/account/login` {} returns native ChatGPT login URL.
POST `/requests/respond` {request_id, result}: preserve native approval/input response schema. Never automatically approve.
POST `/memory` {action: list|record|supersede|delete, body?, record_id?}. No auto memory.

## Coordination and validation

Keep changes on short-lived branches and group commits by behavior. Preserve published main history. Report actual validation and commit only owned files.
Keep test effort proportional: targeted faults (stale scene after queue, duplicate ID, response loss, oversized result, Stop while running, external effect then exception) and native UI screenshots. Do not repeatedly run full suites or perform gratuitous hash audits.
Project worktrees use `model_context_window = 400000` and `model_auto_compact_token_limit = 350000`. Bridge forwards these two project settings into native scene threads. These are configured limits, not a measurement of an already running task's effective context.

The first real Houdini node workflow and native Codex Box task are recorded in [stage readiness results](stage-readiness-results.md). Broader scene, capture, render and interruption behavior remains unverified. Fakes, generated schemas and offscreen screenshots do not extend that evidence.
