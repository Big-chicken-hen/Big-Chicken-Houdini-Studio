# TC-2 technical validation

Status on 2026-09-08: implementation and the required local technical checks are
complete. Technical merge additionally requires the final candidate's CI. Model
benefit remains **unverified**; [TC1-A1 and TC2-A1](deferred-acceptance.md) are both
pending isolated official login. No natural-language model task ran during these
checks. The governing decision is [the latest Pro approval](tc2-brief.md).

## Scope and source

Base: TC-1 merge `c409c88be6c4b75a9cf4c5167a78187bf2812462`. TC-1's identifier
fix is already in #6 and is not resubmitted as TC-2. Implementation is `3ce11cb`,
with capture restoration corrections in `ae1f093` and `ff11a0b`. The final PR also
includes the fixture, evidence extraction and this validation record.

- `observe_after` uses the existing views, at most 16, resolved after the script.
  Original `observe` remains strict before/after inspection of existing targets.
- Completed mutation, checks, observations and result conversion remain distinct.
  Partial diagnostics are restricted to node/children/parameter metadata; parameter
  values, geometry and checks are skipped. No automatic repair, cook or replay.
- Review capture accepts 1–8 explicit SOP/OBJ targets or execution-time node selection,
  and current/front/right/top/three-quarter views. Target frame precedes bounds reads.
- Existing seven tools, queue, ledger, artifact read limits and UI remain intact.
  Capture targets frame the existing viewport; they do not isolate or hide assets.

## Focused source checks

The combined execute/capture/result/reliability selection passed **60 tests**:
`test_tc2_feedback.py`, `test_tc2_capture.py`, `test_tc1_results.py`,
`test_operations.py` and `test_capture.py`. Raw output is
`.runtime/reviews/tc2/source-tests.txt`. The affected 7 capture tests were rerun
after the restoration corrections and passed. The 2 evidence-counting tests and
one final Ruff check of `src`, `scripts`, `tests` also passed.

Coverage includes real stdio dispatch into Adapter and the existing queued runtime,
new-target admission, local observation failure, strict before/precondition failure,
passive partial diagnostics, cancellation/epoch changes, bounded partial values,
long complete addresses and useful summaries, eight-corner transformed bounds,
selection timing, missing/empty/unsupported targets, and immutable artifact retrieval.
Existing lost-response/no-replay, operation identity and capture fault tests passed.
The stdio tests use controlled HOM doubles; actual HOM/GUI evidence is separate below.

No UI code changed. The existing CI native-ui job remains a regression gate; its
offscreen results are not substituted for real Houdini GUI evidence. Final candidate
CI status and exact tested SHA are recorded in the PR checks before technical merge.

## Real H22 production Runtime checks

Houdini **22.0.368**, real GUI, dedicated HIP copies, dedicated preferences/temp/state
under `.runtime/reviews/tc2`. A small local driver sends ordinary Adapter requests to
the production loopback Runtime and its main-thread queue. It starts no reasoning
client, bypasses no authentication, and keeps its fresh service token in memory and
the child environment. Only the driver's owned Houdini processes were closed.

Commands, unabridged results and all failed observations remain locally under
`.runtime/reviews/tc2/commands` and `technical/<session>/`. Runtime receipts and PNGs
remain under `technical/state/workspaces/<workspace>/`. No raw history, credentials,
HIP binaries or machine paths are included in the PR.

Execution checks used source `3ce11cb`, session `5798cfb244984c22ba2fa18b5154ef14`;
subsequent source changes touched only capture restoration.

| Case | Original operation | Observed result |
| --- | --- | --- |
| Create geo/box/output in one batch | `a47741b567e044dfbb1af7c892be2e97` | 3 successful node/parameter/geometry observations in the original receipt; size 2/3/4, 8 points, 6 primitives, 24 vertices |
| Controlled exception after creating a node | `8e15ee011dbe41798fc8717ba0852133` | failed/partial, original exception and partial value retained; 2 passive reads, 2 skipped reads; requested parameter values explicitly skipped |
| Targeted correction | `6fdce5b852a74f0d9424406fb5506290` | same native node instance retained, sizex changed to 2.5; no delete/rebuild |

Temporary counters around native Python `hou.Parm.eval` and `hou.SopNode.geometry`
recorded **zero backend calls during partial diagnostics**; both original methods
were restored before the targeted correction. This establishes the backend's passive
read path, not a claim that every native Houdini internal background action is stopped.

### Target framing, requested frame and restoration

Final capture checks used source `ff11a0b20f1f54865b84333d3bee20cd7dcf63fa`, session
`3dc5959230c7465eb05620c0f602fa32`, workspace `7f336d1f88e64e2e87b164f8141f9dc2`.
The target is nested below a translated, rotated and nonuniformly scaled OBJ parent.
SOP geometry, parent translation and the existing camera translation are animated.
Independent expected bounds were calculated from the eight actual box points and
the native complete object transform at frames 24 and 72.

