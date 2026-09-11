# R4 Windows release package preparation

Current scope is the [final release approval](final-release-brief.md). The
NET-only package `a5731cf` passed its two fresh Houdini checks; see the separate
[NET-1 validation](r4-net-validation.md). Native steer passed in the
[frozen final candidate](r4-final-candidate.md); the standard-user installed
workflow remains pending. The original packaging and failed integrated
candidate evidence below is preserved, not rewritten as a pass.

Scope: [Release Readiness](release-readiness-brief.md), section G. Branch
`codex/windows-release-package`, draft PR #14. R3 merged independently as PR #13
at `b48ceae` and is now integrated. Target is an unsigned
`0.1.0-rc.1` for Windows 11 x64 and Houdini FX 22.0.368.

## Package and ownership

The offline builder copies tracked production files only, never `.runtime`, native
history, authentication or test scenes. It rejects changed input hashes, unsafe
archive paths and an existing output directory. Inputs are pinned in
`release/windows-inputs.lock.json`: CPython 3.13.15 x64 embeddable, PySide6 Essentials
and Shiboken 6.8.3, and the complete official native Codex 0.153.4 win32-x64 layout.
The ordinary user needs no Python, Node, Git, pip, compilation or global PATH change.

Qt bindings are limited to Core/Gui/Widgets/Network/Svg and the common binding
support, Windows/offscreen platform plugins and the existing PNG/JPEG/WebP image
capability. Houdini receives only Studio `src` through its existing child package
environment; it uses SideFX's own Python/Qt. The private interpreter's `_pth` is
relative to the installed version and supports the existing `-m studio`/MCP helpers.

The per-user Inno installer uses `PrivilegesRequired=lowest`, Windows 11/x64 gates
and an immutable `versions/<version>-<commit>` directory. It retains earlier
versions, replaces the Start menu target, and supplies an uninstaller. It refuses
to overwrite an existing build directory. Packaged Launcher, supervisor and
Houdini Runtime processes hold a Windows mutex that the installer checks. No saved
PID is trusted and no process is killed. A successful process exit releases its
handle. There is no automatic updater.

There is no `[UninstallDelete]`, user-directory scan or cache cleanup. Uninstall
removes its recorded program files and shortcuts; state, native cwd/history,
receipts, attachments and cache-based unsaved scene output are not installer-owned.
Explicit reinstall repairs require closing sessions and uninstalling program files
first. Previously installed versions can be opened through their own Start Studio
entry after closing other Studio sessions.

## Diagnostics and first run

The existing Launcher diagnostics page gains one text action. The user chooses
a new ZIP and sees its contents and destination before export. The worker exports
only version/commit, package checksum status, Windows/Python/Houdini/Codex versions,
account-confirmation booleans and a bounded failure code/stage. Unavailable counts
and timings are null. It reads no raw logs, chat, HOM scripts, token, login URL,
authentication database, environment dump, HIP/HDA or image. It performs no model
request, scene access or upload, and refuses an existing destination file.

Packaged discovery and preflight require the selected executable's Windows version
resource to identify Houdini 22.0.368, without starting a probe. SideFX stores this
as `22,0,0,368`; the actual installed executable was read to verify that mapping.
License/edition confirmation still belongs to the real GUI flow. Codex remains
exactly 0.153.4 and official native login remains authoritative.

## License and build evidence

The package contains Studio, Lucide/Feather, CPython, native Codex, ripgrep, PCRE2,
Ratatui and MSVC notices. Matching complete QtBase, QtSvg, QtImageFormats and
PySide/Shiboken sources accompany the package. Runtime DLLs remain replaceable;
diagnostic checksums report modifications without prohibiting them. Native Codex's
archive matched the registry SHA-512 integrity; Ratatui's crate matched the pinned
Codex Cargo.lock checksum. Microsoft and portable Inno installers had valid
Microsoft/Pyrsys signatures. The MSVC installer was only extracted for its runtime
agreement, never installed. Inno was installed in portable mode under the review
directory. No commercial/signing certificate is claimed by these checks; final
distribution approval reviews the supplied component materials.

Local materials and builds are under `.runtime/reviews/r4` in the coordinating
checkout. The first R3 package successfully ran native Bridge/MCP/Houdini but its
offscreen preview failed because the reduced package omitted `qoffscreen.dll`.
Windows reported Qt6Core `0xc0000409`. The failed package is preserved; the builder
now includes the plugin. The new clean-assets R3 review assembly passed 30 private
Python/Qt fixture captures and the real Houdini package-source check documented in
[R3 validation](r3-validation.md). Retired artwork is excluded from production.

Five focused tests passed: diagnostic redaction and tamper reporting, containment,
no directory scan, a real process-held installer mutex, and rejection of an
incompatible Houdini build. The 17 existing Launcher UI tests and Ruff also passed.
R4 source `1180e73` passed all five CI jobs in run `34333389962`. After integrating
R3, the five release tests, 17 Launcher tests and Ruff passed again. These tests do
not certify a real install/upgrade/uninstall or a new-user authoring flow. The
integrated package check follows below; the complete installed-user gate stays open.

## Integrated candidate and observed blocker

The assembled production-code candidate is `3150c15041ebedca1d266305d7375f30777c25a0`.
It includes R3 and passed all five CI jobs in run `34336404909`. Subsequent changes
record the evidence and release status; they do not change this candidate's code.

