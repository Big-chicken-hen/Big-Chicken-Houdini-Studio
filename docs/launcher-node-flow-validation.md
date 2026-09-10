# Fixed node-flow Launcher candidate

This implements [the Pro-approved topology](launcher-node-flow-brief.md) and the
owner's subsequent supplied-artwork, white/blue palette and portrait EXE icon
correction. The local native Qt Launcher is the only presentation being changed.

Account, Empty/Open/Recent and Launch are five fixed nodes with measured Bézier
connections. Scene selection is local; only Launch creates a request and enters
existing preparation/admission. Narrow windows retain branch topology, native
vertical scrolling and keyboard focus. The existing request identity, unknown
status query, single-request Untested confirmation, account generation guards and
runtime-confirmed minimization remain authoritative.

The explicitly requested `redesign-existing-projects` Skill was used to review
contrast, hierarchy, spacing and interaction within that specification. The
supplied background stays unchanged; its displayed opacity is 58%, with a cool
heading veil and bottom fade. Unselected node surfaces are 87% opaque, selection
uses a solid pale blue surface, and all text and controls stay opaque. Menus,
secondary pages and Lucide tints use the same local light palette. The Panel's
shared theme is unchanged. The image is loaded once and its scaled copy is cached
until viewport dimensions change.

Changa One Italic is bundled with its OFL notice. The user-authorized girl
portrait is embedded in Studio.exe, used by the Qt Launcher window and installer,
and encoded at seven Windows icon sizes. Functional icons still use the approved
Lucide SVG subset; no replacement geometry or OS fallback was introduced.

Local checks on 2026-09-10:

- 41 targeted Launcher/UI/entry tests passed, including late selection races,
  local selection without workspace creation, deleted HIP rejection, Open cancel,
  unknown request query without duplicate launch, Untested correlation and
  generation/close/minimize boundaries.
- Ruff passed for the affected UI, preview, icon builder and tests.
- Actual Qt offscreen images at 100% and 150% cover ready, selected sources,
  signed out/waiting, missing dependencies, Untested, launch, unknown, compact
  scrolling and Recent popup. Reports check loaded Changa Italic, measured node
  anchors, no wires through node content and no horizontal overflow. Wide, popup
  and compact unknown/Launch images were visually reviewed.
- Preview evidence stays in `.runtime/previews/launcher/white-blue-final-100` and
  `white-blue-150`. These use isolated fixtures, not real accounts or Houdini.

Candidate `0.1.0-rc.1-042c66b9be95` uses source and builder
`042c66b9be95d6fdeb48fb1367734f93e6b66295`. All five
[candidate CI jobs](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34487149119)
passed. All 242 manifest entries and the pinned font/license resource hashes
matched. The actual packaged EXE opened a visible responding Launcher with
isolated state and initialized bundled Codex. Its EXE and installer expose the
girl portrait as their native Windows icon.

Preserved close observation: closing immediately during the first initialization
left the process alive beyond the 15-second observation window; it exited before
the next read, without forced termination. A separate initialized-window check
accepted normal close and its process ended in 12.3 seconds. The process exit code
was unavailable in that read. This is a limited Launcher smoke check, not a claim
of instantaneous teardown; no backend or shutdown repair was added.

Installer: 216136916 bytes, SHA-256
`a7e5409d6963411f5704803d658dc5b0a437fb7af45abb9b81f9f4760930468e`.
Current five-file ZIP, documentation revision `README-1`: 216142602 bytes, SHA-256
`82aafc7c0c27d7b7ee6e24a206a81272d3d530aab9dda8b8313674ecb5401331`.
Its entries are `Installer.exe`, `README.md`, `验收指南.md`, `问题反馈.md` and
`SHA256.txt`. Full ZIP readback verified every document and the unchanged installer
hash above; 17 relative document/section links passed. The exact document sources
are versioned in [release/handoff](../release/handoff/README.md). The owner's
README request changed only the outer handoff documents, not the installed
application or its build identity. The previous TXT-wrapper hash
`6929b5310f5602a40a42dedfa027091438404e79c5469f8a749046f65fc2f077` is historical.

The owner subsequently requested removal of unused project artifacts and all old
release ZIPs. The completed cleanup removed 31 verified targets totaling
3,973,476,803 bytes: disposable build payloads, duplicate installers, two clean
temporary build worktrees, ZIP readback copies, obsolete previews/scripts and
bytecode caches. The current ZIP and checksum moved into the ignored `发布包`
directory. Previous ZIPs and duplicate installer files are no longer retained in
that project. Small manifests, checksums and written evidence remain available;
historical paths do not imply those binaries still exist. Runtime dependencies,
credentials, history, workspaces, scenes, receipts, preferences, current previews,
backups and historical worktrees containing changes or durable data were preserved.
The pre-existing `docs/authoring-results.md` change was not modified or committed.

No installation was performed on the owner's development machine. Local evidence
is in `.runtime/maintenance/node-flow-delivery-20260910`,
`.runtime/maintenance/e-project-cleanup-20260910` and
`.runtime/maintenance/readme-delivery-20260910`. The initial forced-delete command
was rejected before execution; the cleanup completed with the review tool's
recommended non-force deletion and normal Git worktree removal.

The owner has deferred real official-login/selection/Launch/Houdini preference confirmation.
Standard-user installed acceptance also remains untested. Neither offscreen
screenshots nor a Launcher-only smoke test replace those real workflow gates;
PR #14 stays Draft.
