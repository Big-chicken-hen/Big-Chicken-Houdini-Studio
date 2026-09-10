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
Five-file ZIP: 216142270 bytes, SHA-256
`6929b5310f5602a40a42dedfa027091438404e79c5469f8a749046f65fc2f077`.
Its exact five entries and all reconstructed bytes matched on full ZIP readback:
`Installer.exe`, `SHA256.txt`, `开始使用.txt`, `测试步骤.txt`,
`出现问题怎么办.txt`. The instructions now use selection followed by Launch and
the flat Settings/Diagnostics toolbar. The previous 4e9db5d ZIP and then-current
entry note are archived; the original release remains preserved. No installation
was performed on the owner's development machine. Local delivery evidence is in
`.runtime/maintenance/node-flow-delivery-20260910`.

The owner has deferred real official-login/selection/Launch/Houdini preference confirmation.
Standard-user installed acceptance also remains untested. Neither offscreen
screenshots nor a Launcher-only smoke test replace those real workflow gates;
PR #14 stays Draft.
