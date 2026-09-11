# R4-HELP-1 — evidence preparation, not a fix

## Decision and current status

The owner authorized the full [Pro review](r4-help-review.md) on 2026-09-11.
[R4-HELP-1](acceptance-issues.md#r4-help-1studio-启动后的-houdini-内置帮助失效)
blocks automatic Ready/merge/Public RC for PR #14. Development startup has an
owner-reproduced failure; native startup of the same Houdini installation is
owner-reported normal. Root cause, introducing commit and payload GUI impact
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

Five focused fake-object safety tests exercise wrong-thread rejection,
embedded/shared-window rejection, failed-QML inspection without engine creation,
existing-engine association/URL sanitization, and a hard subtree bound. These
tests verify diagnostic boundaries only; they are not Houdini GUI evidence.
On 2026-09-11, `scripts/check.py --pattern test_help_inspection.py` passed all
five tests and Ruff. The final script metadata addition also passed the focused
static check; `git diff --check` reported no whitespace errors. The builder's
source allowlist excludes this development script and all tests/docs; the
existing installer and Tester ZIP were not rebuilt or modified.

## First real GUI comparison — wait for owner availability

No GUI or test scene is opened automatically. The owner chooses a safe time,
preserves unsaved work, opens the application and normally closes its windows.
Do not take execution ownership of another active Studio workspace.

1. **A: native.** Use the owner's normally working native entry for the same
   Houdini 22.0.368 EXE. Use the same account/preferences/plugins and unchanged
   Clash configuration. Open the help page using the originally failing entry;
   record that entry in words and capture the help window screenshot manually.
2. With that help pane open, run this one line in Houdini's Python Shell:

   ```python
   import runpy; runpy.run_path(r'E:\Big-Chicken-Houdini-Studio\scripts\inspect_houdini_help.py')['capture']('native')
   ```

3. **B: Studio.** At the agreed safe time, open `E:\Big-Chicken-Houdini-Studio\Studio.exe`
   and the same test scene/help entry. Keep the Panel state recorded. Run:

   ```python
   import runpy; runpy.run_path(r'E:\Big-Chicken-Houdini-Studio\scripts\inspect_houdini_help.py')['capture']('studio')
   ```

4. Compare host EXE/version/preferences, help pane type/URL/entry, actual GUI
   library paths, existing carrier errors and availability. Screenshots confirm
   navigation/body appearance; snapshot `captured` never means help passed.
   If multiple panes are reported, supply `pane_name='exact name'`; do not
   automatically close panes or choose an unrelated window.

If the initialization failure is no longer observable, prepare one subsequent
real GUI launch with the approved `QML_IMPORT_TRACE=1`, `QT_DEBUG_PLUGINS=1`
and appended `qt.webenginecontext.debug=true` logging rule. Inject these only
into that final Houdini child environment, after helper cleanup, before Qt
initialization; the GUI snapshot must confirm their arrival. Do not simply set
QT flags outside Studio and assume they survive the existing cleanup. This
conditional logging launch is not yet wired or run.

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
