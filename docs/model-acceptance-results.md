# Authorized model acceptance results

These are natural-language runs through production Studio Bridge, native Codex
0.153.4 and the real Houdini 22.0.368 GUI runtime. The user explicitly authorized
TC1-A1, TC2-A1 and TC3-A1 and conversation-scoped scene permission. No workflow
solution, expected nodes or tool sequence was supplied. The frozen prompts and
between-turn tester edits are in [deferred acceptance](deferred-acceptance.md).

Each arm used a fresh native Thread/workspace and a copy of the source HIP. The
authenticated TC2 test CODEX_HOME/state was used explicitly in place; credentials,
formal user state and old histories were not copied or reset. Raw native histories,
receipts, failures and artifacts remain in their original isolated locations.
Native turn_context records confirm `gpt-6-astra` / `high` for every completed
turn below. Tester snapshots/edits and internal polls are excluded from model counts.

## TC1-A1: complete pair; model-effect gate not met

Baseline `1e9f0f4dc43465bd221b3e0832a5e75d6cd1aa66` was compared with immutable
`tc1-a1-candidate` / `ecef5b3f2dae6e95ccd6feb12507a0761f646d10`. Both completed
the exact two-turn railing task and retained their existing networks. This is one
complete pair, not a broad benchmark or proof of a general quality improvement.

| External MCP calls | Baseline turn 1 / 2 | Candidate turn 1 / 2 |
| --- | --- | --- |
| context | 1 / 1 | 1 / 1 |
| inspect | 0 / 0 | 1 / 1 |
| lookup | 0 / 0 | 16 / 1 |
| execute | 19 / 7 | 15 / 12 |
| capture | 11 / 3 | 9 / 4 |
| Total | 31 / 11 = **42** | 42 / 19 = **61** |

Candidate metadata requests were 4 searches and 19 exact types across the pair,
including requests rejected at schema admission. The extra discovery traffic did
not produce the required efficiency improvement. Baseline had 12 read-only HOM
observation/discovery batches plus 2 context calls; candidate's context/inspect/
lookup calls alone total 21, before its additional HOM probes. Captures and mixed
authoring/view-preparation batches are separate from that observation comparison.
Both arms completed, total calls increased, and candidate API/shape errors were
not zero. None of the original alternative effect gates is met.

The first successful authoring request reached the runtime about 119 seconds after
baseline turn start versus 141 seconds for candidate (native timestamps are rounded
to seconds). Its queue/execution durations were about 0.062/0.076 seconds versus
0.063/0.143 seconds. These measurements include model/network/discovery time before
submission; they do not demonstrate a main-thread metadata stall or a latency gain.

Independent fresh-load checks found no node errors: baseline traversed 47/54 nodes,
candidate 51/55. Both had 20 posts initially and 28 final assembled posts. Both
preserved every recorded round-one native node ID in the live second round. The
only original-input parameter differences were the required guide edit (`29-36`,
local Z `-0.5`); original assets, connections and material parameters remained.
Controls changed 1.2 to 0.8 spacing and 1.1 to 1.32 height, retaining each arm's seed
and module ratio. A separate temporary +0.2 height change moved actual output max Y
by approximately +0.2; spacing changes altered actual post count and restored it.
Opening controls, cooked split rails and inspected local images support continued
editing. Candidate's assembled-post count was corrected from an initial tester
report that counted upstream stations; both reports are retained.

Failures are not discarded:

- Baseline: invalid free-camera state, absent `NetworkEditor.homeToAll`, and a
  missing copied point `id` attribute during a readback. The model corrected its
  view/readback locally; it did not rebuild the whole railing.
- Candidate: a metadata request exceeding declared argument bounds, lookup of
  absent `hou.ViewportCamera`, ambiguous VEX vector sampling causing a local cook
  failure, and the same unsupported copied-point `id` assumption. The opening
  branch was repaired locally with the previous node IDs retained.
- Each frozen arm recorded one `VIEW_RESTORE_MISMATCH` capture failure. Original
  receipts and images remain. These are the older pre-TC2 capture implementation;
  they are not relabelled as successful restoration or a newly proven TC3 failure.
- All 14 baseline and 13 candidate captures are retained. Final overall/opening
  views were inspected; some intermediate frames include distracting viewport
  guides. This is geometry evidence, not a publication-quality render acceptance.

**Outcome:** authoring/continuation evidence is positive; TC1's model-effect gate
is **not passed**. Its prior conditional technical merge is not rewritten. Bounded
discovery batching, schema-error clarity and unnecessary API lookup are review
subjects; no extra experiment or code change is made merely to manufacture 20%.

Raw runs:
`tc1/model/baseline-d366d62a3f4441c9adb4359ddbf90b38` (Thread
`01a0807a-8dfc-7f30-a8e8-1ecd24890ef1`) and
`tc1/model/candidate-ca565bb70d5c4c1592417e8373694dce` (Thread
`01a08087-99d9-7323-886e-48a7b2a15ae4`), under `.runtime/reviews/`.
The saved round-one/two HIP snapshots were taken by the tester after each native
turn completed; the model correctly said its changes were still unsaved.

