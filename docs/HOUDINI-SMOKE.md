# Real Houdini acceptance

This is an opt-in integration check, not a startup dependency. Run in an idle,
disposable Studio workspace/scene. It creates one unique `/obj/bcs_smoke_*`
network and leaves it for inspection. It does not load, clear or save a HIP,
change existing user nodes, install configuration, or run Codex inference.

Launch Houdini using Studio, then run in its Python Shell:

```python
from studio.houdini_smoke import start
report_path = start(capture=True, open_panel=True)
print(report_path)
```

Do not join the worker or busy-wait in the UI. The function returns immediately;
read the report file from disk after it reaches `passed` or `failed`. The finite
worker uses the real `hdefereval` dispatcher and the actual registered Python
Panel. Scene work goes through the production MCP stdio child and authenticated
runtime, not through a fake `hou` module. Authentication stays in environment
variables, not command arguments or the report.

Covered: registered Panel/PySide6 loading, main-thread assertion, a native Box
with size 2, connections, attribute wrangle, output cook/geometry inspection,
parameter edit, deletion of an owned temporary node, optional PNG capture,
injected admission-response loss with same-ID receipt recovery, and the real
receipt read back through Bridge into the Panel. PNG transport is not an
assertion about artistic quality. No screenshot is taken when capture=False.

The report always separates `codex_inference_verified` and
`hip_replacement_verified` (both false in this suite). Offscreen Qt CI only
checks the launcher/Panel and the smoke harness syntax/contracts; it does not
execute this suite or certify Houdini. A timeout never triggers script replay.

## Native Codex vertical acceptance

In a new Panel conversation, send:

> 在 /obj 下新建一个唯一命名的 geo，里面创建一个 Box，size 三个分量都设成 2。
> 用一个 HOM 批次完成，并回读参数确认。不要搜索资料，不要截图，不要保存 HIP。

Expected first-use path: `hia_context` followed by one `hia_execute_hom` with
three `parm_equals` checks. Subsequent known edits can reuse the observation
until the scene is replaced. Verify the actual nodes, receipt and Panel answer;
record observed tool count and timings. This is a user-run inference test, not
a claim made by the deterministic smoke.

## Next high-risk manual checks (not yet certified)

Use a separate throwaway HIP for load/clear/replacement, never an unsaved user
scene. Observe a scene, replace it, and ensure a stale-epoch operation is
rejected before HOM. Also exercise long HOM with `checkpoint()`, queued
cancellation, Stop while native Codex is active, cook errors, Houdini exit and
manual relaunch. Confirm that Codex interruption never stands in for a runtime
terminal receipt. Expand this suite only after running the existing vertical
slice on real supported Houdini builds; do not build an integration platform.
