# TC-3 staged authoring validation

Scope is the [user-supplied Pro approval](tc3-brief.md): 2–8 linear HOM steps in
one existing operation/queue entry, with persisted gates and explicit local
continuation. Rendering expansion is withdrawn. The consent and native conversation
PRs are independent; [PANEL-1](acceptance-issues.md) remains record-only.

## Contract and focused tests

The seven-tool surface is unchanged. Single-script execute remains supported;
staged input compiles every script before mutation and dispatches each step through
the existing main-thread callback. Per-step start/result receipts gate advancement.
Complete JSON inputs/results are copied between independent namespaces (16 KiB per
output, 64 KiB total), with no hidden HOM references, Python session or replay API.
Failure, cancellation, context changes and unknown persistence stop later steps.
Closed step detail is queryable while running; whole-operation detail waits until
terminal state to avoid paging across changing JSON. Frame/Take facts and scene
identity are checked at each step without silently refreshing a write observation.

Thirteen focused staged tests passed: wire schema and adapter/queue integration,
all-script compile admission, exact JSON handoff and budgets, gate ordering,
partial correction/no replay, frame/Take/epoch boundaries, cancel at several
boundaries, commit failure, stable closed-step detail and SQLite restart recovery.
Related checks passed: 35 TC-1/TC-2 cases, 21 operation cases, 4 runtime ownership
cases and 16 capture cases. Ruff is the static check. CI is tracked in the PR.
Fakes and restart/commit fault injection do not count as real GUI evidence.

## Real Houdini 22.0.368 technical evidence

The dedicated driver used the production Adapter, authenticated loopback runtime,
existing queue worker and real Houdini GUI/main-thread dispatcher. All state,
preferences, HIP copies and logs were isolated under this checkout's `.runtime`.
No Computer Use, new executor or Qt processEvents loop was used.

At source `5444936df793e82a968374e1249b272d9ca4d9e4`, technical session
`df37a9e2a0bb4b34976d14d0baefd3e6` recorded:

- Operation `9b1c3d78c048404a8ad34f7ae9c35459`: four separate phases prepared the
  transformed existing input, module layout, assembled geometry and parameter/UV
  wiring. All four completed their gates. Qt timer values 6943/6948/6953/6958 and
  main-thread identity prove real GUI event opportunities between callbacks.
  Deliberate short holds were for progress observation, not latency measurements.
- Operation `d3f24033d40545289edc0ae0163825f9`: a controlled third-step failure
  retained the first two completed results, recorded partial third-step work and
  left the fourth step not_run. Live reads showed individual running steps.
- New local correction `f937401690b84344803f6e77b72245c0` retained the original
  input/layout native IDs 50/51 and completed only the remaining work. No replay
  or whole-network rebuild was used.
- Original technical authoring failures are retained: an invalid `uvtexture` node
  name in an initial fourth step was corrected locally after verifying installed
  type `texture`; a tester preservation assertion used the wrong expected ID and
  failed before save. The original baseline evidence established the correct ID.
  Neither failure is omitted or presented as a natural-language model run.

The first Stop run exposed ambiguous active/cancelled labels. Fixes made running
mutation uncertainty explicit, retained declared check outcomes and refreshed cached
scene facts on the main thread. Source `6549153eb36db2a6940aff281323ee0f5444fab0`,
session `370d0cbc3a6341abbead79e8d60e6b41`, then verified:

- Operation `d026f140ddc74a28b809365e91563aa7`: live active step remained
  running/unknown immediately after owner Stop; only the eventual receipt marked
  it cancelled with confirmed completed mutation. Later assembly/wiring stayed
  not_run. The first completed step remained queryable by step_id. Timer 25/31
  again showed GUI events between steps.
- Stop was sent by the dedicated driver's production owner/stop route, not a
  human click in the Panel. This proves execution boundaries and event opportunity;
  it does not claim a new physical Stop-button or cross-monitor GUI acceptance.
- Final technical geometry: 240 points, 180 primitives, UV present, width 2.1
  actually wired to geometry, original unrelated transform retained, and the
  cancelled future outputs absent. A new HIP was saved. Fresh-load/cook of that
  final technical HIP checked 51 nodes with zero errors.
- Existing capture operation `001eb6fce9e248278d4ec8f501402593` finished with
  successful restoration; its 960x540 viewport image was opened and inspected.
  This is a simple technical paving fixture, not HDA/model-quality evidence.

Raw receipts, progress reads, failures and images remain under
`.runtime/reviews/tc3/technical/` in the two session directories above. The original
receipt ledger and artifacts remain in `technical/state/workspaces/`; they are not
moved or rewritten. Owned GUI processes were closed after evidence capture.

## Natural model acceptance

The TC3-A1 source HIP was prepared by `scripts/tc3_fixture.py`: two different
elevated guide curves, existing paving/curb modules, two exclusions, a nondefault
input transform and an unrelated preserved asset. No generator, HDA, material,
lighting or render solution was prebuilt. Its fresh-load inventory has 18 nodes
and zero errors. The between-turn tester change edits only the original curve and
exclusion. Model prompts and actual HDA/reusability requirements remain verbatim
in the approval; no expected workflow is supplied to the model.

The user has now authorized TC1-A1, TC2-A1 and TC3-A1 and scene-operation permission
in their fresh test conversations. Existing authenticated TC2 acceptance state is
used explicitly in place, without copying credentials or production history.
The frozen older experiments run first. Their candidate checkouts remain unchanged.
TC3-A1 is queued and is not yet marked passed. Immutable tag `tc3-a1-candidate`
freezes `c03317d6db36acb1533c042f9c094c3322ed3a65` before its natural-language run;
later integration changes do not replace that candidate. Model results are separate
from technical safety.
