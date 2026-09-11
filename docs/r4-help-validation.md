# R4-HELP-1 — environment-key candidate, GUI recovery pending

## Decision and current status

The owner authorized the full [Pro review](r4-help-review.md) on 2026-09-11.
[R4-HELP-1](acceptance-issues.md#r4-help-1studio-启动后的-houdini-内置帮助失效)
blocks automatic Ready/merge/Public RC for PR #14. Development startup has an
owner-reproduced failure; native startup of the same Houdini installation is
owner-reported normal. Matching real GUI snapshots now support the host/pane
comparison below. The candidate below addresses a verified Python/Chromium
environment-key compatibility conflict. Whether it resolves this host's GUI
failure, the introducing commit and actual payload impact remain unconfirmed.
The existing installer and ZIP have not been rebuilt.

Latest result: actual Studio browser-child stop events now report
`0xC0000135` (`STATUS_DLL_NOT_FOUND`). This identifies the failure category,
not the missing module or the responsible inherited environment field. The
follow-up logging run still failed. The latest Pro review replaces the proposed
private Qt PATH-removal comparison with the three-key spelling correction below.
All temporary logging/autostart/PATH-removal hunks are removed.

## Latest review: final Windows host environment key spelling

The [latest Pro review](r4-help-environment-case-review.md) is preserved verbatim.
Its scope is implemented in `houdini_host_environment()` and the final
`supervise()` call to `Popen`: copy `os.environ` to an ordinary dict, rename the
three uppercase keys to `Path`, `SystemRoot`, `SystemDrive` on Windows, then
pass that dict directly to the host. Absent keys stay absent; non-Windows
environments are unchanged. Nothing is written back to `os.environ`.
All values, PATH entries/order/empty segments, six Houdini search variables,
native preferences, Runtime startup, cwd/history, tokens and proxy settings
retain their existing behavior. No Qt/DLL or sandbox settings are changed.

Independent source verification follows the actual
[Qt WebEngine v6.8.3 submodule](https://github.com/qt/qtwebengine/tree/v6.8.3/src),
`55749ed0af5869215b88007df0cba430746583ae`:

- [Renderer launch](https://github.com/qt/qtwebengine-chromium/blob/55749ed0af5869215b88007df0cba430746583ae/chromium/content/browser/renderer_host/renderer_sandboxed_process_launcher_delegate.cc#L126)
  enables environment filtering.
- [Target creation and filter](https://github.com/qt/qtwebengine-chromium/blob/55749ed0af5869215b88007df0cba430746583ae/chromium/sandbox/win/src/target_process.cc#L141)
  use a fixed allowlist with the three mixed-case names and exact-case matching
  in `FilterEnvironment()` (lines 408–427).
- [Python's Windows environment mapping](https://docs.python.org/3.13/library/os.html#os.environ)
  uppercases keys; [CPython 3.13.15 serialization](https://github.com/python/cpython/blob/v3.13.15/Modules/_winapi.c#L1051)
  preserves the spelling in an ordinary mapping passed to process creation.

The diagnostic now reads only those three original key/value entries from this
process's [GetEnvironmentStringsW](https://learn.microsoft.com/en-us/windows/win32/api/processenv/nf-processenv-getenvironmentstringsw)
block, scans at most 1,048,576 WCHARs, and releases the block in `finally`.
This creates no Qt object or process and reads no other process memory. The
existing `os.environ` snapshot remains for continuity, but it cannot establish
raw Windows key spelling. No earlier snapshot is relabelled as raw evidence.

Local checks on 2026-09-11:

- Before the correction, the new final-spawn regression failed because `Path`
  was absent; the other 12 launcher checks passed.
- After correction, 30 checks across `test_launcher.py`,
  `test_houdini_environment.py`, `test_windows_environment.py` and
  `test_help_inspection.py` passed. Ruff passed once on `src`, `scripts`, `tests`.
- The actual Windows child test launches two tiny Python processes without
  Qt/Houdini. Raw Win32 blocks keep uppercase names for the old mapping and
  mixed-case names for the correction, while `os.environ` shows uppercase in
  both. Every selected value is identical. Applying the pinned source's
  case-sensitive allowlist model discards all three old keys and retains all
  three corrected keys. Updating the existing PATH value through Python in
  the child preserves its original Win32 key spelling as well.
- Both development and installed Python bootstrap tests traverse the
  supervisor environment normalization before the final correction; custom
  search paths, native preferences, fresh test token and proxy survive.
- The diagnostic tests verify original spelling, a three-key allowlist,
  secret exclusion and a hard scan limit alongside the existing Qt safety gates.

These are implementation/serialization checks, not a real Chromium renderer
or Houdini GUI pass. No SideFX binary patch provenance or exact missing DLL is
claimed. The owner paused for class after these checks, then resumed. The next
owner action is one fresh E: `Studio.exe` Launch of the same HIP and opening
help. If recovery is observed, correlate the session and raw key spellings,
then finish the bounded real navigation/cold-start/Panel and payload gates below.
Do not apply the superseded private-Qt-PATH patch or request more generic logs.

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

The owner initially paused for rest, then returned for the logging run below.
No GUI was launched or closed by the diagnostic while waiting. Root cause and
release-payload impact remain unknown, and R4-HELP-1 remains open.

## Logging-enabled Studio GUI run — settings arrived, no Qt errors captured

The owner launched the same E: `Studio.exe` and selected
`Procedural_lake_village.hip`. The new session `7109cd7dbd0e4d9db4bf5b7db42bedda`
started Houdini PID 20812 at 04:53:32 UTC. The temporary logging hunk was removed
as soon as the intended child was observed; no diagnostic default remained in
production source. The owner's normal close later returned exit code 0.

- `studio-20812-27b317f02a.json` confirms all four diagnostic fields arrived in
  the actual GUI environment. Houdini retained the WebEngine debug rule and
  appended its existing SVG-warning suppression. That first snapshot had no
  HelpBrowser present; it remains an incomplete pane observation.
- After the owner kept both windows open, `studio-20812-ec9d0d776f.json`
  captured the same embedded `panetab10` with an empty current URL. The owner
  reports the help remains blank. Host/cwd/preferences/Qt paths match the prior
  Studio run, Runtime is loaded and Panel is still absent.
- The session's `houdini.log` remained empty. The 55-second child observation
  began at 04:53:56 UTC, after the owner had opened help, and saw no child. It
  missed the earlier initialization window; this cannot establish that no
  helper was started.
- A further read, `studio-20812-300e314678.json`, found an existing Houdini
  memory-log sink with two entries and no matching Qt excerpts. Its connected
  sources included Standard Error/Output, but not Generic Logging. This proves
  neither an absence of Qt errors nor that a particular sink received them.

The script's additional log read calls
[`hou.logging.defaultSink(False)`](https://www.sidefx.com/docs/houdini/hom/hou/logging/defaultSink.html)
and reads at most 2048 existing entries through
[`logEntries()`](https://www.sidefx.com/docs/houdini/hom/hou/logging/MemorySink.html).
It never creates, drains, connects or changes a sink. Only bounded Qt-related
text from Generic Logging and Standard Error/Output is retained; unrelated
source messages, full command lines and credential-bearing messages are omitted,
and URL query/user-info is removed. Two additional focused tests cover absent
sink behavior, filtering and the hard bound; all eight safety tests and Ruff
passed. These are diagnostic checks, not evidence that help is fixed.

Because these logging routes did not expose an initialization error, the next
approved comparison is a fresh Studio launch with only `BCS_AUTOSTART=0`
changed from the logging-enabled environment. The prepared local
`autostart-off.patch` keeps all command/cwd/stdio arguments unchanged and is
never committed as a product mode. Confirm its actual host environment and
Runtime/Panel module absence before attributing any visible improvement.

An initial attempt observed a fresh Houdini PID 29632 and the owner reported
normal help. The E: Studio session directory had no new session, and no GUI
environment snapshot was collected before that process closed. The owner then
confirmed it was opened directly through HIP/Houdini. **Record this as another
owner-reported normal native launch, not an autostart-off result.** Its process
trace saw a renderer from Houdini's own `qt/bin/QtWebEngineProcess.exe`,
subsequently exiting with status 0. The trace filename retains its original
intended-test label; it does not prove Studio launched that process. No Runtime
fix or successful causal comparison is claimed from this attempt. The next
attempt correlates a newly created E: Studio session to the actual host PID
before removing the temporary hunk.

## Captured real child exit status

The next attempt did correlate the E: Studio session
`d067398edcc140f5a806b8441a3179da` with Houdini PID 29188, parent supervisor
28908. The temporary [autostart-off patch](evidence/r4-help/autostart-off.patch)
was reversed after the host started. The owner reports help remained blank.
Before the owner supplied the next Pro analysis and closed this GUI, no snapshot
was taken to verify the actual `BCS_AUTOSTART` value and Runtime-module absence.
Therefore do not treat this as a completed Runtime-exclusion result.

The [process trace](evidence/r4-help/studio-autostart-comparison-child-events.jsonl)
did cover four child starts and four stop events between 05:11:34 and 05:12:29
UTC. All four exit statuses are `3221225781`, hexadecimal `0xC0000135`.
Microsoft defines this as
[`STATUS_DLL_NOT_FOUND`](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55).
The attempted helper image and role were still unavailable before lookup.
This is real host-child evidence, unlike the preserved invalid standalone
browser tests; it does not identify which DLL failed to resolve.

The owner then supplied the [follow-up Pro investigation](r4-help-followup-review.md).
Its two changes to the next step are exact WebEngine libraryinfo logging and,
if still needed, one diagnostic removal of the observed Launcher-owned PySide6
PATH entry. It does not authorize a permanent blanket PATH filter or Qt/DLL
replacement.

## WebEngine libraryinfo logging run — failure persists

The next real Studio session `8453e650bdf641bd91583b5dfc493870` started Houdini
PID 9924 under supervisor 19232 at 05:20:40 UTC. Runtime autostart returned to
the unchanged product default. The [temporary logging patch](evidence/r4-help/libraryinfo-logging.patch)
added `qt.webengine.libraryinfo.debug=true` while retaining earlier diagnostic
rules and the existing settings. Because stderr had provided no Qt records,
the child also requested Houdini's own `HOUDINI_DEFAULT_LOG_FILE` in that
session's E: log directory, with only Generic Logging and Standard Error
sources. These are native [Houdini logging settings](https://www.sidefx.com/docs/houdini/ref/env),
not a new message handler or product setting. The patch was removed immediately
after the session-correlated host started.

The launch record and `studio-9924-4802039ada.json` at 05:21:13 UTC confirm:

- The same saved-HIP launch target, workspace cwd, Houdini EXE and native
  preferences; the same actual GUI Qt library metadata.
- `BCS_AUTOSTART=1`, Runtime module loaded, Panel module absent.
- The WebEngine libraryinfo rule, stderr routing flag and native log-file/source
  variables all present in the actual GUI environment.
- The existing embedded help pane still has an empty current URL and the same
  loopback homepage. The owner reports it is still blank.
- The existing memory sink has two entries and no matching Qt text. The ordinary
  stderr file remains empty and no requested native log file was produced at
  inspection. Thus the helper/resource/locales paths are still **unavailable**;
  enabling a logging category was not equivalent to capturing its output.

The [new 55-second process trace](evidence/r4-help/studio-libraryinfo-child-events.jsonl)
captured six starts under PID 9924 and six stop events, all again reporting
`0xC0000135`. The helper image and role were unavailable at lookup. Timestamps
are observer receipt times and can appear out of order between start/detail
queries and stop-event delivery; do not infer exact lifetimes from them.
The selected System/Application and existing Security 4688 records provided
no matching additional event for this window. No audit policy was changed.

The owner is tired and further GUI requests are paused. There is no production
fix, no new installer/ZIP, and no release approval from these results.

## Superseded private Qt PATH comparison — never applied

This historical experiment was replaced by the latest environment-key review
above. Keep the patch as evidence of the prior proposal; do not apply it.

The [reviewable diagnostic patch](evidence/r4-help/private-qt-path-comparison.patch)
retains the logging run's settings and normal Runtime autostart. Its only
functional difference is removal of this exact known directory from the final
Houdini child's copied PATH:

```text
E:\Big-Chicken-Houdini-Studio\.runtime\venv\Lib\site-packages\PySide6
```

Syntax and focused dictionary checks passed: parent environment unchanged;
native Houdini's PySide6 path, other user paths, similarly named paths, ordering
and empty entries retained; cwd/command/stdio unchanged; a missing target entry
rejects the comparison. `git apply --check` passed. The patch has **not** been
applied and no GUI result exists for it.

The earlier plan was to correlate a fresh Studio session and compare removal,
restoration and removal again. None of those runs occurred. The source-backed
key-spelling candidate now takes priority, with all PATH contents preserved.

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

## Temporary logging procedure — source hunks currently removed

The A/B comparison did not safely expose the existing QML carrier, and the
ordinary log did not retain the initialization error. Prepare one subsequent
real GUI launch with the approved `QML_IMPORT_TRACE=1`, `QT_DEBUG_PLUGINS=1`
and appended `qt.webenginecontext.debug=true` logging rule. Inject these only
into the final Houdini child environment, after helper cleanup, before Qt
initialization; the GUI snapshot must confirm their arrival. Do not simply set
QT flags outside Studio and assume they survive the existing cleanup.

The local evidence directory retains the original `one-launch-logging.patch`
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

`QT_FORCE_STDERR_LOGGING=1` in that same temporary child environment requests
stderr routing in Qt's standard handler, without installing a new global
message handler or debugger. It did not produce the needed output in the real
Houdini runs above. Qt 6.8.3 implements this flag in
[`shouldLogToStderr()`](https://github.com/qt/qtbase/blob/v6.8.3/src/corelib/global/qlogging.cpp).
It changes the logging destination, not WebEngine resource paths or Chromium
behavior. Verify it and the three approved diagnostic settings in the actual
GUI snapshot; absent settings or output are an evidence gap, not a pass.

Open only the agreed help page for this diagnostic session, observe the bounded
child-process window, collect relevant initialization errors and the snapshot,
then let the owner normally close the test GUI. Raw diagnostic logs stay in the
private E: evidence/cache directories; publish only reviewed excerpts without
authentication values, complete command lines or unrelated user data. The
completed logging runs and their output gaps are recorded above; none is a fix.

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
