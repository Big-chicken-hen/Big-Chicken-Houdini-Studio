# Big-Chicken Houdini Studio runtime notices

This is an unsigned internal release candidate. Release acceptance is pending.
Houdini and account credentials are not distributed. Studio source is Apache-2.0;
its LICENSE is at the installation root. Only the 23 approved Lucide 0.468.0 SVG
files are distributed, with their original Lucide/Feather licenses beside them.

The Launcher hero uses the unmodified Changa One Italic face by Eduardo Tunni,
under SIL Open Font License 1.1 (Reserved Font Name: Changa). Only the italic
face is bundled; it is loaded locally by the Launcher, never installed as a
system font. Its unchanged OFL.txt, official Google Fonts metadata and pinned
revision/file hashes accompany it under src/studio/ui/assets/changa-one.

CPython 3.13.15 is the official Windows x64 embeddable distribution, unmodified
apart from its explicit module search path. Its license and bundled component
notices are in PYTHON-LICENSE.txt. Source:
https://www.python.org/downloads/release/python-31315/

PySide6 Essentials and Shiboken6 are pinned to 6.8.3. Studio uses the LGPLv3
option. The installed Qt binding modules are Core, Gui, Widgets, Network and Svg,
with the Windows platform and selected image plugins. Qt is dynamically linked;
users may replace the compatible Qt/PySide libraries and modify/relink Studio.
Reverse engineering for debugging those modifications is not prohibited.
Matching complete QtBase, QtSvg, QtImageFormats and PySide/Shiboken source archives, including
their licenses, third-party attributions and build instructions, accompany this
package under licenses/sources. The Python wheel metadata is preserved. The
commercial-license text in the upstream wheel does not imply a commercial license
was purchased or substitute for the LGPLv3 terms included with the sources.

Native Codex 0.153.4 uses the complete official win32-x64 npm binary layout,
including its command runner, code mode host, sandbox setup helper and ripgrep.
The original Apache-2.0 license and NOTICE are in CODEX-LICENSE and CODEX-NOTICE.
The exact registry source, integrity-checked archive and input SHA-256 values are
recorded in build-inputs.json. No account or another Codex installation is copied.

Additional native notices are supplied for ripgrep 15.2.0 (MIT/Unlicense), PCRE2
10.45 and Ratatui 0.30.2. The latter's crate checksum matches the pinned Codex
Cargo.lock. MSVC-RUNTIME-LICENSE.rtf is the unchanged English runtime agreement
extracted from Microsoft's signature-verified Visual C++ 2015-2022 Redistributable;
its archive and member hashes are recorded. The redistributable installer is a
build-time license source; Studio neither runs it nor replaces a system runtime.

The binary/file inventory and corresponding notices are available for the final
distribution review. This internal candidate does not claim that public release
approval or certification is complete.
Windows 11 x64 / Houdini FX 22.0.368 is the target, not a completed certification.
