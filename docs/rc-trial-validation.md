# RC trial handover — 2026-09-10

## Single EXE delivery follow-up

The Owner requested one `Studio.exe` entry instead of VBS/Python alternatives,
and delivery files under the selected development project rather than a new
Owner installation. The Windows Framework shim launches the existing private
Python runtime; the installed Start Menu shortcut targets the EXE. The bootstrap
is internal to `runtime`. Source setup builds the same EXE; VBS entries are retired.
There are no launcher/Panel layout, networking, consent or execution changes.

Local validation: Ruff passed and seven focused release tests passed, including
executing the compiled EXE in development and packaged layouts with Chinese and
space-containing paths, a different working directory and a stale inherited root.
The current development launcher opened with a visible native window and pinned
Codex 0.153.4 available. This is not installed-package or standard-user acceptance.
The original f0fce6e installer below stays preserved; the changed entry requires
a separately identified build. External testing and optional polish are deferred
by the Owner. Private path inventories and cleanup records remain local.

The [Pro audit](rc-trial-review.md) and [direct user correction](rc-trial-scope.md)
authorize daily Owner trials and distribution to named testers. **PR #14 remains
Draft: independent standard-user acceptance and final Pro Go are still required.**
No public release or external message was sent.

## Frozen installer

| Field | Value |
| --- | --- |
| Source / builder | `f0fce6e5fd2bd111e779b2e336bd82b5b0491bf3` |
| Build ID | `0.1.0-rc.1-f0fce6e5fd2b` |
| Installer | `Big-Chicken-Studio-0.1.0-rc.1-f0fce6e5fd2b-win-x64.exe` |
| SHA-256 | `95915fad026c7ba36d0df3ad8befdcf8543e074a5c32f3f6ac32f228545ee9c2` |
| Bytes / manifest files | 211657859 / 232 |
| Runtime | Private CPython 3.13.15, PySide6 / Qt 6.8.3, Codex 0.153.4 |
| Lock | `release/windows-inputs.lock.json` at the source; copied as `build-inputs.json` |
| Candidate CI | All five jobs passed, [34461330525](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34461330525) |
| Build directory | R4 worktree `.runtime/rc-trial-f0fce6e/` |

`ce388a4` implements the bounded policy/identity changes and passed all five jobs
in [34460251580](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34460251580).
Its real regression revealed a missing displayed Codex version. The native
initialize response used `Codex Desktop/0.153.4 (...) (big_chicken_studio; 0.1.0)`
because the parent supplied an originator override. `f0fce6e` reads the leading
native version independently of that name, never the Studio client suffix.
This final commit changes only identity parsing and its focused test.

The former `991cbce` frozen installer, `ce388a4`, prior NET pass and failed
packages remain preserved. Later documentation commits do not replace the above
source, builder, bytes or checksum. No rebuild is needed for external instructions.

## Bounded product changes and checks

- One shared Houdini classifier replaces exact-build rejection in Onboarding and
  preflight. The known FX combination is Validated; supported trial candidates
  are Untested and require a request/path/version-bound confirmation. Later
  22.x minors are not automatically selected. Unknown edition is not guessed
  from an executable name or Commercial license. Missing integration and other
  majors remain explicit rejections. A nonstandard unresolved installation
  layout is Unknown and cannot launch.
- Runtime records actual application/license/Python/Qt/Panel/module facts once
  at normal UI-ready registration. Health only copies that cache. A failed fact
  query is Unknown; a confirmed absent/wrong Panel registration is different.
  No model context, operation queue, receipts or HOM policy changed.
- Normal installed selection uses bundled Codex. Stale automatic discovery and
  PATH do not take over. Explicit external selection must pass exact 0.153.4 and
  initialize; failure has the existing explicit restore-bundle action, no hidden
  fallback or updater.
- Existing Launcher/Panel details show build, source, roots and selected versus
  connected host. Diagnostics adds whitelisted scalars, not paths, conversations,
  credentials or environment dumps. Approved layout, native Qt and icons remain.
- Focused classifier/selection, request-bound confirmation, UI details, host
  caching/Unknown faults, runtime startup cleanup and Bridge identity tests passed.
  Ruff and diff checks passed; final candidate CI covers the existing backend/UI
  checks. Adjacent Houdini versions were not launched or certified.

## Owner installation and network facts

The Owner machine is **Windows 11 Pro 23H2 x64, build 22631.6060**, with an
Administrators member and elevated developer token. This is not a standard-user
environment. Read-only inventory found no prior installed Studio shortcut,
active Studio session or duplicate user Houdini package to remove. No global
Python/Clash settings, user packages, old state, authentication or native cwd moved.

The per-user installer completed with exit 0. The identity-only update also
installed with exit 0 and retained the preceding version directory. The sole
recommended daily entry is **Start menu → Big-Chicken Houdini Studio** and now
targets `versions/0.1.0-rc.1-f0fce6e5fd2b/runtime/pythonw.exe` with its own
`start_release.pyw`. The ordinary Windows shell enumerated this Start menu entry.
The launched Owner process uses the existing formal state/cache roots under
`LOCALAPPDATA/BigChickenStudio`, with `CODEX_HOME` under formal state.

