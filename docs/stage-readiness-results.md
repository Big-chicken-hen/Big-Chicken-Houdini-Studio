# Stage readiness results — 2026-09-05

The first real node workflow and a natural-language task have now completed in
Houdini 22.0.368. This is a development preview with a verified small workflow;
rendering, scene replacement and long-running cook interruption remain unverified.

## Changes and checks

Implementation reviewed at `d4ed92096c15e7733f2adebbf6de8c68673a8cea`:

- Backend CI excludes native Qt tests before import. A separate Windows job installs
  Qt, runs its tests and retains Panel and launcher preview artifacts.
- Bridge exceptions support normal traceback handling. Scene input checks reject
  missing targets; tool schemas describe bounded checks and observations. Script
  failures report bounded exception types and submitted-source locations.
- Panel hydration preserves native events across an in-flight history read.
  Definite submission rejection preserves editing; uncertain submission remains
  distinct. HTTP 200 operation receipts, including receipts with an execution
  error, reach the receipt display. Empty native tool approval requests have an
  explicit Allow action instead of requiring an empty JSON form.
- The launcher has a new rain-night workspace entrance, inline first-workspace
  creation, secondary settings, persistent copyable errors and actual process
  stages. Artwork is local and included in the wheel.

The integrated Qt check ran 15 tests successfully, including real asynchronous
HTTP responses and launcher ownership/state cases. The subsequent native approval
change passed its focused interaction test. Ruff passed during integration.
[The final implementation CI run passed](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/33962106453),
covering Windows/Linux backend environments on Python 3.10/3.13 and a separate
Windows Qt job. The launcher was reviewed in eight offscreen states, including
800×620 and DPR 2. These images are UI fixtures, not Houdini evidence.
An isolated wheel build also confirmed that the bundled artwork is included.

## Real Houdini evidence

Environment: Houdini 22.0.368, its Python 3.13.10 and PySide6/Qt 6.8.3,
Codex CLI 0.153.4. The production launcher opened a dedicated new workspace
without an initial HIP. Existing user Houdini windows were preserved.

The registered `big_chicken_studio.pypanel` created the actual `StudioPanel`
without interface script errors. Production MCP stdio and the runtime's bounded
main-thread queue created Box → Attribute Wrangle → Null under
`/obj/bcs_smoke_97226d95c240422b`. Size was `(2, 2, 2)`; the cooked result had
8 points, 6 primitives and the expected point attribute.

This first run, on `c7b6364`, exposed the Panel receipt bug after the scene work
passed. Its original failed `report.json` is retained. After the fix, the same
operation `a1f91a962ceb4b31b88653d7edd46e87` was queried successfully; its creation
script was not replayed. The registered Panel was then recreated from the updated
modules and again displayed the persisted receipt.

## Real natural-language task

After native ChatGPT login, the actual Panel submitted a request to create a
uniquely named geo containing a size-2 Box, perform one HOM batch and read back
the parameters, without searching, capturing or saving the HIP.

- Native thread: `01a07130-dd63-7501-a9e4-f9d888df0037`.
- Native turn: `01a07131-a15c-7951-8cac-12c64474f2ab`.
- Model: `gpt-6-astra`, reasoning effort `medium`.
- Exactly two model tool calls: `hia_context`, then `hia_execute_hom`.
  The user explicitly approved the requested scene read and creation.
- Execution receipt: `afd07e7fb8d94cf8b6316759f217564d`, state `finished`,
  mutation outcome `completed`. The batch read back `(2, 2, 2)` at
  `/obj/box_size_2_geo/box_size_2`. Its assertions passed; the separate optional
  checks field correctly remains `not_run`.
- The runtime reported 0.030985 seconds queued and 0.003632 seconds executing
  this batch. These numbers exclude login, inference, network retries and approval
  wait and are not an end-to-end speed claim.
- The original Panel displayed the final response. Recreating the registered
  Panel recovered the native history with the same two tool items and displayed
  the same persisted execution receipt.

Codex reported WebSocket timeouts and then a successful fallback to HTTPS.
No proxy configuration change was included on the basis of those retries.

Local detailed evidence remains under
`.runtime/houdini-smoke/7266cb2fde624ccd8197f26887e256bd/`: the original report,
`acceptance.json` and actual Panel images. The acceptance supplement records the
fixed receipt query and recreated Panel; it does not replace the original failure.
Account-bearing screenshots and local session data are not published.

## Remaining scope

Existing HIP replacement, viewport capture and image reasoning, render output,
long-running cook cancellation, process-crash timing, and history across a full
application restart remain unverified. Windows double-click launching has not
been exercised through desktop interaction. No existing HIP was saved, cleared
or loaded during this acceptance, and no Houdini installation or global user
configuration was changed. Configured context limits remain 400000/350000;
effective running-task capacity has not been measured.