## TC2-A1: authoring checks passed; feedback adoption is partial

Immutable `tc2-a1-candidate` / `293d7b229c586c273a05cee1158c4b09aea0d30a` ran the
exact two-turn editable-blinds task. Turn one used 21 MCP calls (context 1, inspect
3, lookup 9, execute 5, capture 3); turn two used 5 (context 1, execute 3, capture 1).
This is a single task, not an A/B efficiency percentage.

Fresh-load/cook checks traversed 44 nodes in each saved round with zero errors.
The first output had 10 blades. The second has 12 actual blade groups, with native
angle values 15 degrees at frame 24 and 65 degrees at frame 72. Measured blade
extents match the rotated source dimensions. At frame 72 the aperture clearance
is approximately 0.006738 above/below and 0.10 at both sides, in window coordinates.
The generated object shares the frame's coordinate system. These are endpoint
geometry checks, not a swept collision proof for the entire animation interval.

Count set temporarily to 8 produced 8 blade groups and restored to 12; thickness
set temporarily to 0.045 produced approximately 0.045 actual fitted thickness.
All recorded original/generated round-one node IDs persisted. The only original
parameter changes were the prescribed parent translation (+0.8, +0.2, -0.6) and
Y rotation +22 degrees, now `(4.8, 0.6, -2.6)` / Y `40`. Other source nodes and
connections stayed unchanged. Tester probes did not save their temporary edits.

Three captures used target paths; one used explicit close-up bounds. All four
receipts finished with successful restoration, including the requested frame-72
image after the tester had moved the viewport away. Front/side images were opened
and inspected. Viewport background guides/selection outlines can remain visible.

The model used **zero explicit observe_after requests** in its eight execute calls;
it continued to write its own HOM readbacks. Thus target-capture adoption is proven,
but adoption of standardized execution feedback and a reduction in total calls are
not. One lookup exceeded the schema limit (`limit: 80`) and was rejected; the model
corrected it. No execution or capture failure occurred in this task.

**Outcome:** the requested authoring and continuation checks pass. TC2's model
benefit is supported for target capture only; do not report full feedback adoption.
Raw run: `.runtime/reviews/tc2/model/candidate-6729d82e8adf4ff4af95865de667fa25`,
Thread `01a08093-9169-79c0-a6fa-8d9eb89c8f08`. Original receipts/artifacts remain in
its workspace under the explicit TC2 acceptance state.

## TC3-A1: staged recovery and HDA reuse verified; quality gaps retained

Immutable `tc3-a1-candidate` / `c03317d6db36acb1533c042f9c094c3322ed3a65`
completed the exact two-turn HDA task. The tester only applied the frozen input
edit between turns and appended the new output directory to the prompt. There was
no extra prompt to repair the asset after acceptance.

| External MCP calls | Turn 1 | Turn 2 |
| --- | --- | --- |
| context | 2 | 1 |
| inspect | 5 | 1 |
| lookup | 13 | 4 |
| execute | 12 | 8 |
| capture | 2 | 1 |
| operation | 5 | 1 |
| Total | **39** | **16** |

There were 55 MCP calls plus one native sleep item. The 20 execute calls include
**three staged requests containing six steps**. An early progress statement that
the model did not use steps was based on the beginning of the run and was wrong;
the complete native history and original step receipts establish this count.

| Operation | Steps and retained result |
| --- | --- |
| `62ce2d6d608843b68890f9ddb47424e0` | `clean` finished with checks passed; `package` failed after partial mutation (`Invalid parameter name: instance_id`). A new local correction repaired the HDA interface without replaying the completed step. |
| `0dd96ab200b7466aa2c8d05a491c22ae` | `controls` finished, with no declared checks; `inputs` finished with declared checks passed. Both step results remained available. |
| `8ef9a6d845404ff19dca4f3c931fd200` | `version_and_control` finished with checks passed; `second_instance` failed its node-identity assertion after native HDA type migration. A new operation inspected and corrected the remaining migration/validation work; it did not replay the batch. |

The versioning request's second step actually reads the first step's JSON result.
Some scripts also explicitly stored bookkeeping dictionaries in `hou.session`
(`walkway_delivery`, `walkway_verification`, `walkway_v2_baseline`). This is visible
model-authored HOM code, not a backend-created Python session or evidence of passing
HOM objects/functions through JSON. Its reliance on extra scene-session bookkeeping
remains a review point; standalone HDA reuse was checked without that session.

Other failures remain in the record: an initial VEX type/cook issue was corrected
locally; legacy save/embed operation `3700cf1874f4433cb0ecc461eeba4863` failed with
`HOM_FAILED`, followed by a successful explicit embed/save operation
`ef326ff496e44cf8873708c70dfc2718`. That callback took about 22.22 seconds. The
longest callback in a staged request took about 3.58 seconds. Steps provide event
opportunities between callbacks, not preemption inside a long HOM/save call.

### Delivered asset and independent checks

