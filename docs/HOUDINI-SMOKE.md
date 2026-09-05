# Real Houdini node smoke

This entry is **not run** until a reviewer executes it in real Houdini and inspects its unique report. Offline contract tests, native Qt offscreen tests and generated scripts do not prove the GUI chain. This smoke does not request Codex inference.

## Prepare a dedicated workspace

Use the current checkout's installed console Python, with `HIA_PROJECT_ROOT` pointing to that checkout:

```powershell
.runtime/venv/Scripts/python.exe -m studio.houdini_smoke prepare
```

The command creates a new workspace with a `gui-smoke.json` marker and a unique `.runtime/houdini-smoke/<run_id>/report.json` with status `not_run`. It starts no process and imports neither `hou` nor Qt. The marker contains only `purpose: houdini-gui-smoke`, `workspace_id` and `run_id`.

Select that workspace in the production launcher and open a **new Houdini GUI without an initial HIP**. Keep it empty. Do not reuse an existing user session, edit nodes, load a HIP or start a Codex turn. The launcher supplies `HIA_PROJECT_ROOT`, `BCS_WORKSPACE_ID`, `BCS_SESSION_ID`, `BCS_SESSION_TOKEN` and `BCS_PYTHON_EXECUTABLE`; do not print, copy to command arguments or persist the token.

## Start on the Houdini main thread

In that GUI's Python Shell:

```python
from studio.houdini_smoke import start
report_path = start()
print(report_path)
```

`start()` returns immediately. Do not join its worker, busy-wait in Qt or call `processEvents()`. A reviewer may instead use a tiny explicitly authorized production execute operation that calls `start()`; the worker waits up to 15 seconds for this bootstrap operation to finish before issuing its own context. Bootstrap tool calls must be counted separately from the smoke's recorded tool calls.

The entry validates the dedicated marker, matching workspace/session identities, initial HIP being absent and the runtime descriptor's PID matching this Houdini process. An exclusive `gui-smoke.claim.json` allows only one attempt per prepared workspace. All actual scene reads, including the new/clean HIP and empty `/obj` guards, occur inside the production scene queue. A failed/unknown attempt is inspected by its original IDs; it is never replayed to recover a missing response.

The harness opens this installation's **registered** `.pypanel` using real `hou` and `hdefereval`. It checks the resulting root is the production `StudioPanel` and has no interface script errors. The existing widget and pane remain available as `studio.houdini_smoke._panel` and `_pane` for a reviewer's explicitly authorized follow-up on the GUI thread. No new service or production control route is installed.

## What this slice measures

One production `studio.mcp` stdio child first calls `hia_context` and waits for that exact context to finish. If necessary, it uses `hia_operation get` through the same adapter so the completed observation binds the subsequent write. It then submits one batch:

- Create one unique `/obj/bcs_smoke_*` geo without initialization scripts.
- Create a Box with all size components set to 2, an attribute wrangle and an output Null; connect them.
- Cook the output through `geometry()`, read point/primitive counts and the actual `studio_smoke` point attribute values.
- Run the batch's targeted parameter, connection and geometry checks; retain the authoritative operation receipt.
- Ask the real Panel to read that receipt through its Qt HTTP client and Bridge.

Only successful real assertions and receipts can mark cases `passed`. The report records commit SHA, Houdini/Python/Qt/PySide/Codex versions (Codex version from the launcher's preflight), session/runtime/operation IDs, measured tool calls and timings. It never contains a token. The unique network is left for inspection; no existing nodes are deleted, and no HIP is saved, loaded or cleared. No screenshot or flipbook is requested.

Expected fast path is context + execute. `hia_operation` polls, if observed, are recorded as actual additional calls. A timeout can leave Houdini work pending: look up the recorded operation IDs (or recorded owner ID if no response arrived), never resubmit the script. Status `passed` describes this deterministic node slice only.

## Separate natural-language acceptance

After the deterministic result is reviewed, use the real Panel in this dedicated GUI to create a native Codex conversation and submit:

> 在 /obj 下新建一个唯一命名的 geo，里面创建一个 Box，把 size 的三个分量都设成 2。用一个 HOM 批次完成，并回读参数确认。不要搜索资料，不要截图，不要保存 HIP。

Codex must choose tools and generate its own HOM. Record actual tool count, receipt IDs, resulting scene and Panel response. Do not label the deterministic script as model-generated work. Native account login, if needed, remains an explicit user flow; do not copy global credentials.

## Still unverified by this entry

Cook-failure outcome handling, injected response loss, duplicate payload conflict, cancellation, reachable Stop during long HOM, HIP reload/clear epochs, restart recovery, capture/frame restoration, image input, materials, simulation and rendering remain separate acceptance work. No install/version-wide support claim follows from a single tested Houdini build.

The panel APIs were checked against the installed Houdini 22.0.368 HOM definitions and the official [Desktop](https://www.sidefx.com/docs/houdini/hom/hou/Desktop.html), [Python Panel](https://www.sidefx.com/docs/houdini/hom/hou/PythonPanel.html) and [hipFile](https://www.sidefx.com/docs/houdini/hom/hou/hipFile.html) documentation. Actual execution is still required; do not substitute `hython` or fake `hou` for the real GUI.
