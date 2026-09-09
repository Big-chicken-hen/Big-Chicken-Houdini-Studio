# R2: tool-use efficiency

Base: R1 merge `fe57c7a85b650d8a37159f896b85f885d8c046fb`. Branch:
`codex/tool-use-efficiency`. Authority: [Release Readiness](release-readiness-brief.md),
sections 1 and E. This is runtime/tool-cost work, not another model benchmark or UI PR.

## Original eight-turn audit

Read the original `native-thread.json`, `native-events.jsonl` and
`original-receipts-and-details.json` for all four frozen runs linked in
[model acceptance](model-acceptance-results.md). No original export, scene, receipt,
candidate tag or authentication directory was changed. All **184 calls** retain
their Thread/Turn/Item and original operation identities in the local call ledger.
Scripts are classified by actual content, not by the name `execute`.

Local evidence lives under this checkout's `.runtime/reviews/r2/`:

- `call-ledger-raw.json`: exact native arguments/results, matching full original
  receipt/detail, event times and literal target addresses.
- `call-ledger-reviewed.json`: per-call purpose, read/write targets, delivered fact
  fields, static-record overlap, errors and corrective call IDs, visual objective,
  script classification, runtime records, tool gaps and approval-timing limits.
- `turn-diagnostics.json`: eight rows calculated from the native events. `audit.py`,
  `review_calls.py` and `annotate.py` preserve the extraction and review annotations.

`baseline`, `tc1`, `tc2`, `tc3` below map respectively to these original run roots
under `.runtime/reviews/` (all remain in place):

```text
tc1/model/baseline-d366d62a3f4441c9adb4359ddbf90b38
tc1/model/candidate-ca565bb70d5c4c1592417e8373694dce
tc2/model/candidate-6729d82e8adf4ff4af95865de667fa25
tc3/model/candidate-590df37fc2894fed8a7db643c43d6d76
```

Call labels use `run.turn.ordinal`, for example `tc2.1.10`. Full UUIDs are preserved
in each ledger row; no local sequence replaces native identity.

| Turn | MCP calls | Execute: probe / authoring / view / mixed | First authoring arrival (s) | Positive inter-tool gaps (s) |
| --- | ---: | --- | ---: | ---: |
| baseline.1 | 31 | 6 / 1 / 4 / 8 | 118.03 | 450.24 |
| baseline.2 | 11 | 3 / 1 / 0 / 3 | 126.22 | 251.94 |
| tc1.1 | 42 | 3 / 4 / 4 / 4 | 139.81 | 371.95 |
| tc1.2 | 19 | 4 / 3 / 2 / 3 | 108.73 | 312.63 |
| tc2.1 | 21 | 1 / 2 / 0 / 2 | 147.69 | 256.67 |
| tc2.2 | 5 | 1 / 1 / 0 / 1 | 47.70 | 82.66 |
| tc3.1 | 39 | 4 / 8 / 0 / 0 | 271.21 | 696.39 |
| tc3.2 | 16 | 5 / 3 / 0 / 0 | 107.83 | 262.88 |

Probe means no scene/view/file mutation; Python bookkeeping alone is not a scene
write. Authoring includes temporary control-variation tests and delivery writes.
Mixed means scene reads/authoring combined with view/selection/frame changes.
Classification describes the submitted script, including attempts that failed
before reaching every line; the receipt remains the authority for actual effects.
The earlier coarse statement "12 read-only baseline execute calls" is therefore
not used as a strict side-effect classification here: several observation-purpose
scripts also changed viewport/selection. The originals and their pass/fail decisions
remain untouched; this audit distinguishes those cases instead of silently carrying
that coarse count forward.

Arrival is native `turn/started` to the first content-authoring receipt's admission,
not the earlier driver submission or UI click. Thus 118.03/139.81 s here and the older
approximately 119/141 s describe different start boundaries. Gaps are positive time
between completed tool items and the next start; they combine model/network/other
native activity and **cannot be labelled pure thinking or Runtime latency**.
Every call has an elicitation/resolution in the saved authorized test stream. Those
callbacks share recorded timestamps; their zero logged interval does not measure
human approval latency. Actual user wait is explicitly unavailable, not zero.

### Information gain and correction findings

- **Confirmed repeats:** `tc2.1.10` queried `environment`, returning two identical
  members already delivered by `.09` (`background`). `.15` queried `ground` and
  returned the same 15 background members, because matching is substring-based.
  No installation change intervened. `.18` (`guide`) instead supplied three new
  members, so it is not counted as another redundant call.
