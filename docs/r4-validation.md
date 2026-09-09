# R4 Windows release package preparation

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

## Required release acceptance

The user confirmed on 2026-09-09 that no clean Windows 11 non-administrator account
or other test machine is currently available and asked to finish the remaining
preparation. Do not create a Windows account, copy authentication or treat the
development account as that environment. This is a release gate, not a deferred
exception permitting publication.

When that environment is available, use the actual installer and record its SHA-256:

1. Install to a path containing spaces and Chinese characters, without a development
   checkout, Studio Python environment or global PYTHONPATH. Open from the Start menu.
2. Confirm missing/incompatible Houdini feedback where applicable, then select FX
   22.0.368. Complete official login without importing another installation's account.
3. Open the designated test HIP, grant the conversation's scene permission once,
   request an edit, inspect an image and make a second edit. Check long replies,
   native message ownership and compact activity/error visibility.
4. Save, close, reopen, resume the original native conversation and make a third
   edit. Record the unchanged native cwd and retained operation receipts/artifacts.
5. Request Stop during staged work. Record Codex and Runtime outcomes independently;
   completed mutations remain and stopped later steps are not replayed.
6. Attempt upgrade while a packaged session is active: the installer must ask for
   normal closure. Then install the next candidate, retaining the earlier version.
   Verify the same state/cwd/history, saved files and unsaved-scene temporary output.
7. Export diagnostics and inspect the ZIP whitelist. Uninstall, verify all user data
   remains, reinstall and resume the same conversation. Preserve failures as failures.

No public release until this full flow and outstanding distribution review pass.
