# Scene operation protocol

The runtime owns operation facts. Codex turn events, HTTP disconnects and Stop acknowledgements do not establish whether HOM finished. There is no script replay or automatic recovery planner.

## Admission and scene identity

`POST /operations` carries `operation_id`, `workspace_id`, `runtime_id`, `owner_id`, `kind`, `scene_epoch` and `arguments`. The adapter allocates the ID before sending. The ledger stores a canonical payload digest and rejects reuse of the ID with a different payload. Repeating an identical submission only reads its existing receipt, including after Stop or runtime restart.

Arguments and targeted check/view definitions are validated before admission, without HOM. The script is compiled before execution. The submitted payload is copied so later caller changes cannot change admitted work. No script text is persisted in the ledger.

Every scene read, cook, capture and script uses one queue with a default total admission capacity of 16. Capacity includes dispatched and running work. A cancelled queued item retains its capacity slot until physically drained, so repeated submit/cancel cannot grow a hidden queue. `/health` reads cached scene facts and runtime state without HOM. `queue_depth` is occupied capacity; `main_thread_busy` means an operation has entered its main-thread execution callback.

Inside that callback the runtime checks the Stop/cancel fence and the observed scene epoch before persisting `running` and calling scene code. `BeforeLoad` and `BeforeClear` advance the epoch even when the HIP path is unchanged. These are explicit [SideFX HIP events](https://www.sidefx.com/docs/houdini/hom/hou/hipFileEventType.html). Save/rename does not substitute for scene identity. The adapter never refreshes context before a write. Only its latest self-allocated context operation ID, from its own owner and current runtime, can update its observation binding. Panel and other adapter context receipts cannot bind writes; missing result epochs preserve the previous observation.

## Targeted checks and observations

The `hia_execute_hom` and `hia_inspect` schemas publish local `$defs` for check/view variants. Required fields and allowed properties are visible before calling the tool; the adapter validates those same shapes without contacting HOM. Runtime argument validation remains the execution boundary.

Every check requires `kind` and an absolute node `path` without `..` segments:

| `kind` | Other required fields | Optional fields / meaning |
| --- | --- | --- |
| `node_exists` | none | Boolean `expected`, default `true` |
| `node_type` | string `expected` | Installed node type name |
| `parm_equals` | nonempty string `parm`, JSON `expected` | Nonnegative finite `tolerance`, default `0.000001` for numeric comparisons |
| `input_equals` | `expected`: source node path or `null` | Nonnegative integer `index`, default `0`; `null` requires an existing target with an unconnected input |
| `cook` | none | Force a targeted cook and report node errors |
| `geometry_nonempty` | none | Target geometry must contain points |

A missing `input_equals` target fails with `NODE_NOT_FOUND`, including as a precondition. It does not represent an unconnected input.

`preconditions` run before the script, `checks` run after it, and both accept up to 64 checks. Preconditions can cook when explicitly requested. Neither runs implicitly when omitted.

`views` accepts 1–32 views; `observe` accepts up to 64. A view defaults to `view: "node"` at `path: "/obj"`. Other variants explicitly select `view: "parms"` with 1–64 nonempty `names`, `"children"` with optional integer `limit` (1–200, default 64), `"geometry"`, or `"checks"` with a check list. Unknown fields are rejected.

**`observe` reads the declared views both before and after execution. Its targets must already exist.** A missing target during the before-read prevents the script from starting. For a node created by the batch, use post-execution `checks` or put its parameter readback in `result`; do not declare it as a before/after observation. For example, a new Box batch can return `result = {"size": box.parmTuple("size").eval()}` without an extra inspection or screenshot.

## Execution facts and durability

| Field | Meaning |
| --- | --- |
| `state` | `queued`, `running`, `finished`, `failed`, `rejected`, `cancelled`, `unknown` |
| `mutation_outcome` | `not_run` before entering the script; `partial` once entered and interrupted/raised; `completed` once the script returned; `unknown` if execution cannot be confirmed; `none` for non-script operations |
| `checks_outcome` | `passed`, `failed`, `not_run`, independent of script completion |
| `external_side_effects` | Always `unknown` for general Python/HOM |
| `automatic_retry_safe` | Always `false`; Undo grouping makes no external transaction guarantee |
| `result_ref` | Operation ID for persisted detail pages |

Execution facts change at the actual script boundary, not by classifying exception names. A script may raise `INVALID_ARGUMENTS` after writing a file; that remains `partial`. Optional checks, after-observations, result conversion, serialization and cached-state refresh do not erase `completed`. A `finished` receipt can therefore contain failed checks or `observation_error`/`result_error`; it does not certify artistic success. No automatic Undo is performed.

Compile/HOM errors preserve a bounded `exception_type`, a short `message` reason, and the deepest matching submitted `script_line` when available. Compilation syntax errors also include `script_column`. Lines and columns are one-based. Diagnostics do not format full tracebacks, source snippets or locals; known secrets, credential assignments, environment dumps and absolute paths are omitted before truncation. `COMPILE_FAILED` remains rejected/`not_run`; an exception raised after entering the script remains `partial`. These fields explain where to edit the next batch, not whether it is safe to retry the original one.

The full detail and final receipt are committed together before completion is visible to a client. A receipt commit failure disables new scene operations and prevents queued work from starting. The worker attempts only to persist `unknown`; it never reruns the script. If even this write fails, individual receipt/detail reads return `RECEIPT_UNAVAILABLE`, while the operation list explicitly projects `unknown` with `receipt_confirmed: false`. This projection is not a durable receipt. `/health.storage_fault` remains set and resume is rejected. A late exception after a successfully committed terminal receipt preserves that receipt.

A new runtime recovers old `running` entries as `unknown` and old `queued` entries as cancelled with `not_run`. It does not recover them on HTTP reconnect and does not replay either class. A crash after side effects but before the final commit is inherently uncertain; this protocol does not promise exactly-once execution for arbitrary Python.

## Stop, queries and transport limits

`POST /owner/stop` establishes an owner fence and requests cancellation of its pending operations. Queued operations cannot start after the fence. Already running HOM remains `running` with `cancel_requested: true` until it returns or reaches an explicit `checkpoint()`. Native blocking HOM cannot be forcibly interrupted by stopping Codex. `POST /owner/resume` requires the queue to drain and storage to be healthy.

`GET /operations/<id>` and `GET /operations/<id>/detail?offset=N` never execute HOM. Detail offsets count Unicode characters, with a default 24,000-character page and `next_offset` cursor. Normal result summaries are at most 16,000 UTF-8 bytes; larger successful results remain successful and retain full paged details. Summary limits do not replace the final receipt with an execution error.

If submission returns an uncertain transport or server error, the adapter queries the allocated ID once and then polls only that ID. If unavailable, it returns the ID with explicit uncertainty and no retry permission. Partial HTTP responses and invalid response JSON count as connection loss. An unconfirmed submission must not be repeated with a new ID.

HTTP binds `127.0.0.1`, rejects redirects/cross-origin/chunked requests, authenticates with the environment-only session token, limits bodies to 2 MiB, and bounds concurrent handlers to 32. MCP stdio processes requests serially with pipe backpressure, bounded 2 MiB line reads, and no executor backlog. Oversized lines are discarded in bounded chunks. Seven decision tools remain; there is no new tool discovery or recovery system.

Capture receipts retain an artifact ID. The adapter queries the artifact and emits a native MCP `image` content item, with no duplicate `structuredContent` payload. Image retrieval failures do not recapture the scene. Artifact bytes remain limited to 12 MiB and under the app's `.runtime` storage.

A single-frame capture modifies only a stashed copy of the viewport flipbook settings. It explicitly disables simulation initialization, motion blur, keyframe-only scope and rendering all viewports, and still restores the previous frame on success or failure. SideFX documents that [flipbook simulation initialization resets simulations and motion blur renders extra subframes](https://www.sidefx.com/docs/houdini/hom/hou/FlipbookSettings.html); these options must not be inherited from a previous interactive flipbook. Moving to a requested frame can still cook, and this change does not promise simulation-cache rollback or bounded progressive-render time. Fake settings tests verify the calls and restoration, not actual viewport/cook behavior.

## Metadata, documents and output

`hia_inspect` supports `view=parameters` for an existing node. `pattern` filters
actual parameter names; `offset` and `limit` page their native metadata without
evaluating parameter values. Records retain the name returned by
`parm.parmTemplate()` (which can already be expanded) and native multiparm
instance indices. Do not infer an index base or a real parameter name from a
template suffix. Use `view=parms` with the discovered names to read values.

`view=geometry` accepts selected attribute `owners` (point, primitive, vertex,
detail), optional exact `attributes`, and `samples` from 0 to 16. Metadata reports
data type, tuple size, native qualifier and array status, limited to 64 attributes
per owner. Sampling uses direct element indices, at most 16 attributes per
sample, rather than constructing all point/primitive/vertex handles. Array,
dictionary and oversized tuple values remain metadata-only. String previews are
truncated explicitly. Native attribute metadata enumeration and the requested
node's cook can still cost work; the sample limit is not a cook-time guarantee.

`hia_lookup(source=metadata)` queries live installed node types/parameter templates through the same bounded main-thread queue, without requiring a scene observation. It must not call HOM from HTTP workers. `POST /lookup` accepts only `source=hom`: public symbol resolution uses static Python attributes and returns docstrings with the version cached at scene construction. It does not evaluate properties, read scene nodes or cook. No whole-installation metadata snapshot blocks startup.

`hia_lookup(source=documents)` and `hia_project_memory` use Bridge/workspace routes directly. MCP loads the runtime descriptor only when a runtime capability is actually requested, so document and explicit memory operations work before Houdini connects.

Session secrets are removed from result strings, keys, labels and errors before persistence/truncation, and at HTTP/MCP output boundaries. Ordinary Python stdout/stderr from a HOM batch is discarded rather than forwarded to logs. Set `result` for useful diagnostics. Arbitrary native file-descriptor writes, third-party logging handlers, subprocesses and files deliberately written by a trusted script are outside this output filter; general HOM is not a Python sandbox.

## Focused verification

`tests/test_operations.py` exercises fake-HOM execution, real SQLite receipts and one authenticated loopback exchange. It covers stale queued scenes and same-path reload, bounded cancellation, payload conflict, lost/unconfirmed responses without replay, Stop while running, post-execution failures, preflight validation, external file effects, commit faults, restart uncertainty, paged oversized results, token filtering, native image content, document/memory independence and bounded stdio reads.

The readiness cases additionally cover missing/disconnected/connected inputs and the missing-target precondition, exported check/view schemas, compile/HOM diagnostic location and filtering, before/after observation behavior, and isolated flipbook settings with frame restoration on success/failure.

These tests do not establish real Houdini GUI dispatch, installed HOM metadata behavior, viewport rendering, native cook interruption, process-kill crash timing or Codex inference end-to-end behavior. Those remain manual integration checks.
