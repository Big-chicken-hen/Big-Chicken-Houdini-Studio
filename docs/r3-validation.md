# R3: release UI refinement

Base: R2 merge `2b180da0e4b96125e1e543e7b4123a3779669184`. Branch:
`codex/release-ui-refinement`. Approved scope is [Release Readiness](release-readiness-brief.md),
sections 2 and F, together with the [existing presentation specification](ui-presentation-brief.md).

## Candidate behavior

User messages occupy 86% of the available width and align right, with the existing
neutral elevated surface and label. Codex replies remain left-aligned transparent
content. Turn boundaries have additional spacing. Existing font tokens, pink accent,
native Qt and the 23 approved Lucide resources remain; no icon/brand asset changed.

Ordinary tools fold into contiguous activity segments. An intervening visible
explanation or another Turn ends the segment; grouping never moves tools around an
explanation. Empty native reasoning summaries stay in the projection but contribute
no blank header or artificial activity boundary. A coalesced first summary update
restores its card and separates the activities; recovery warnings remain visible.
Counts describe queries/executions/images, not inferred modified nodes.
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

Targeted checks already run: five R3 UI cases, six R1 projection cases, five history
and race cases, 14 composer cases, 13 Panel cases, 17 Launcher cases and Ruff. The
observed history-details regression was fixed and that affected group passed again.
These are native Qt offscreen checks, not real Houdini or physical input certification.

## Real-host findings and final-source evidence

The real host is Houdini 22.0.368, using its own Python **3.13.10** and Qt 6.8.3.
The independent package process uses CPython **3.13.15** and Qt 6.8.3. Module paths
were recorded, confirming that Houdini did not import the package's private Qt.
All scene activity used copies and the existing bounded main-thread operation queue.
No new model-quality experiment was run.

Real testing exposed three host-specific paths that offscreen checks did not prove:

- A repeated document-size invalidation kept scheduling zero timers after the
  width/height had stabilized. In session `b1b6b7b3356c45a09dc25018d123961b`, the
  long reply's fit count grew from 189 to 4,111 across 16 samples and idle-dispatched
  HOM stopped progressing. `fit_text` now only changes document width and widget
  height when they differ. A new real session stayed at 13 calls across the samples;
  the subsequent queued UI read started after 0.056 seconds. Failed runs are kept.
- Houdini renamed the Panel root to `QT_Feel`, breaking the prior object-name CSS
  selector. An explicit local style-root property now preserves the approved theme
  without changing the host's application style or palette.
- A newly added broad `viewportEvent` override coincided with a native reply wrapper
  becoming invalid before `/events` completion while the 98-item TC3 history loaded.
  It repeated on `4c36085`; a trial owned-slot change did not fix it and was reverted.
  Removing that override and using existing resize/scroll-range signals eliminated
  it in the same source and package history checks. Session
  `7f35438dfdd8488e9b0303a8162c29b8` recorded 30 seconds without an invalid reply or
  failure notice. This documents the R3 regression, not a claim about the unique
  cause of the user's older PANEL-1 report.

Stop acknowledgment now immediately retains the confirmed request fact while the
next state read is pending. Runtime completion still requires its receipt/health;
acknowledgment never asserts that an already running HOM step stopped immediately.

Source `64343e6e29fd6b7007defe2197dbc5fb2c58e529` is the final production-code candidate.
Later record/image changes do not alter that code. It passed CI run `34332099366`
(all five jobs), following the focused checks above. An earlier Windows 3.13 CI run
timed out in the existing eight-second supervisor-startup fixture; the ownership
test was not weakened, and the subsequent candidate runs passed it.

`verify_release_panel.py` compared seven real views and **56 user/assistant items**
against fresh native exports: identity, canonical source, copy source, independent
Qt Markdown plain-text rendering, recovery state and disabled inner scrolling all
matched. It includes A/B/A and the 3,310-character reply with `R1_A2_END`, plus the
original TC3 history. Both 360- and 540-pixel real views were checked.

The final package history session `0ba7e188510b47c4bebb6b55e50f9042` displayed all 98
native items through the projection, with 28 empty reasoning cards hidden and **10
activity segments**. All four original error/partial warnings stayed visible and
all three available native images decoded. It remained connected, with no failure
notice or Python Panel script error. The original asset-quality conclusions remain
unchanged; reading its history is not another authoring success.

Real staged QA operation `a6bf100af79a46c9899a542d86e5d42e` displayed receipt-derived
`2 / 4` and used the existing visible Stop control. The receipt ended `cancelled`
with `mutation_outcome=partial`; earlier modifications remain and the output step
was not run. No script was replayed. The native Codex turn was already completed,
demonstrating that active Runtime work still controls the work/Stop display. This
was programmatic Qt interaction in a real Houdini GUI, not physical mouse/DPI testing.
An immediate observer grab could precede Qt's pending layout pass. A separate
settled-layout check in session `d2baa36476624bd593b32e84e93a4d52` confirmed the
two-line stage label occupied y=812..850 within the 858-pixel native Panel; the
Stop control remained visible. It activated layout only, without pumping Qt events
inside HOM or changing the Runtime scheduler. The earlier timed grabs are retained.

## Production-package screenshot review

R4's independent builder assembled the same committed R3 source with private Python,
Qt and native Codex. Final offscreen evidence under `.runtime/reviews/r3/` uses that
package's actual modules and interpreter, with explicit test state/cache:

- `release-review`: 12 narrow/normal timeline, partial failure, long reply, progress,
  Stop and recovery PNGs. The long view visibly includes `R3_END`.
- `standard-review`: six approval, unknown and attachment PNGs at 360/720 pixels.
- `launcher-review`: 12 existing staged Launcher cases, including unknown launch.

The reduced package initially omitted the offscreen Qt platform plugin and could
not produce these images. That failed artifact is preserved. The builder now
includes it; the above captures passed. The final assembly also excludes the
retired artwork from production, preserving it only as an explicitly permitted
source image-decode fixture. See R4's separate package record for ownership checks.

Selected images are committed for direct review in
[the screenshot record](evidence/r3/README.md), rather than relying on an inaccessible
CI archive. Native and fixture images are labeled separately. Fonts, pink tokens,
page structure, approved icon geometry and the R1 reducer remain unchanged.

R3's source/host/package UI checks are complete; merge requires the final record
commit's CI to pass. R4 is still a separate draft: the user has no clean Windows 11
non-administrator environment at present. Actual install/upgrade/uninstall and the
full login/edit/image/save/reopen/resume path must pass before its merge/public
release. This UI review does not waive that gate or certify cross-monitor input.

## Subsequent integrated-package finding

R3 merged as PR #13 at `b48ceae` after final record `419bb52` passed all five CI
jobs (`34335158148`). On 2026-09-09, the integrated R4 package `3150c15` reproduced
an intermittent `REPLY_UNAVAILABLE` during real Houdini history loading and later
polling. Successful R3 runs above remain their actual observed results; removal
of the viewport override is not proof of the complete cause or a universal fix.
The new failed receipts and native screenshot are recorded as
[R4-NET-1](acceptance-issues.md). That defect blocks final package acceptance and
publication; no speculative network/Qt fix was folded into the packaging PR.