| Artifact fact | Observed value |
| --- | --- |
| Build ID | `0.1.0-rc.1-3150c15041eb` |
| Installer | `Big-Chicken-Studio-0.1.0-rc.1-3150c15041eb-win-x64.exe` |
| Installer size | 211,633,966 bytes |
| SHA-256, independently checked against the sidecar | `8badc3c520aabd821e5bb2349a6aec6e96a4d19ba37572dc5b39540d2bb2b0ee` |
| Signature | `NotSigned`; internal candidate, not a public release |
| Manifest | 229 files; all matched, zero missing or changed |
| Build location | R4 worktree `.runtime/安装包 RC 3150c15/` |

The existing package entry `start_release.pyw` ran with its own CPython 3.13.15 and
Qt 6.8.3, without a source path injected into `sys.path`. The process started with
no global PYTHONPATH and only Windows system directories on PATH. Its explicit QA
state/cache stayed under the coordinating checkout's `.runtime/reviews/r4/`.
Native Codex 0.153.4 initialized, read the account as signed out, and the executable
version resource identified Houdini 22.0.368. Only `initialize` and `account/read`
were sent; no login, thread, model or scene request occurred. FTS5 and the private
`-m studio --version` entry passed. Owned native processes closed after the test.

The real Launcher export action, with controlled file-dialog/confirmation answers,
wrote a ZIP containing only `diagnostics.json`. Its 16 fields matched the whitelist,
account confirmation was false, and unavailable timings/counts remained null.
There was no authentication file in the new QA state. The checked file inventory
was read only from this selected package, not from user state or outputs.

The first offscreen-only entry capture lacked a registered font database and drew
squares. It is retained under `integrated-3150c15`, not accepted as visual evidence.
A separate hidden-window check used the actual Windows Qt platform plugin and its
96 installed font families, without registering or changing fonts. The real entry,
account probe and export passed again; Chinese and English text rendered correctly.
That evidence is under `integrated-3150c15-windows-qt`. Neither test installed the
product or used a clean Windows account. Selected screenshots and the exact safe
diagnostic JSON are [directly reviewable](evidence/r4/README.md).

The integrated package also started a dedicated Houdini GUI with a HIP copy, using
the existing isolated native state in place. Session `b3bd5306a57e46b1a176fbc03d5fe997`
confirmed SideFX Python **3.13.10** / Qt **6.8.3**, Studio from the selected package,
and no private Qt directory on Houdini's module path. The live private-Python
`-m studio.mcp` process was observed, and Houdini held the process-lifetime installer
mutex. The original frozen TC3 native history could be exported with its two Turns.
No new model Turn or model-quality experiment ran; the owned GUI/Bridge were closed.

**This native check did not pass overall.** The first Panel reported a history
read failure with `REPLY_UNAVAILABLE`, leaving zero visible messages although the
native source existed. Failed observation receipt `2fe0362051fe4c16885e3f37bd53f955`
and the following state receipt `629b64ca0c0f4bc7aa14bce10ccde44b` preserve it.
A second Panel initially loaded all 98 items, 10 segments, four warnings and three
images. Later both Panels displayed another unavailable-reply notice. The host
also recorded a `QNetworkReply` supplied to an icon event filter as a non-event;
this is an observed correlation, not an established cause. No Qt library, icon
system, network policy or event-loop workaround was changed in response.

This is tracked as **R4-NET-1** in [acceptance issues](acceptance-issues.md).
Previous R3 successful checks remain historical evidence, not proof that this
intermittent path is fixed. R4 stays draft until this blocker and the actual
clean-user installed workflow pass. The preserved package is a review artifact,
not a recommended daily-work version.

## Required release acceptance

The user confirmed on 2026-09-09 that no clean Windows 11 non-administrator account
or other test machine is currently available and asked to finish the remaining
preparation. Do not create a Windows account, copy authentication or treat the
development account as that environment. This is a release gate, not a deferred
exception permitting publication.

The [Chinese RC runbook](rc-acceptance.md) now includes working-time steering.
NET-1 has its separate completed gate. When the environment is available, use the final steer-enabled installer
and record its SHA-256:

1. Install to a path containing spaces and Chinese characters. Prove there is no
   dependency on a development checkout, PYTHONPATH or external Python/Node/Git;
   other installed development software need not be removed. Open from the Start menu.
2. Confirm missing/incompatible Houdini feedback where applicable, then select FX
   22.0.368. Complete official login without importing another installation's account.
3. Open the designated test HIP, grant the conversation's scene permission once,
   request an edit, inspect an image and make a second edit. Check long replies,
   native message ownership and compact activity/error visibility. Successfully add
   guidance through the working Composer in the original native Thread/Turn.
4. Save, close, reopen, resume the original native conversation and make a third
   edit. Record the unchanged native cwd and retained operation receipts/artifacts.
5. Request Stop during staged work. Record Codex and Runtime outcomes independently;
   completed mutations remain and stopped later steps are not replayed.
6. Attempt upgrade while a packaged session is active: the installer must ask for
   normal closure. Then install the next candidate, retaining the earlier version.
   Verify the same state/cwd/history, saved files and unsaved-scene temporary output.
7. Export diagnostics and inspect the ZIP whitelist. Uninstall, verify all user data
   remains, reinstall and resume the same conversation. Preserve failures as failures.

No public release until the three gates in the final approval pass. Publish the same
accepted installer bytes, with their source/builder commits, lock and SHA-256 recorded.
