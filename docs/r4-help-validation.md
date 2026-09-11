# R4-HELP-1 — evidence preparation, not a fix

## Decision and current status

The owner authorized the full [Pro review](r4-help-review.md) on 2026-09-11.
[R4-HELP-1](acceptance-issues.md#r4-help-1studio-启动后的-houdini-内置帮助失效)
blocks automatic Ready/merge/Public RC for PR #14. Development startup has an
owner-reproduced failure; native startup of the same Houdini installation is
owner-reported normal. Matching real GUI snapshots now support the host/pane
comparison below. Root cause, introducing commit and payload GUI impact
remain unknown. No production fix or new package has been made.

Reviewed code: `e686e548352da2de3b742f393c52568df09551d2`.
Existing candidate: `0.1.0-rc.1-8af563981e73`. Its previous checks do not prove
embedded help works. Local evidence remains in
`E:\Big-Chicken-Houdini-Studio\.runtime\maintenance\help-browser-20260911`.
The original missing-DLL test error, unsuitable standalone Qt probes and native
offscreen/hython exit 139 remain invalid as production regression evidence.
Do not rerun them to fill the GUI evidence gap.

## Audited read-only snapshot

The development-only [script](../scripts/inspect_houdini_help.py) is not wired
into the product or installer. It uses modules already loaded in the real GUI,
checks the existing application's main thread before HOM/Qt object access,
and creates no host, application, browser, QML engine or message handler.
The first owner-run native snapshot safely returned `unavailable`: Houdini's
Python Shell was not on the GUI main thread. That original result remains
preserved. The entry now uses Houdini's existing
`hdefereval.executeInMainThreadWithResult` for the one bounded read, retaining
the main-thread guard inside the callback. This dispatch does not start a scene
operation or create a new UI/engine; report-file writing remains outside it.

- Selects an existing `hou.HelpBrowser` through the documented HOM API. Multiple
  candidates require an exact pane name; no first-window guess or scene lookup.
- Records host identity, cwd/preferences, narrowly allowlisted environment
  fields, existing Studio module presence, current help URL and actual GUI Qt
  library paths. Loaded modules do not prove the Panel is visible.
- Uses documented `qtParentWindow()` only when HOM confirms that a floating
  window contains exactly that help pane. Embedded/shared windows are marked
  unavailable. It never scans all application widgets or wraps raw pointers.
- Within that single-help window, visits at most 192 QWidget descendants to
  depth 10. Only already typed QQuickWidget objects have their documented
  status/errors/source/root read. No QML object graph traversal, guessed getter,
  navigation toggle or repaint/screenshot operation is performed.
- Qt 6.8.3 `QQuickWidget.engine()` and `rootContext()` call `ensureEngine()`;
  **neither is used**. Only an existing root's `qmlEngine(root)` association is
  queried. With no root/binding, engine paths remain unavailable instead of
  constructing a replacement. Library paths and existing engine paths remain
  distinct facts.
- Query strings, fragments and URL user-info are removed. No full environment,
  session token, authentication store, chat body or command line is exported.
  Each invocation exclusively creates a new small JSON in the local evidence
  directory; existing snapshots are not overwritten.

Method references: [HOM HelpBrowser](https://www.sidefx.com/docs/houdini/hom/hou/HelpBrowser.html),
[HOM PaneTab](https://www.sidefx.com/docs/houdini/hom/hou/PaneTab.html),
[Qt QQuickWidget](https://doc.qt.io/qt-6.8/qquickwidget.html), and
[Qt 6.8.3 implementation](https://github.com/qt/qtdeclarative/blob/v6.8.3/src/quickwidgets/qquickwidget.cpp#L689).

Six focused fake-object safety tests exercise wrong-thread rejection,
embedded/shared-window rejection, failed-QML inspection without engine creation,
existing-engine association/URL sanitization, a hard subtree bound, and one-shot
shell dispatch without a GUI-thread self-wait. These
tests verify diagnostic boundaries only; they are not Houdini GUI evidence.
On 2026-09-11, `scripts/check.py --pattern test_help_inspection.py` passed all
five initial tests and Ruff. The shell-dispatch update passed six focused tests
and Ruff. Preparation commit `e930abd` also passed all five
[CI jobs](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34561123764).
These CI results do not close R4-HELP-1. The builder's
source allowlist excludes this development script and all tests/docs; the
existing installer and Tester ZIP were not rebuilt or modified.

## Native GUI baseline obtained

The owner reports normal native help and supplied a
[cropped homepage screenshot](evidence/r4-help/native-help-home.png) showing
the address bar, navigation and homepage content at `http://127.0.0.1:48626/`.
That screenshot is an owner observation, not a full navigation test or a
process-identified automated capture.

The later main-thread snapshot `native-27596-4e2d78530a.json` captured the actual
GUI on 2026-09-11 at 04:16:16 UTC:

- Actual EXE: `Houdini 22.0.368/bin/houdini.exe`, PID 27596; an OS read identified
  Explorer as its parent. No Studio runtime or Panel module was loaded.
- Native cwd is `C:\Users\Administrator`, **not the Houdini bin directory**.
  Earlier speculation that native startup works because of a bin cwd is not
  supported by this baseline. Preferences remain the native houdini22.0 folder.
- Current embedded HelpBrowser `panetab10` points to the loopback homepage.
  Qt paths resolve to this installation's `qt` tree; effective library paths
  include its `bin/Qt_plugins` and `bin` directories. No Launcher private
  PySide6 entry occurs in this baseline PATH.
- The help pane is embedded in a shared main window. In accordance with the
  scope guard, no global Qt scan was made and carrier/QML-engine errors remain
  unavailable. This is not proof that no QML errors exist.
- A subsequent 55-second process observation saw an already running renderer
  from this installation's `qt/bin/QtWebEngineProcess.exe`, parent 27596. It did
  not capture that renderer's earlier creation event or infer an exit result.

The first snapshot rejected the Python Shell worker thread; the next obtained
host/Qt information but found no open HelpBrowser. Both remain preserved. The
owner then reopened help while keeping the Python Shell and produced the
successful pane snapshot above.

## Studio GUI failure obtained

After the owner normally closed native Houdini and started the E: development
`Studio.exe`, `studio-11004-541015216e.json` captured the blank GUI at
04:21:03 UTC on 2026-09-11. The owner's first pasted command had a Python syntax
error; the subsequent `.get('capture')('studio')` invocation produced this JSON
successfully. The syntax error is not a failure of help or of the completed
snapshot.

| Observed fact | Native A | Studio B |
| --- | --- | --- |
| Houdini process | PID 27596, Explorer parent | PID 11004, Studio supervisor parent |
| EXE / version | Houdini 22.0.368 `bin/houdini.exe` | Same EXE and version |
| Preferences | Native `Documents/houdini22.0` | Same directory |
| Help pane | Embedded `panetab10`, current tab | Embedded `panetab10`, current tab |
| Current URL | `http://127.0.0.1:48626/` | Empty string |
| Configured homepage | `http://127.0.0.1:48626/` | Same homepage |
| Owner-visible result | Homepage normal | Still blank |
| Runtime / Panel modules | Both absent | Runtime loaded; Panel module absent |
| Qt library version | 6.8.3 | 6.8.3 |
| GUI `libraryPaths()` / `QLibraryInfo` | Houdini's installation | Identical values |
| Existing QML carrier / engine | Unavailable: embedded/shared window | Same safe-inspection limit |

This run establishes that failure was already present before loading the Panel
module. It does not rule out the Runtime or an earlier startup/environment
effect. Identical Qt library metadata does not prove identical actual QML or
helper loading. Scene identity and a complete plugin inventory were not
collected; this is not the full controlled navigation/authoring acceptance.

The snapshots retain the relevant differences without changing them: Studio's
PATH includes its development venv's PySide6 directory after the native Houdini
directories; Studio uses its workspace `work` cwd, local temp/XDG roots and
integration Python/package/search settings. Native uses its normal user cwd
and temp settings. These are comparison facts, not a finding that any particular
variable caused the failure. No PATH, cwd, preference or proxy correction has
been applied.

The first Studio process observation ran from 04:19:11 to 04:20:07 UTC and saw
six QtWebEngine process starts whose parent was PID 11004. Each was unavailable
by the subsequent OS detail query; actual helper path, role and exit status
could not be read. Event timestamps are observer receipt times, not a measured
process lifetime. A second observation at 04:22:16–04:23:11 UTC saw no new child;
it cannot negate the earlier starts. Native's earlier observation saw a live
renderer from Houdini's `qt/bin/QtWebEngineProcess.exe`. The records are:

- `native-children-20260911-121639.jsonl`
- `studio-children-11004-20260911-121911.jsonl`
- `studio-children-11004-20260911-122216.jsonl`

The current Studio session's `houdini.log` was zero bytes at inspection. Neither
this empty log nor missing exit information proves that no Qt error occurred.
No missing-DLL dialog was reported in this comparison. The old diagnostic
probe's DLL popup remains separate evidence.

The owner is now resting. The next step is one real startup with finite logging
enabled, not another headless browser probe. No new GUI is launched or active
GUI closed while waiting; the logging patch remains unapplied. Root cause and
release-payload impact remain unknown, and R4-HELP-1 remains open.

## Repeating the GUI comparison

No GUI or test scene is opened automatically. The owner chooses a safe time,
preserves unsaved work, opens the application and normally closes its windows.
Do not take execution ownership of another active Studio workspace.

1. **A: native.** Use the owner's normally working native entry for the same
   Houdini 22.0.368 EXE. Use the same account/preferences/plugins and unchanged
   Clash configuration. Open the help page using the originally failing entry;
   record that entry in words and capture the help window screenshot manually.
2. With that help pane open, run this one line in Houdini's Python Shell:

   ```python
   import runpy; runpy.run_path(r'E:\Big-Chicken-Houdini-Studio\scripts\inspect_houdini_help.py').get('capture')('native')
   ```

3. **B: Studio.** At the agreed safe time, open `E:\Big-Chicken-Houdini-Studio\Studio.exe`
   and the same test scene/help entry. Keep the Panel state recorded. Run:

   ```python
   import runpy; runpy.run_path(r'E:\Big-Chicken-Houdini-Studio\scripts\inspect_houdini_help.py').get('capture')('studio')
   ```

4. Compare host EXE/version/preferences, help pane type/URL/entry, actual GUI
   library paths, existing carrier errors and availability. Screenshots confirm
   navigation/body appearance; snapshot `captured` never means help passed.
   If multiple panes are reported, supply `pane_name='exact name'`; do not
   automatically close panes or choose an unrelated window.

## Prepared one-launch logging procedure — not enabled

The A/B comparison did not safely expose the existing QML carrier, and the
ordinary log did not retain the initialization error. Prepare one subsequent
real GUI launch with the approved `QML_IMPORT_TRACE=1`, `QT_DEBUG_PLUGINS=1`
and appended `qt.webenginecontext.debug=true` logging rule. Inject these only
into the final Houdini child environment, after helper cleanup, before Qt
initialization; the GUI snapshot must confirm their arrival. Do not simply set
QT flags outside Studio and assume they survive the existing cleanup.

The local evidence directory holds an unapplied `one-launch-logging.patch`
against `supervise()`'s final `Popen` call. It uses an environment copy, leaves
the command/cwd/log destination unchanged and adds only logging fields. It is
not a product option, startup configuration or packaged file. After the owner
is ready, check the patch still matches the current source, apply only this
temporary hunk, and launch via the same `Studio.exe`. Revert the hunk immediately
after that intended Houdini child has started; its copied environment remains
in that process, while later launches return to ordinary settings. Do not leave
the hunk active overnight or commit it as a fix.

Preparation verified the proposed source parses, the existing command/cwd/stdio
arguments are unchanged, a fake parent environment is not mutated, only the
four diagnostic fields differ, and the existing logging rule is retained.
`git apply --check` passed without applying the patch. These checks do not
verify that Houdini emits or captures the required initialization errors.

`QT_FORCE_STDERR_LOGGING=1` in that same temporary child environment routes Qt
messages to the already captured stderr instead of requiring a new global
message handler or debugger. Qt 6.8.3 implements this flag in
[`shouldLogToStderr()`](https://github.com/qt/qtbase/blob/v6.8.3/src/corelib/global/qlogging.cpp).
It changes the logging destination, not WebEngine resource paths or Chromium
behavior. Verify it and the three approved diagnostic settings in the actual
GUI snapshot; absent settings or output are an evidence gap, not a pass.

Open only the agreed help page for this diagnostic session, observe the bounded
child-process window, collect relevant initialization errors and the snapshot,
then let the owner normally close the test GUI. Raw diagnostic logs stay in the
private E: evidence/cache directories; publish only reviewed excerpts without
authentication values, complete command lines or unrelated user data. No process
has yet run with this patch.

For the timed child-process trace, observe from before the agreed help action
through failure: time, host/parent/PID, actual helper EXE, allowlisted process
role and exit status only. Do not persist raw command lines, unrelated process
events or full environments. Mark missed/too-fast events unavailable. No
process trace is equivalent to the owner's window check.

## Stop and acceptance rules

Choose the next single-variable comparison from observed errors: a particular
resource/path, native environment with the same cwd, or identical host startup
with Studio autostart/Panel absent. No full variable matrix or speculative fix.
Prove a candidate correction with restore-failure/reapply-recovery evidence.
Preserve the six user Houdini search paths, native preferences, cwd/history,
Clash, and all execution/consent boundaries.

A real fix must pass both bootstraps' focused tests and real H22 help navigation,
node pages, close/reopen, at least two cold starts, small Panel authoring and
normal owner-driven exit. Independently verify the actual release payload via
its own Studio.exe, without Owner installation or the development venv.
Production/package edits need a new source/builder/build/installer identity and
new payload GUI checks before refreshing the Tester ZIP. A proven development-
only dependency correction need not rebuild unaffected verified installer bytes.
Standard-user Installer acceptance remains a separate pending gate.