The model wrote new v001 and v002 HIP, external HDA, README and validation files,
retaining both versions. The final type is
`bigchicken::procedural_walkway::1.1`, upgraded from `1.0`, with two existing
instances at `/obj/procedural_walkway_demo/walkway_road_1` and `walkway_road_2`.
Its inputs are a guide, paving modules, a curb module and optional exclusions;
outputs expose combined geometry, paving and curbs. Width, dimensions, joint,
stagger, clearance, seed and instance ID are exposed. Version 1.1 adds independent
curb depth while retaining the other controls. Road two width changes 2.4 to 3.0;
the seeds remain 23 and 71. Both HIPs and HDAs remain available.

Fresh-load/cook of the saved versions found no output errors. Final outputs contain
147/139 pieces, 1176/1112 points and 882/834 primitives, with finite UVs and actual
paving/left-curb/right-curb groups. Original source parameters changed only for the
prescribed first-guide edit (points `20-28`, local Z `+0.5`) and exclusion X `+0.8`.
Original source connections and unrelated assets were retained. Probe edits were
temporary and were not saved over the model's HIP/HDA files.

A second independent hython process started without the custom type, original HIP,
Studio paths or HIA/BCS environment. It installed only the external v002 HDA and
instantiated two new nodes using exported original input geometry. It did not use
baked walkway outputs. Both instances cooked with no errors and nonconstant finite
UVs. The second instance verified:

- Increasing paving thickness changed paving vertices while curb vertices stayed
  identical; increasing curb depth by 0.05 changed curb vertices by about 0.05 while
  paving vertices stayed identical.
- Width 3.0 to 3.4 changed the output from 139 to 161 pieces.
- Seed 71 to 72 retained piece IDs while changing 46 module variants.
- Disconnecting exclusions changed 139 to 171 pieces.
- Translating the second input guide by +0.25 Y moved the output by about +0.25 Y.

Closed-edge checks passed, but they do not establish absence of self-intersections.
All three capture operations finished successfully. The final image was opened and
shows local folded/overlapping modules at the edited sharp bend on the first guide.
The model also acknowledged this in its final reply/README. Zero cook errors,
working controls and reusable HDA packaging do not make that visual defect pass.

Across the live two-turn snapshots all 96 recorded node paths remain, but **41
native node IDs changed** during HDA type migration, including the two HDA roots
(72 to 148 and 94 to 180) and some generated internals. The original 18 source nodes
and unrelated assets kept their IDs; paths, wiring and existing control values
were preserved. This is positive input-preservation evidence, not proof that all
original runtime node identities survived or that names can replace that condition.

**Outcome:** natural staged usage, retained step facts, local recovery and clean
external HDA reuse are demonstrated. Full artifact-quality/identity continuity is
**not passed** because the local fold and changed native IDs remain for Pro review.
No generated-asset repair or tool-description tuning was added to change this run's
result. Technical step/Stop evidence is separate in
[TC3 validation](tc3-validation.md).

Raw run: `.runtime/reviews/tc3/model/candidate-590df37fc2894fed8a7db643c43d6d76`,
Thread `01a0809b-2d19-7853-bd8c-cd260aadd352`. Deliverables are in that run's
`outputs/`, including `walkway_example_v002.hip` and
`procedural_walkway_v002.hda`. `fresh-quality.json` and
`clean-check/standalone-report.json` contain the independent checks; all original
receipts/details and native exports are retained alongside the evidence.

## Evidence locations and review disposition

Each run above retains `run.json`, native turn exports, `metrics.json`,
`native-confirmed-settings.json`, `original-receipts-and-details.json` and tester
snapshot details. The original ledgers and artifacts stay under
`.runtime/reviews/tc2/acceptance/state/workspaces/` in their respective workspaces:

| Run | Workspace ID | Independent quality report in its run directory |
| --- | --- | --- |
| TC1 baseline | `a0dd3b2d3a174fb3a3268e0fe6c7a87e` | `fresh-quality.json` |
| TC1 candidate | `09deb22fe7b1459a9621bed2feb23ab3` | `fresh-quality-corrected.json` (initial counting report retained) |
| TC2 candidate | `2924b961578d4c1ba4812a5a8e0598da` | `fresh-quality.json` |
| TC3 candidate | `87678ce9883a453299e76939fb7ec98a` | `fresh-quality.json`, `clean-check/standalone-report.json` |

Original native histories remain in the shared isolated test
`tc2/acceptance/state/codex-home/sessions`; the table identifies each native working
directory and its runtime ledger, not a substitute history database.

The frozen installation provenance is recorded separately in
`.runtime/reviews/tc3/model-source-provenance.json`; each driver loaded its exact
frozen source and corresponding seven-tool schema. All eight native turns completed;
owned acceptance drivers/Houdini processes were closed after capture and snapshots.
The technical CI and prior conditional TC1/TC2 merges remain separate facts.
TC3's PR remains open for Pro to review these results and outstanding gaps.

## User report retained for Pro

[PANEL-1](acceptance-issues.md) remains open, unclassified and unrepaired. These
drivers exercise native model/Bridge/runtime behavior; they do not diagnose or
resolve the user's Panel message mixing and clipping report.