- **Partial repeat, useful new facts:** `tc1.1.08` repeated four resample parameter
  records from `.07`, added four records and obtained new copy groups/radius/xform
  tokens. `.10` obtained `length`, `method`, `class`, `pack`, absent from the earlier
  transmitted pages. Treating these as entirely wasted lookup would be wrong.
- **Payload selection matters:** broad type requests with both default parameter
  and help payloads often delivered only four parameters and 256 help characters
  per request after summarization. TC2's `tube` request at offset 8 correctly
  continued the previous page. TC3's targeted `class`/`xformtype` reads added missing
  tokens. Use the existing include flags/patterns to avoid unrelated payload; no
  automatic requirement to inspect more or increase every budget was added.
- **Schema correction:** `tc1.1.06` failed for `requests[0].parameter_limit=70`
  (maximum 64). The frozen candidate schema permits `help_limit=5000` (maximum
  8192); that value is not itself a violation. `tc2.1.14` used HOM member `limit=80`
  (maximum 64), then `.17` corrected it to 40. The original generic oneOf error did
  not tell the model which value to fix. R2 reports the exact index/field/range.
- **Recovery is useful work:** TC3 original step detail plus current target reads
  support new local correction after the `instance_id` and type-migration failures.
  `.1.36/.37` query the same long-running save/embed operation, not repeat execution.
  The 22.22 s original save/embed callback is not evidence of SQLite being slow.
- **Inline readback remains valid:** all eight TC2 execute calls use script readback;
  zero use `observe_after`. Existing successful editing/continuity evidence remains
  valid. Temporary control tests are not mislabeled pure read-only calls.

### Capture review

All 34 captures have a per-call objective linked to preceding changes: source views,
new geometry, openings, bend/crest details, frame 72 clearances, or view recovery.
Not all are independent geometry validations. Numerous TC1 calls prepare a different
angle, restore a camera, change display preferences or return to an overall view.
The audit does not prohibit a capture solely because geometry is unchanged.

Four original PNGs were actually opened during R2 (no new capture): baseline `.1.29`
artifact `438319b2041142d182dfcaba35b9f6ba` versus `.1.31`
`972894cec5d44e268c49b71b6b82c35e`; TC1 `.1.16`
`54af7f2def78483589ca492c36c55459` versus `.1.22`
`92551d8d338b442a99b8e099e14d0e1c`. The first pair shows the same overall guardrail
with a changed scene/selection display; the second remains cluttered by the grid
despite shading/view work. This supports identifying presentation/recovery overhead,
not deleting necessary close-ups or declaring the original asset quality improved.
Other capture necessity assessments use scripts/receipts and intended questions,
not a new pixel-level pass of every historical image.

## Bounded implementation

`SCENE_INSTRUCTIONS` now expresses six decision principles. Known edits can execute
directly; relevant reads can be combined; valid facts are reusable; single scripts
and staged execution are optional alternatives; readback and `observe_after` need
not duplicate one another. Native-history authority, explicit destructive/overwrite
authorization, runtime-only scene control and honest delivery remain. Output helper,
step JSON limits and wait/Stop mechanics live in the relevant tool description.
No quota, mandatory capture/check, Python subset, node allowlist or hou.session ban.

Schema validation still accepts exactly one valid shape. Ranking invalid shapes
only selects the most relevant diagnostic; it never makes a request valid. Errors
carry paths such as `arguments.requests[1].parameter_limit` and allowed bounds.
Metadata search now uses **default 12, maximum 80** for both canonical and legacy
flat requests. Previously valid flat requests remain accepted, with accurate cursors;
the legacy default page becomes smaller. Existing filter defaults remain distinct
for compatibility. HOM members stay at 64; parameter/help bounds are unchanged.

Lookup builds cheap name/label/alias candidates, checks lifecycle filters only for
keyword matches and constructs detailed status only for the transmitted page.
Category maps and replacement checks reuse one request-local catalog. Help archive
handles and bounded static target text are reused within that request and closed
afterwards. The next call sees HDA/catalog/help changes. No disk index or persistent
cross-session cache was added. Summary construction clones retained rows only;
full sanitized original detail, identifiers, errors and cursor semantics remain.

## Same-installation comparison

