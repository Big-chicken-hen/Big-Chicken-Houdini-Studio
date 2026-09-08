# Native conversation lifecycle validation

Scope: [approved independent lifecycle PR](native-conversations-brief.md), based on
the scoped-consent merge `d900779`. No scene tool/runtime change or new chat store.

## Behavior

The existing Panel menu opens a compact manager with native title search,
cursor pagination and an archived filter. Rename/archive/restore/delete call only
the pinned native methods. Resume checks both requested ID and returned cwd/ID;
its native model/effort remain authoritative. Current archive/delete detaches the
selection only after native confirmation. Archive preserves its draft; delete
discards only that thread's draft and ignores its late callbacks.

Deletion requires confirmation mentioning possible descendant deletion. Current
turns, pending approvals, busy runtime and unknown receipts block it. The receipt
gate reads the runtime-owned SQLite ledger in read-only mode so an old unknown
receipt cannot disappear behind the compact recent list. Storage read errors fail
closed. No receipt, attachment file, capture, HIP, HDA or output is deleted.

Unknown mutation responses retain the targeted item and draft with a reconciliation
action. A matching native notification, positive scoped title read or positive
archived/unarchived list membership can confirm the appropriate mutation. List
absence never proves delete; an unconfirmed deletion is not retried automatically.
Pending archive/delete also blocks new turns and selection even if a separate
turn-status read reports idle. Noncurrent native notifications invalidate lists;
only known workspace IDs can cause draft removal.

## Evidence

- Nine focused backend tests cover scoping, native query parameters, confirmations,
  unknown/lost replies, noncurrent events, old unknown receipts and no replay.
- Six focused Qt tests cover title/filter pagination generations, deleted-thread
  list/selection/turn callbacks, pending deletion and independent drafts.
- Related Bridge, native model settings, consent and Panel interaction tests were
  run. Ruff is the static check. Candidate CI results are recorded in the PR.
- Initial CI exposed a retained SQLite connection on Windows/Python 3.13 during
  fixture cleanup. The read-only receipt gate and fixture now explicitly close
  their connections rather than relying on connection garbage collection.
- Actual installed `codex-cli 0.153.4` schemas and APIs were used. In isolated local
  fixtures, native name/set, list/search, archive, archived list, unarchive, resume
  and delete all returned success through production Bridge routes. The expected
  name/archived/unarchived/deleted notifications were observed. The fixture's native
  turn deliberately had no authentication and failed; it materialized history for
  storage tests and is **not model or Houdini authoring evidence**.
- Native behavior for an unmaterialized empty thread was retained separately:
  rename/delete succeed, archive reports no rollout and restore reports no archived
  rollout. These errors remain visible; the app does not invent an archived row.
- The actual Qt manager was rendered and inspected at 460x520 and 340x450 using
  existing fonts/theme. This is an offscreen UI check, not a real Houdini GUI test.

Local evidence, not committed: `.runtime/reviews/conversations/manager*.png` and
`native/57173e19b8de4d7583bbd6911b20f0c2/report.json` (empty native thread),
`native/b074207ce6954a80bd2f358b52bc3fc3/report.json` (pinned native lifecycle), and
`native/5a2e858af3594753b825d85e09df8544/report.json` (production Bridge integration).
All fixture state/cache/history remain under this development worktree's `.runtime`.

## Open user report

[PANEL-1](acceptance-issues.md): old messages appear mixed with current Codex replies
and replies can be clipped. It remains unreproduced, unclassified and unrepaired,
as the user requested. The added deletion-only callback guards make no claim about
that existing problem. This issue must accompany the GitHub review.
