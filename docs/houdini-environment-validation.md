# Houdini user search-path compatibility correction

## Current delivery: 0.1.0-rc.1-8af563981e73

Source and builder: `8af563981e73995825f0e35bd6e1d11dd74f7c64`.
This includes environment fix `3d956f7`, output guidance `8af5639` and the
previously committed persistent artwork/cards/native caption/taskbar correction
`df008b1`. All five [source-candidate CI jobs](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34554361151)
passed. The environment-only commit's five CI jobs also passed.

The assembled payload's **244/244** manifest entries matched. Its bundled Python
3.13.15 repeated the real H22 three-HDA comparison successfully. The actual
packaged `Studio.exe` opened a responding Launcher with isolated state, initialized
bundled Codex, accepted normal close and exited with code 0. Its entry shim also
exited with code 0. This smoke did not install the product, log in or launch a
real Houdini GUI. The intermediate environment-only smoke closed normally but
its first fixture did not retain a process handle, so its exit code is unavailable;
that limited observation remains recorded separately.

The current five-file ZIP is in the owner's E: `发布包` directory. Handoff revision
is `README-2`. Every ZIP member matched its source, including the installer and
four versioned documents, and all 17 relative handoff links passed. Installer:
216139477 bytes, SHA-256
`429a1a7d7958bea8a071b8269c4a8670bda5f3e678730fe4570308d847a18b3e`.
ZIP: 215690746 bytes, SHA-256
`b74b3736a284309b13944a25da6639906c437e60cce2defaa52ab622bc0f8bc7`.
Package
`release_acceptance` remains `pending`; real standard-user installed acceptance
and fresh model compliance with the corrected output instructions remain untested.

After full ZIP readback, the previous delivery ZIP/checksum and this task's two
unpacked builds/duplicate installers were removed. Both clean temporary source
worktrees were removed through Git. Only the current ZIP and checksum remain in
`发布包`. Manifests, checksums, fixture assets and reports remain in the bounded E:
review directory; those reports' old build paths do not imply live binaries.
Authentication, native workspaces/history, user output files and the pre-existing
`docs/authoring-results.md` change were preserved. No Owner installation occurred.

## Environment correction

The owner's independent review reproduced dropped search paths in installed
candidate `042c66b9be95`. The owner authorized a bounded fix, commit and new ZIP
on 2026-09-11. This replaces that candidate for delivery only after the new build
is verified; it does not constitute standard-user or real GUI authoring acceptance.

The installed entry previously called `helper_environment()` before opening the
Launcher, losing the inherited paths before host creation. `child_environment()`
then replaced `HOUDINI_PACKAGE_DIR` with Studio's directory. Restoring only
`HOUDINI_USER_PREF_DIR` preserved preferences but did not preserve plugin discovery.

`launcher_environment()` now carries a narrow list in normal user mode:
`HOUDINI_PATH`, `HOUDINI_PACKAGE_DIR`, `HOUDINI_OTLSCAN_PATH`, `HOUDINI_OTL_PATH`,
`HOUDINI_OPLIBRARIES_PATH` and `HOUDINI_DSO_PATH`. Values, user ordering, variables,
spaces and `&` remain literal. Host creation appends Studio's package directory
without duplicating its exact entry. `helper_environment()` still strips these
paths, and explicit isolated tests do not inherit them. Existing Python, Qt, HFS,
old integration and credential cleanup, temporary storage, proxy handling and
fresh launcher-session credentials remain unchanged. No global environment,
Houdini installation, user preference or plugin file is edited.

The selected variables and package handling follow SideFX's
[environment reference](https://www.sidefx.com/docs/houdini/ref/env.html) and
[package search rules](https://www.sidefx.com/docs/houdini/ref/plugins.html).
Other Houdini variables remain outside this bounded inheritance contract.

## Validation

- Five focused regression cases cover direct host creation, the real installed
  bootstrap with a substituted UI entry, development bootstrap, explicit test
  isolation and a reconstructed child. Before the fix four cases failed on lost
  paths and the isolation case passed. Afterward all five passed; the combined
  environment/storage/launcher set passed **24 tests**.
- Same Windows host and same `Houdini 22.0.368/bin/hython.exe`, with three real
  fixture HDAs in separate extra directories and a package marker:

| Launch environment | HOUDINI_PATH HDA | OTLSCAN HDA | Package HDA | Studio path |
| --- | --- | --- | --- | --- |
| Native baseline | loaded, 8 points | loaded, 8 points | loaded, 8 points | absent |
| Old installed bootstrap/host environment | not discovered | not discovered | not discovered | present |
| Fixed installed bootstrap/host environment | loaded, 8 points | loaded, 8 points | loaded, 8 points | present |

All discovered test nodes cooked with zero errors; each process exited with code
0. Paths contain spaces and Chinese characters. Original user data was not used:
all assets, preferences, logs and comparison scripts stay under
`.runtime/maintenance/houdini-environment-20260911`. The test fixture's initial
failure accidentally displayed the development error dialog; the test now
substitutes that dialog and checks the environment outside the bootstrap's error
handler. No Setup or reinstallation was needed.

These are actual headless Houdini discovery/cook checks, not a Houdini GUI,
official-login, arbitrary third-party binary-plugin or standard-user install
acceptance. `release_acceptance` remains `pending`.

## Owner-reported VEX export location

The owner identified `heightfield_distort_generated_b213b651.vfl` in a native
workspace's `work` directory. Read-only inspection of that operation's native
tool call showed a literal workspace path passed to `saveCookCodeToFile()`;
`output_path()` was not used. The Runtime's file facts correctly identified the
saved HIP. The existing resolver still selects
`$HIP/BigChickenStudio/<HIP stem>/{renders,exports,assets}` for new default outputs.

The scene instructions and execute-tool description now explicitly classify
generated source exports, including inspection VEX, as scene outputs and direct
the model to use the existing helper. Explicit user destinations and existing
node outputs retain priority. No path interception, script rewriting, cwd/history
move, existing-file migration or output-resolver change is introduced. Existing
misplaced files stay available to old conversation references. This corrects the
model's instructions; it is not a claim that arbitrary Python writes are sandboxed
or that a fresh real model conversation has already demonstrated compliance.
All four existing saved-HIP/Save As/explicit-output resolver tests passed unchanged.