Codex desktop child-process observations include Windows package redirection to
an OpenAI.Codex LocalCache physical program path; shortcut/CIM paths and queried
physical executable/module paths are recorded separately in the local Owner
report. This is not silently represented as a different release. Source/build,
bundled executable and actual loaded Panel agree. No unobserved path is declared
to have been migrated or deleted.

**Clash remains on and required by the user. Each tester keeps their own working
configuration/port. No Clash-off or no-Clash environment B test was performed.**
The read-only process chain confirmed native `respect_system_proxy` on login and
session Codex. Internal requests were additionally checked with unavailable
upper/lowercase proxy variables (including ALL_PROXY, without NO_PROXY exceptions)
in test processes only, using local fixtures and test tokens. Both internal HTTP
paths stayed direct. There was no global proxy edit or fixed product proxy port.

The isolated native account/workspace was accessed in place. Its actual native
Codex tree also contains an external Node child in a previously enabled plugin
directory. This is recorded honestly; this reused development state cannot prove
a clean user's lack of optional external plugin dependencies. Studio's own MCP
uses the installed private Python. Standard-user portability remains its own gate.

## Actual installed regression

Full private records are in the coordination checkout under
`.runtime/reviews/rc-handover/`; [published scalar results](evidence/r4-trial/results.json)
omit full process environments, paths, credentials and native message bodies.

1. Installed `ce388a4` used production Onboarding, initialize/account verification,
   preflight and supervisor. A fresh roof copy explicitly retained workspace
   `6e91a54f79264b68a58b4791818d4ae7` and Thread
   `01a08a61-068e-7450-a572-4b6bce305db4`; its unassociated copy used the existing
   explicit legacy workspace entrance, without copying or rebinding history.
2. The real registered Panel sent one modification and one steer through its
   normal Composer and consent controls. Both inputs appeared once in Turn
   `01a08aa6-77cb-72c3-87f6-130f89929820`; GPT-6-Astra/native default completed in
   about 51 seconds. A native `Reconnecting... 2/5` notice appeared and remained
   visible after completion; it is preserved, not described as zero network notices.
3. Actual roof thickness became **0.18 m**; slope remained **35°**, eaves **0.25 m**.
   The final model HOM changes only the existing thickness parameter and reports
   unchanged other parameters/nodes/objects. Explicit queued verification found
   no roof node errors. Eleven complete Panel messages, copy text and rendered
   text matched native history. Save As wrote a new acceptance HIP; the frozen
   original HIP stayed byte-identical.
4. Installed **final `f0fce6e`** opened that saved HIP through ordinary
   `launch_target`/SceneCatalog. Actual registration confirmed Houdini FX
   22.0.368, Commercial, Python 3.13.10, PySide6/Qt 6.8.3 and package Panel source.
   The same workspace, Thread and native cwd remained; all eleven messages and
   the 35° / 0.25 m / 0.18 m parameters survived a fresh GUI load/cook. Geometry
   had 12 points/10 faces and no node errors. Details correctly showed the final
   build and **Bundled / 0.153.4**. No new model benchmark or turn ran in this
   identity-only follow-up.
5. A final-package diagnostic export contained only `diagnostics.json`; integrity
   matched all **232** manifest files with zero changed/missing files. This checks
   package identity and whitelist structure; it is not the external user's GUI
   export or account acceptance. Final native-window shutdown returned **0**.

### Preserved shutdown fault for Pro review

The first run's test-only Python QTimer callback called
`hou.exit(exit_code=0, suppress_save_prompt=True)` after Save As. Its operation
receipt finished, then Houdini PID 25828 caught signal 11 and exited **139**.
The local crash log shows H22 interpreter/GIL and compiled-code/UI destruction,
with `Py_Exit`, `UT_Exit` and QTimer lower in the stack. A completed operation
receipt therefore does not prove clean application shutdown.

The final fresh process instead used the existing native window `close()` slot,
with no Python exit callback and no suppressed unsaved-work prompt; it exited
**0**. The saved scene/history remained usable after the earlier crash. This
distinguishes the observed exit routes but does **not** prove a unique root cause
or claim every shutdown path fixed. No product/Houdini shutdown code was changed.
The failure, script, crash log and later pass remain together for Pro; ordinary
human close/reopen remains part of the standard-user gate.

## Tester handover and remaining gate

The current local **Big-Chicken Studio 测试包** contains exactly:
`Installer.exe`, `Installer.exe.sha256`, `开始使用.md`, `测试结果.md`.
The copied installer checksum matches the frozen candidate; only its delivery
filename changes. The short Chinese documents use the final build ID, require
the tester's own Clash/official account and provide ten PASS/FAIL/BLOCKED rows.
No source checkout, credentials, extra tools or legacy user data are included.

Independent Windows 11 standard-user installation/login/authoring/steer/images,
Save As/resume, Stop, diagnostics, active-session upgrade protection,
upgrade/uninstall/reinstall and data retention remain **unverified**. An Untested
Houdini experiment cannot replace the declared validated-combination gate.
Keep #14 Draft and obtain final Pro Go before merge or public release; do not
expand tools, UI, model policy or network configuration while waiting.
