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

Candidate build, CI and delivery results are recorded after packaging. The owner
has deferred real official-login/selection/Launch/Houdini preference confirmation.
Standard-user installed acceptance also remains untested. Neither offscreen
screenshots nor a Launcher-only smoke test replace those real workflow gates;
PR #14 stays Draft.
