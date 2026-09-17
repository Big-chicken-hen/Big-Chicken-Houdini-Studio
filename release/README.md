# Windows package build

This directory is for developers. Ordinary users receive the per-user installer.
The [R4 validation record](../docs/r4-validation.md) distinguishes preparation from
the mandatory clean-user release acceptance.

1. Obtain the exact files named by `windows-inputs.lock.json` from their recorded
   official sources into a checkout-local input cache. Verify the listed size and
   SHA-256. For derived license inputs, preserve the specified `archive_member` from
   the archive with the recorded `archive_sha256`; do not download the archive body
   under the license filename. Ratatui uses its crates.io archive, and MSVC uses
   the unchanged English RTF from Microsoft's verified redistributable.
2. Verify Inno's checksum/signature and install the compiler with `/PORTABLE=1
   /CURRENTUSER /VERYSILENT /NORESTART /DIR=<checkout-local compiler directory>`.
   Do not change PATH, create associations or install the MSVC source installer.
3. Commit the candidate and run from a developer Python interpreter:

```powershell
python scripts/build_windows_release.py `
  --inputs .runtime/release-inputs `
  --output .runtime/release-build-01 `
  --iscc '.runtime/inno/ISCC.exe'
```

The builder is offline. It does not use pip, move existing outputs or include test
state. Each assembly creates a new directory, a manifest and an Inno installer
with a separate `.sha256` file. `--source` permits an explicitly selected committed
UI candidate during the independent R3 package review; the manifest records that
source commit separately from the builder commit. Such a review is not R4 acceptance.

For package review, invoke the actual `runtime/python.exe` with `-I -B` and the
source checkout's `scripts/preview_release_ui.py --install-root <package>` harness.
Keep all fixture state/cache and screenshots in checkout `.runtime`. Run native
Houdini against the same package and verify `PySide6.__file__` points to SideFX's
installation while Studio resolves inside the selected package.

Before distribution, review the package's THIRD-PARTY-NOTICES, corresponding source
archives and binary/file inventory, and complete the real installer flow. The
candidate is unsigned; never instruct users to disable Windows protection.

## Current tester handoff

The owner requested one document in the delivery: the current ZIP contains only
`Installer.exe` and the [handoff README](handoff/README.md). Installation, usage,
feedback and installer checksum information are consolidated into that README.
The separate acceptance/feedback/checksum files in `handoff/` remain repository
reference material and are not included in the ZIP. Documentation is versioned
separately from the installer; it does not rebuild or change the application.
The Installer.exe link resolves in the delivered ZIP; the executable is not tracked here.

The owner-selected `发布包` directory contains only the latest ZIP and its checksum.
See [the current delivery record](../docs/r4-package-refresh-20260917.md) for
the README-4 archive identity, package checks and completed temporary-file cleanup.
