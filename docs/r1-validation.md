# R1: native message identity, history recovery and complete reading

Scope follows [Release Readiness](release-readiness-brief.md). PR #10 technically
merged at `890284bd7b51c484244181542dd4b059ce4fa7ca`; all original TC1/TC2/TC3
model results and quality gaps are unchanged. R1 contains no tool expansion,
prompt changes, theme redesign or package/release claims.

## Original evidence and causal limits

The four original run directories in [model results](model-acceptance-results.md)
were read in place: native exports, complete event logs and original receipt/detail
exports. All eight turns contain 39 agent-message terminal items (10/10/7/12).
Their native terminal text equals their stored native history text. No missing
start or cross-turn item-ID reuse was found in those recorded streams. The audit
is `.runtime/reviews/r1/original-record-audit.json`. These runs did not record the
original user's Panel state, so they cannot establish that user's unique cause.

Before production edits, `tests/test_ui_projection.py` failed four controlled
regressions against `890284b`: a late completed-turn summary overwrote terminal
text; a non-atomic active snapshot suppressed the rest of a continuous stream;
two turns sharing an item ID collapsed into one card; and complete long text was
limited to 1600 display pixels with a second vertical scrollbar. The last finding
is a reading issue, not proof of lost native characters. The original failure
record remains in `.runtime/reviews/r1/before-regression.json`.

One retained actual TC3 native terminal item was also passed through production
Bridge and Transcript before applying a controlled late summary. The old code kept
the native/Bridge item intact but replaced reducer/copy text; the corrected code
retained all three. Complete native item, Bridge event, controlled history,
canonical before/after, copy source and rendered plain text are in
`.runtime/reviews/r1/chain-before/chain.json` and `chain-after/chain.json`.
This is a reproducible projection failure using original content and a controlled
delivery schedule, not a claim to have reconstructed the original user's session.

## Corrected projection and native history contract

The memory-only projection uses connection generation, Thread, Turn and Item.
Terminal native items outrank snapshots. A complete stream observed from start
remains continuous while history loads; a missing start or transport gap is marked
recovering without guessing a prefix or appending an overlapping tail. Summary and
notLoaded views cannot replace full bodies. Delivery sequence deduplicates events;
equal text in distinct events/items remains legitimate. Old history requests,
connections, deleted/archived Threads and retired image/layout callbacks are fenced.

Native Codex 0.153.4 was probed against the actual stored TC3 conversation. Both
thread/turns/list and thread/items/list succeeded, including native cursor and
Turn filtering, with experimentalApi false and true. Production keeps its existing
false setting and adds only these two methods to the allowlist. Original responses
and capability results remain in `.runtime/reviews/r1/native-pagination-probe.json`
and the adjacent method response files.

Normal opening loads a recent native page; older pages are requested explicitly.
Recovery targets a Turn. The item-page response has no Turn status: only a native
terminal fact already observed before that read can mark its snapshot terminal.
A Turn-completed event received during an older active read cannot promote that
snapshot to final. Unsupported methods are remembered for the connection, with a
bounded displayed page from the existing read fallback. Its cursor anchors a
native item/Turn ID, so new incoming history does not shift an offset. Native
history remains the only persisted chat source.

Panel receives events during history reads and does not buffer/discard their
content. Only Markdown drawing is coalesced over 50 ms; canonical source changes
immediately and terminal items flush immediately. A 100-delta fixture retained all
text with one Markdown update. Long text uses the outer timeline scrollbar and
offers a context-menu action to copy its complete source. Selection and reading
anchors are retained across streaming updates. No raw-versus-rendered Markdown
comparison is used as a loss detector.

Native lifecycle and page semantics are cross-checked against the fixed generated
schemas and the [official App Server documentation](https://learn.chatgpt.com/docs/app-server).
Qt document replacement behavior is described in the
[QTextEdit documentation](https://doc.qt.io/qt-6/qtextedit.html).

## Validation boundary

Focused reducer/history faults, Panel races, long-text rendering, existing model
settings/composer/conversation behavior and Bridge checks pass. Ruff is the static
check. The real Houdini Panel run is still pending; these offscreen checks alone do
not close PANEL-1 or authorize public release. R2/R3/R4 remain separate stages.
