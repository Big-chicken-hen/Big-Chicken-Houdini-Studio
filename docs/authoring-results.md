# Authoring stage: implementation and evidence

Review baseline: `c2c63111c3a10ae3131e271a48dbacddae3570b7`.
The execution/query foundation in [PR #3](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/pull/3)
closed at `9ad3e260775520a89350ec246eda8c20a7e26f01` and merged into main as
`76e2292bf7609d5da6a3c4ada6c2954abdd1f57a`, preserving its commit ancestry.
[PR #4](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/pull/4)
closes the implemented native input, scoped-consent and targeted authoring
foundation. The subsequent scene-first UI brief moves its outstanding user
workflow acceptance into `codex/ui-productization`; those checks remain pending,
not passed. HIP onboarding, official sign-in, model-setting synchronization and
the shared visual system are outside PR #4's bounded implementation scope.

## Implementation review

- The Houdini Runtime acquires its own workspace execution lock before opening
  or recovering the ledger. The worker retains that lock and SQLite connection
  until outstanding execution and receipt persistence finish, even when a close
  request times out. The supervisor's lock is no longer the sole protection.
- Review also found that a ledger or service initialization exception could leave
  the launcher waiting indefinitely for Runtime registration. That failure now
  uses the existing session error channel with a fixed safe message, while
  retaining the existing cleanup behavior and leaving Houdini open.
- Parameter inspection exposes actual native instances and multiparm indices
  without evaluating parameter values. Geometry inspection limits element reads
  and attribute samples; array and dictionary values remain metadata-only.
- Captures validate PNG bytes, dimensions and frame evidence. A durable workspace
  artifact reference survives Runtime restart. Capture and restoration errors
  remain separate, and a missing image does not rewrite the original receipt.
- Active history repair has a bounded automatic reread budget. Existing message
  cards, text documents and images are reused, with reading-position preservation.
  Codex native history remains the only conversation store.
- Stop requests still depend on the Panel's Qt event handler running. A cooperative
  checkpoint can observe a received cancellation, but it does not make a blocked
  GUI process mouse input. Scene instructions favor short semantic batches and the
  Panel explains this limitation without claiming immediate interruption.

## Verified checks

[Final PR #3 candidate CI at `9ad3e26`](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34006143566)
passed all four Windows/Linux Python 3.10/3.13 backend jobs and the separate
Windows Qt job. This supersedes the earlier `33b2429` development checkpoint.
The initial integrated local run exposed a Windows venv redirector PID mismatch
in the ownership test fixture. The fixture was corrected to use the direct
interpreter; the affected normal, handled-error and forced-exit cases then passed.
This was a test-fixture correction, not a relaxation of production PID validation.

The final candidate CI includes startup-error propagation, Stop wording, scene
instructions and pane-menu registration. The closure review checked their source
and existing test coverage; it did not repeat the full local suite or inject a
new real Houdini startup failure.

Dedicated Houdini 22.0.368 runs produced evidence for queued cancellation,
same-path HIP reload rejecting an old observation, one execution after an
intentionally discarded admission response, and receipt/image retrieval in a new
Houdini process. Integer-frame captures passed explicit and viewport-derived
resolution checks. A request for frame 1.5 was rounded to 2 in that installation;
capture failed explicitly and restored frame 1. It is not fractional-frame support.

These runs used a developer-controlled dedicated scene and test driver. They do
not substitute for the final ordinary-user workflow. The archived reports do not
identify the executing commit SHA and retain their original running status;
individual case results are not a completed acceptance of `9ad3e26`. Intermediate
reports are retained; selected public evidence describes individual cases rather
than relabeling every raw report as a completed acceptance run.
The [selected receipts](evidence/authoring-2026-09-05/README.md) omit the original
PNG because its text metadata contains a local machine username. The untouched
image remains local; the public bundle provides no independent visual check.

For PR #4, [source candidate CI at `0e2c362`](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34011616375)
passed all five jobs against the original stacked base. The diagnostic capture
regression and 16 capture tests also passed locally with process exit 0, followed
by a successful scoped Ruff check. The 2026-09-06 closure edit changes this report
only; [PR #4 checks](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/pull/4/checks)
track the current candidate against main. Automated and offscreen checks do not
establish actual model consent delivery, Houdini capture or continuous authoring.

## Product acceptance carried into the UI stage

The archived Stop attempts do not establish button reachability during long HOM.
Two native turns were interrupted before a long execution was admitted. A later
attempt completed its context read, but no long-execution receipt was present at
that checkpoint. Computer Use was subsequently stopped by the user.
Those historical input-helper focus failures did not establish a Composer defect.

The UI stage carries real input and draft behavior, native consent grant/revoke, three
ordinary Panel requests that create and twice modify the same asset, native image
feedback, and continuation in an existing HIP copy after a manual scene change.
The [latest closure brief](pr5-closure-brief.md) combines these into one short
edit/capture/continue/Save As/reopen workflow for #5; no separate complex asset
project is required to close the UI stage.
Review capture must preserve the original view, camera binding/lock and frame.
The actual running-HOM Stop boundary still needs one bounded user check: when the
request can arrive, whether subsequent work stops, and the final original receipt.
An honestly reported uninterruptible native call is a known limit; duplicate
effects, lost receipts, wrong terminal states or camera pollution require fixes.

These checks move with the explicit scope change; neither foundation PR claims
they have been completed. PR #4 merged at `557a393`; `codex/ui-productization`
starts from that main and concentrates on scene entry, native account/model settings and editor
interaction. MaterialX, Solaris, Karma, animation and simulation are outside this
UI stage. Runtime ownership, receipts and the bounded main-thread queue remain
the execution authority throughout.

## Earlier UI candidate verification, 2026-09-06

The UI implementation at `55eeddc` replaces the ordinary workspace entrance with
Recent HIP, Open HIP and Start Empty. Native onboarding checks the pinned Codex
executable and account before launching Houdini. Installation resources, persistent
user data and disposable cache are separate; successful HIP saves update file
associations and subsequent default outputs without moving the active ledger or
native cwd. Panel model/effort selection follows native settings, and local
per-conversation documents retain drafts and attachment ownership.

The user's final scope correction removes the proposed legacy-context browser,
profile-switching launch flow and extra copy-details button. Icons use Qt standard
resources or text controls; there is no custom brand mark or hand-drawn status
icon. Unknown-source prompts and automatic restoration of the previous requested
model were removed; confirmed scene replacement and explicit current user model
choices retain the Pro brief's behavior. Existing private data was not migrated.

After integration, 31 focused backend checks and 34 native Qt checks passed with
process exit 0 on Python 3.10.11 / Qt 6.8.3. They cover storage containment,
HIP association/output policy, account uncertainty, native model settings,
launch-response loss without a second process, draft/attachment preservation,
structured HTTP errors, scoped consent, history reuse and QObject teardown.
One integrated Ruff check passed. Launcher previews at 100%, 125%, 150% and 200%
and Panel working-state previews at widths 360, 440 and 720 were generated from
isolated fixtures and reviewed. Local logs and previews remain under `.runtime`.

The [initial UI candidate CI](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34018288515)
passed all four backend jobs and all 57 Qt tests. Its high-DPI preview step failed
because two scales shared an output filename. The workflow now gives each scale
its own directory and includes the nested Launcher and Panel reports in uploaded
evidence. This was an evidence-output collision, not a successful overall CI run.

A separate clean-profile probe of the real Codex 0.153.4 executable completed
`initialize` and `account/read`, reported signed out and closed its owned client.
It did not sign in, call a model or start Houdini. Official browser sign-in,
ordinary end-to-end authoring, actual HIP Save/Save As events, native consent and
model use, real input/clipboard behavior and cross-monitor DPI remain pending.
Offscreen fixtures do not satisfy those acceptance conditions; this UI candidate
is not approved for main on the strength of screenshots or CI alone.

## Staged UI candidate verification, 2026-09-06

The [approved presentation specification](ui-presentation-brief.md) supersedes the
earlier Dashboard layout and Qt standard product icons. The reviewed UI source is
`2e373d36eaac566d525f03491b326287269a01e8`. Launcher now projects Checking, Setup,
Authentication, Home and Launching from the existing service facts. Open HIP and
Empty activate through one launch guard; Recent single-click only selects. An
uncertain launch retains its original request and cannot return to an action
that creates a second process. Confirmed target opening minimizes once per
request unless that preference is disabled or the user is viewing details.

Panel has a compact scene/conversation header, one model/effort popup, one
Composer frame and a fixed Send/Stop slot. Per-thread QTextDocuments, native
settings revisions, attachment ownership and late-callback guards remain intact.
Result images fit the available width and enlarge already decoded, approved
image data. Consent presents operation, target and scope before its expandable
native request. The model popup has one permanent next-turn footer; an image
modality mismatch explains disabled Send in the existing work-status area.

The only product icons are the 23 approved Lucide Outline 0.468.0 SVGs. Resource
review compared original upstream bytes at the pinned commit and built an actual
wheel: 23 SVGs, both license notices and their README were included; the old
artwork was excluded. All 23 icons rendered from that wheel at DPR 1.5. Missing
resources retain readable text and diagnostics. No graphic logo or Qt system-icon
fallback is used in the product. Native window and file-dialog icons stay native.

The integrated static check and all 67 native Qt tests passed on Python 3.10.11 /
Qt 6.8.3 with process exit 0. After the final popup/status adjustment, the 12
affected model/Composer tests and scoped Ruff passed again. The final Setup action
correction also passed its targeted action-template test. These checks use
checkout-local fixtures and do not access real account or scene state.

Review generated all twelve required Launcher states, plus key compact states
at 125%, 150% and 200%. Panel fixtures cover the nine required states at widths
360, 440 and 720, with narrow working/popup cases at 150% and 200%. Final integrated
source was rendered again at 100%, plus the narrow Panel at 200%; the popup fit
the available screen. Reports distinguish local fixtures from real execution.
CI publishes these bounded previews and their environment reports with the
[current PR checks](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/pull/5/checks).

The presentation correction has no source changes to the existing backend
onboarding, accounts, storage, native protocol, receipt or Houdini capability
contracts. The formal installation and private user data were not changed.

PR #5 remains Draft. The [latest Pro closure decision](pr5-closure-brief.md)
freezes features and further UI redesign. Its compact real workflow is the merge
gate: official browser sign-in with Launcher/production account continuity;
first-use and returning-user startup; Microsoft Pinyin and text/image clipboard
input in the real Panel; native model/effort and consent grant, reuse and revoke;
a small edit, production capture and a second edit of the same asset; real
Save/Save As into another test directory, Recent reopen and continued editing;
and one bounded Stop check after execute is actually running.

These items remain unverified for the candidate until user actions and the
corresponding records are reconciled. Record an image reaching the model and
Panel separately from the model using that image. Save As must retain the active
workspace, ledger and native cwd while updating confirmed associations and later
default outputs; existing output parameters must remain intact. For Stop, record
reachability, delivery time, subsequent work and the original final receipt.
An uninterruptible native call with honest final facts can be a known limitation;
duplicate effects, uncontrolled later writes, wrong terminal state, missing
receipts or a false claim of scene rollback require fixes.

Real cross-monitor DPI also remains unverified, but a missing full matrix is not
an unconditional merge prerequisite. Any observed wrong click coordinates,
off-screen model popup or unreachable Stop control is a correctness blocker.
Do not relabel untested DPI behavior as passed. Neither passing CI nor offscreen
screenshots satisfy the real workflow gate, and it cannot move to another PR.

The closure review reconfirmed source candidate `06b2c5c` directly against main
`557a393`, a clean worktree and all five successful jobs in
[its CI run](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/34025648571),
including 68 native Qt tests. The gate clarification itself changes documentation;
the bounded user-flow fixes below have their own validation.
Only confirmed defects from real use may reopen implementation. After the gate
passes, current candidate CI is valid and no known blocker remains, close #5;
do not wait for more visual polish or next-stage capabilities.

After #5 merges, create `codex/scene-authoring-quality` from the resulting main.
Its sole direction is maintainable procedural editing in an existing HIP. The
approved preparation is small additions to existing node lookup and a short
new-network versus legacy-maintenance principle. No lookup implementation or
new capability is included in this closure change. Copy Stamp's reported use is
an authoring-quality signal. Its underlying selection cause remains unconfirmed;
user-specific trace notes and native records stay local.

## Bounded user-flow fixes after the closure review

Studio's Windows onboarding and production clients now both start native Codex
with `--enable respect_system_proxy`. Their isolated CODEX_HOME had left this
feature at its default disabled value while Windows had a system proxy
configured. Real workflow logs contained five WebSocket timeouts before HTTP
fallback. This fixes the confirmed startup-configuration gap without copying
desktop configuration or credentials, writing global proxy variables, changing
the system proxy, forcing an HTTP-only provider or increasing retry limits.
The installed Codex 0.153.4 accepted the feature and initialized once in isolated
test state; no login, model request, config.toml or auth.json was created there.
The failing WebSocket's exact route and success in a new ordinary user session
are not established by this parameter check alone.

An isolated production-entry regression reproduced a Windows MCP encoding defect:
with a legacy-code-page stdout pipe, a finished context operation could produce
JSONL that was not valid UTF-8. MCP now fixes its stdout wire encoding and strictly
decodes incoming UTF-8 after the existing byte limit. The regression checks a
Chinese request ID and HIP path, equality with the single durable receipt, and
recovery after rejecting non-UTF-8 input. It uses a fake scene and isolated roots;
it establishes the protocol defect, not the cause of every real tool timeout.

An existing real Qt HTTP fixture also reproduced cleanup after an owner had been
destroyed by its success or rejection callback. The HTTP adapter now finishes
reading and schedules reply deletion before delivering a callback, then never
accesses that reply afterward. Both callback-destroys-owner cases pass. This
does not establish a cause or fix for unrelated host event-wrapper symptoms.
No page structure, icon geometry, native scene queue or operation identity changed.

After integration, 21 operation/MCP checks, 10 native UI checks and 20
launcher/onboarding checks passed locally with process exit 0. One integrated
Ruff check passed. Existing fixtures were extended for the reproduced defects;
no acceptance framework, live Houdini run or model-authenticated test was added.
The current candidate still requires the compact real workflow above, including
confirmation of upstream reconnection behavior in a newly started Studio session.

## Repository cleanup

PR #1 was compared with main and closed as superseded. Its distinct old launcher
and smoke implementation remains at tag `archive/product-readiness-draft-20260905`
(`36081143f9fbe6f365fc01dcda57fff981cc3507`). The completed remote PR #1 and PR #2
branches were removed. Local worktrees and unrelated drafts were preserved;
public main history was not rewritten.

The latest closure review also checked the remote `codex/authoring-cycle`
(`9ad3e26`) and `codex/usable-authoring-integration` (`36da952`) tips against main
`557a393`: both were ancestors with zero unique commits. Those two remote refs
were removed with their observed tips guarded; local branches, worktrees and
user data were preserved.

## 待审核问题：项目约定

当前项目约定能持久保存并按需查询，但不会自动进入模型指令。用户希望讨论：是否将它作为类似 AGENTS.md 的功能，仅针对当前 Studio 对话生效。本次仅附上这个问题供审核，尚未实现或改变现有行为。
