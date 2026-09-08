# Approved native conversation lifecycle

The user's Pro review of 2026-09-08 approves this independent small PR on
`codex/native-conversation-lifecycle`, separately from TC-3 staged authoring.
The rendering proposal is withdrawn. TC1-A1 and TC2-A1 remain independent frozen
experiments; neither is replaced by this change.

Use the actual Codex 0.153.4 generated schemas for native thread/list cursor,
title-only searchTerm, archived filtering and updated_at sorting; reuse
start/read/resume and add name/set, archive, unarchive and delete. No conversation
database, full-text search, history rewrite, alternate tree or cross-workspace move.

Validate workspace and target identity. Restore model/effort from native resume.
Keep drafts and attachments thread-owned, and reset conversation consent on switch
or restart. Native delete needs explicit irreversible/descendant confirmation.
Do not delete the current thread while its turn, approval response or related
Houdini operations remain unfinished or unknown. Only confirmed native success can
remove the corresponding Panel draft/selection. Never delete workspace receipts,
captures, HDA files or scene outputs by thread ID.

Handle noncurrent native lifecycle notifications. Request generations must reject
late list/selection responses for deleted conversations. Reconcile unknown native
results without replay; absence from a list does not prove deletion.

The approved page structure, fonts, pink direction, Lucide assets and PySide6 remain
unchanged. The user-reported message mixing/truncation issue remains **record-only,
unreproduced and unrepaired** as [PANEL-1](acceptance-issues.md). This PR does not
diagnose it or modify message delta/history reconciliation.
