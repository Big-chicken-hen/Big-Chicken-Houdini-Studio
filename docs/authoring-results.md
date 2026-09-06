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
Review capture must preserve the original view, camera binding/lock and frame.
The actual running-HOM Stop boundary still needs one bounded user check: when the
request can arrive, whether subsequent work stops, and the final original receipt.
An honestly reported uninterruptible native call is a known limit; duplicate
effects, lost receipts, wrong terminal states or camera pollution require fixes.

These checks move with the explicit scope change; neither foundation PR claims
they have been completed. The next short branch starts from main after PR #4
closes and concentrates on scene entry, native account/model settings and editor
interaction. MaterialX, Solaris, Karma, animation and simulation are outside this
UI stage. Runtime ownership, receipts and the bounded main-thread queue remain
the execution authority throughout.

## Repository cleanup

PR #1 was compared with main and closed as superseded. Its distinct old launcher
and smoke implementation remains at tag `archive/product-readiness-draft-20260905`
(`36081143f9fbe6f365fc01dcda57fff981cc3507`). The completed remote PR #1 and PR #2
branches were removed. Local worktrees and unrelated drafts were preserved;
public main history was not rewritten.