Native **Houdini 22.0.368 hython**, real HOM on its main thread, production Adapter,
authenticated loopback HTTP, the single operation queue and SQLite `synchronous=FULL`.
New disposable fixtures/state/prefs/temp only under `.runtime/reviews/r2/`; no model,
live user scene or credential copy. The standalone tester dispatches callbacks to
its actual main thread. This measures Runtime behavior, not GUI/Panel responsiveness.

`bench.py` and `run_bench.py` ran the same 19-request set before/after, then once in
reverse order to investigate a first-run timing spike. Four fresh processes exited
normally: `before-isolated`, `after`, `after-repeat`, `before-repeat`. Each directory
retains results, receipts, log and profile. Initial setup attempt `before` emitted a
preference-path warning; it was excluded. The corrected path includes `__HVER__`,
and all accepted measurement logs are free of that warning. No environment or
Houdini preference changes were made globally.

"First" means first request of that family in a fresh process. OS disk caching was
not controlled, so this is not a claim of cold disk performance. Lookup families
each have two first samples and six warm samples. Metrics below are milliseconds;
HOM/metadata is median scene.run time over the identical set, not total tool time.

| Family | Internal HOM/metadata before → after | Warm Adapter median before → after | First Adapter samples before / after |
| --- | --- | --- | --- |
| Four SOP keyword searches | 67.64 → 19.76 | 94.11 → 94.08 | 125.74, 93.56 / 94.18, 109.46 |
| Four exact type/parameter/help reads | 61.35 → 18.04 | 93.99 → 93.47 | 186.55, 187.64 / 94.96, 92.92 |
| Four pages of the same installed help | 50.70 → 15.26 | 94.49 → 93.84 | 93.88, 91.90 / 124.08, 95.34 |
| Existing box parameter page | 0.548 → 0.554 | 93.88 → 93.45 | 94.00, 93.43 / 94.45, 92.79 |
| Create owned fixture and read geometry | 18.76 → 18.99 | single request per process | 93.70, 109.33 / 109.87, 93.67 |
| Two-step change/readback | separate staged callbacks | single request per process | 94.44, 93.81 / 93.34, 93.66 |

The isolated 124 ms first help sample did not reproduce; the reversed pair and warm
samples expose the common scheduling/polling variation. Authoring first-run values
also swap between roughly 94 and 110 ms with no production authoring change.
Queue medians stay about 2.3–3.0 ms. Inclusive durable transactions remain about
7–9 ms per single operation and 14.6 ms for the two-step batch. Measured JSON encoding
remains about 0.07–0.60 ms for ordinary receipts and 4.1–4.3 ms for the staged batch.
These measures overlap: encoding is included in transactions/Runtime, not an extra
duration to add again. Full decomposition is in `runtime-comparison.json`.

The current 80 ms Adapter polling interval limits visible warm RTT gains. It was
not changed to manufacture a faster result. The representative profile changes
9 help archive opens to 2 (one per help-bearing call), and 45 `nodeTypes()` reads to
3 (one per metadata call). The 16×64-row synthetic parameter summary returned the
identical output while profiled construction fell from 18.09–18.56 ms to
1.47–1.74 ms. This is a construction profile, not an end-to-end authoring benchmark.
**All 34 comparisons passed:** 32 lookup/inspect result comparisons plus two large
summary comparisons. Full identifiers, metadata, original rows and cursors agree.

No Runtime, Ledger, queue, scene execution or staged gate code changed. Durable
admission, per-step start/result commits, Stop/context fencing, original detail,
unknown/partial outcomes and no-blind-replay remain intact.

## Validation and remaining gates

- Five new focused cases: indexed schema diagnostics, strict nested unions,
  compatible metadata paging and selective lifecycle work, request-local help reuse
  with fresh updates, and bounded summary construction without original mutation.
- Existing targeted checks: 11 help/result, 10 TC1 contract, 21 operation fault and
  13 staged fault cases passed. Ruff passed. No full local suite was repeated.
- Real isolated HOM successfully created/cooked an owned box, read its parameters,
  changed it through two durable steps and retrieved original receipts. All owned
  benchmark processes closed. No user data or installed tool configuration changed.

The local R2 technical checks pass; final PR-head CI is recorded on its PR before
merge. This demonstrates reduced mechanical backend work and more actionable tool
contracts, **not a new claim that TC1's model efficiency gate passed**. The frozen
42-versus-61 outcome, TC2's successful authoring and TC3's quality/identity gaps remain.
R3 presentation and R4 real-package user-flow acceptance are separate work. This
does not authorize or declare a public release.
