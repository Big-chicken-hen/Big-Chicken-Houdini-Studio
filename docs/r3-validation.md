# R3: release UI refinement

Base: R2 merge `2b180da0e4b96125e1e543e7b4123a3779669184`. Branch:
`codex/release-ui-refinement`. Approved scope is [Release Readiness](release-readiness-brief.md),
sections 2 and F, together with the [existing presentation specification](ui-presentation-brief.md).

## Candidate behavior

User messages occupy 86% of the available width and align right, with the existing
neutral elevated surface and label. Codex replies remain left-aligned transparent
content. Turn boundaries have additional spacing. Existing font tokens, pink accent,
native Qt and the 23 approved Lucide resources remain; no icon/brand asset changed.

Ordinary tools fold into contiguous activity segments. An intervening native
message or another Turn ends the segment; grouping never moves tools around an
explanation. Counts describe queries/executions/images, not inferred modified nodes.
Errors, partial/unknown outcomes and recovery warnings remain visible when collapsed.
Images stay on the timeline; available target/frame facts accompany them, while
technical payloads require explicit details. A native tool item's `completed` status
is no longer displayed as if it establishes successful Houdini execution.

Progress reads the existing active operation receipt, at most once per second while
its identity remains active. Callback connection/operation identities are checked.
Stage labels and `2 / 4` come from that receipt's active step and declared steps;
there is no overall task percentage. A completed Codex turn cannot clear active
Houdini work or hide Stop. Current capture and requested Stop have distinct text.

Launcher retains its page/activation/unknown-request model. Known missing-component,
version, process-start, connection and unknown-launch failures have short actionable
messages. Raw diagnostic data remains available. The existing installation-help action
shows user installation guidance rather than developer npm/Python setup instructions.
Private runtime/installer implementation and real-package acceptance belong to R4.

## Development findings and checks

Native offscreen review exposed retired widgets painting until deferred deletion and
width changes using an old text height. Retired cards/controls now hide immediately;
document-size changes schedule a height update with actual viewport chrome included.
Neither change rewrites native source or the R1 reducer. A history regression also
caught refresh collapsing explicitly opened tool details; expansion/detail state is
now preserved across ordinary updates and regrouping.

Evidence under `.runtime/reviews/r3/` is local and explicitly fixture-based:

- `release-previews` preserves the initial overlapping/clipped failures.
- `release-previews-fixed`, `release-previews-wrap-fixed` and
  `release-previews-final` retain the successive layout corrections. Final narrow
  timeline and partial-failure images were opened and visually checked.
- `previews` exercises the existing input/image/approval/unknown cases.
- `launcher-previews` preserves the existing staged Launcher states; the unknown
  account page was opened and checked. More final-source and package review follows.

`scripts/preview_release_ui.py` provides 360/720-pixel timeline, failure, long reply,
progress, Stop and recovery fixtures. `--install-root` imports the selected production
package and records the actual module path; it does not pretend that source previews
are packaged-installation evidence. Before capture it waits for document height to
contain the visible text. Fixture state/cache and images stay beneath the review root.

Targeted checks already run: three R3 UI cases, six R1 projection cases, five history
and race cases, 14 composer cases, 13 Panel cases, 17 Launcher cases and Ruff. The
observed history-details regression was fixed and that affected group passed again.
These are native Qt offscreen checks, not real Houdini or physical input certification.

## Gate still open

The candidate is not ready for R3 merge yet. Real Houdini Panel review, final
candidate CI and screenshots from the assembled production package are still needed.
R4 remains a separate packaging PR; its actual new-user installation/upgrade/uninstall
and full authoring/resume path must pass before public release. R1/R2 are already
merged; frozen TC1/TC2/TC3 model/asset conclusions are unchanged.