| Case | Operation | Result |
| --- | --- | --- |
| OBJ viewer, right view, free camera, frame 72 | `996cec91978a492e8c5e86c533cb7cba` | finished; complete framing and free-view restoration |
| SOP viewer, actual selection, top view, locked animated camera, frame 24 | `22b42466ae204dbab9c647af554b7387` | finished; exact selected source, bounds equal independent frame-24 reference |
| SOP viewer, OBJ target, three-quarter, locked camera, frame 72 | `7c3098a869dc4bf4ba2271fc80026f80` | finished; display SOP resolved, bounds equal independent frame-72 reference |
| Multiple targets, current view, one non-display SOP | `72da4b75c741449daa690e968b4f63a4d` | finished; union bounds, actual display source and `TARGET_NOT_DISPLAY_OUTPUT` warning; no display switch |
| Capture-call fault | `adf6d64b1284410286bf901d5a2cdbb9` | failed/none; capture error, no artifact, no restore error |
| Default-view restoration fault | `9ea876dbd77840af862ff76fd40fd0e1` | failed/unknown; capture itself succeeded, valid PNG retained, separate restoration errors |
| Query that failed receipt | same operation | same artifact `d65497c6cf06412f97ec41931280f151`; flipbook counter stayed at 1 |

For the animated target, expected frame-24 world bounds were approximately
`[40.771737,4,-19.915525,49.733975,5.6,-11.886475]`; frame-72 bounds were
`[58.235597,4,-25.421858,67.197834,5.6,-17.392808]`. Actual arrays equal the full
precision reference in the saved setup record, not the rounded display here.

Before/after assertions compared frame, camera binding/lock, camera node translation,
rotation, scale, focal length, aperture and animation expression, viewer network,
selection, target/object/parent flags and the parent's world transform. All were
unchanged after successful captures and the capture-call fault. Original frame 1,
projection, view pose/zoom, camera binding/lock and temporary decorations were restored.
The restore-fault case still restored binding, lock, frame and authored parameters,
but correctly detected the damaged free-view cache; the receipt remains failed.
The tester explicitly removed the injected fault and restored that cache afterward.
This tester cleanup is recorded separately and does not alter or replay the receipt.

The faults were injected at the real native `SceneViewer.flipbook` call and the second
`GeometryViewport.setDefaultCamera` call (restore). Successful image creation and
all other view/frame operations used actual Houdini GUI. They were not fake captures
and were not faults injected into an authoring model task.

Actual three-quarter and right-view PNGs were opened and visually inspected: the
transformed target is framed and visible. Background/other geometry was preserved;
the product reports `visibility_verified: false` and makes no pixel-level guarantee.
The final saved technical HIP was freshly loaded/cooked: **25 nodes, zero errors**.

### Native behavior found and fixed

Real GUI exposed that restoring a perspective stash does not restore its inactive
orthographic width in H22. The backend now restores that width while detached before
copying the full camera. Native composed `viewTransform` also showed a 3.499e-6
position roundoff after unchanged camera components. Verification now checks raw
rotation/translation/pivot/focal/aperture at absolute 1e-7 and separately bounds derived
matrix position roundoff by pose scale with a 1e-5 floor. Injected raw component drift
is rejected by the regression test. Binding, lock, width and projection checks remain
independent. Earlier failed receipts are retained, not rewritten as successes.

Normal OBJ and SOP viewers with `isWorldSpaceLocal() == false` were checked against
native projection: world bounds center at the viewport center; object-local bounds
do not. Local-world mode or an unavailable space fact is explicitly unsupported.
Named views require a freely orientable perspective viewport; fixed views are
explicitly unsupported. No temporary camera/node/pane or guessed conversion is used.

## Deferred model task

`scripts/tc2_fixture.py` prepared a write-once 17-node input with an existing opening,
four-part frame, blade module, camera, unrelated asset and transformed parent. There
is **no target blind network**. It freshly loaded/cooked with zero node errors.
Fixture logs and reports remain in `.runtime/reviews/tc2`. This proves input integrity,
not successful blinds, useful model behavior or animation quality.

Resume the exact two prompts and tester change in [TC2-A1](deferred-acceptance.md).
The existing evidence extractor accepts `--stage tc2`, counts unique native calls and
original receipt observations, and retains capture frame/target/restoration facts.
Extra post-create inspections, viewport-only scripts, API guesses, repair strategy,
continuity and visual quality remain manual classifications, never inferred passes.
Neither TC1-A1's efficiency threshold nor TC-2's model benefit is claimed.
