# Authoring stage: implementation and evidence

Review baseline: `c2c63111c3a10ae3131e271a48dbacddae3570b7`.
The implementation is in [PR #3](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/pull/3).
This stage is still awaiting final cold-launch authoring acceptance.

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

[CI at `33b2429`](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/33967096704)
passed all four Windows/Linux backend jobs and the separate Windows Qt job.
The initial integrated local run exposed a Windows venv redirector PID mismatch
in the ownership test fixture. The fixture was corrected to use the direct
interpreter; the affected normal, handled-error and forced-exit cases then passed.
This was a test-fixture correction, not a relaxation of production PID validation.

The subsequent startup-error propagation change, Stop wording and scene
instructions were source-reviewed but have not been retested in this review pass.
The earlier CI result does not certify those later commits.

Dedicated Houdini 22.0.368 runs produced evidence for queued cancellation,
same-path HIP reload rejecting an old observation, one execution after an
intentionally discarded admission response, and receipt/image retrieval in a new
Houdini process. Integer-frame captures passed explicit and viewport-derived
resolution checks. A request for frame 1.5 was rounded to 2 in that installation;
capture failed explicitly and restored frame 1. It is not fractional-frame support.

These runs used a developer-controlled dedicated scene and test driver. They do
not substitute for the final ordinary-user workflow. Original intermediate
reports are retained; selected public evidence describes individual cases rather
than relabeling every raw report as a completed acceptance run.
The [selected receipts](evidence/authoring-2026-09-05/README.md) omit the original
PNG because its text metadata contains a local machine username. The untouched
image remains local; the public bundle provides no independent visual check.

## Acceptance still open

The Stop attempts so far do not establish button reachability during long HOM.
Two native turns were interrupted before a long execution was admitted. A later
attempt completed its context read, but no long-execution receipt was present at
this review checkpoint. Computer Use was subsequently stopped by the user.
Input-helper focus failures also do not establish a Composer defect.

The final current-main cold launch, new workspace, three ordinary Panel requests
that create and twice modify the same bookcase, and native image feedback with a
model explanation are still required. Do not report this stage as complete on
the strength of CI, the earlier Box example or the dedicated fault driver.

## Repository cleanup

PR #1 was compared with main and closed as superseded. Its distinct old launcher
and smoke implementation remains at tag `archive/product-readiness-draft-20260905`
(`36081143f9fbe6f365fc01dcda57fff981cc3507`). The completed remote PR #1 and PR #2
branches were removed. Local worktrees and unrelated drafts were preserved;
public main history was not rewritten.
