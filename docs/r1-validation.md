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
A full terminal history item can also finish a previously continuous stream when
its terminal events are missing. An additional focused regression exposed and
corrected this boundary before R1 closure; active snapshots still cannot do so.

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

## Real Houdini Python Panel acceptance

The driver loaded the production `big_chicken_studio` Python Panel interface in
Houdini 22.0.368, with its native Qt 6.8.3, production Bridge and authenticated
isolated Codex 0.153.4. Actions called the production Panel methods through the
existing main-thread queue. There was no Computer Use, extra scene executor or
model authoring benchmark. This verifies real host content/layout; it does not
claim another physical mouse, IME or cross-monitor acceptance.

All state remained in the explicitly reused TC2 acceptance root. New workspace
`44e6c4da744a4a4bb99eda69bd87873c` owns these tests. Its native cwd, ledger and
histories stayed in place across fresh test processes; no authentication directory
was copied, production state accessed, or previous experiment changed.

| Source | Owned GUI session under `.runtime/reviews/r1/gui/` | Evidence |
| --- | --- | --- |
| `d5ba005e9a4811cab0f7d88530d2792e7e26f8f8` | `fda8f606e49846ec871224953716dcd0` | Two live A turns, streaming reconnection, new B turn and A/B/A; native/Bridge logs, source/copy/render dumps and 540/360-pixel Panel captures. |
| `e51272583bc22695439cae64e517a5d732f78ba2` | `eed0132e5d92407f937048c4a1ea07c7` | Fresh process, corrected new-empty-thread metadata behavior, then stored A/B/A recovery through actual native pagination. |
| `c631342f7216dca607eb2df9793b02ca551eeb41` | `0736ae0e05234a08a453b7580f564ab5` | Fresh final-code Panel. Original native start/deltas replayed while terminal events were withheld and an actual native history response delayed. Releasing full history restored the exact final body/copy/end marker. |

Native A is `01a084d9-13a8-7181-a4a7-824d604aaeae`; B is
`01a084dc-5dee-7580-afed-af1804a1612a`. The three new native turns confirm
`gpt-6-astra`; effort is null/native default and is not relabelled as a measured
reasoning level. They made zero MCP calls. The first A reply was 27 characters;
the second contained 3310 characters, 100 numbered entries and a 40-line Python
code block ending `R1_A2_END`. B contained only its expected independent reply.

The live reconnection occurred after 66 characters of A's second reply, changing
Panel connection generation 1 to 2. The final reply, its source-copy accessor and
its independently rendered Markdown all matched native content. Its measured body
height was 2265 pixels, beyond the former cap, with inner vertical scrolling off.
Both normal and narrow real Panel captures visibly contain the final marker.
Returning from B restored both A turns without B items.

The first live run also exposed a new-thread history response:
`thread … is not materialized yet; thread/turns/list is unavailable before first user message`.
Its original failure remains in that session's `history-failures.jsonl`. The fix
reads native metadata only for this confirmed lifecycle condition; it does not
disable pagination for later materialized history. The second session verified
`history_source: metadata`, `history_available: false`, no error and the message
"对话尚无已保存的消息，可继续发送。" Stored A/B pages then succeeded via
`thread/turns/list` in the same connection. No empty history was fabricated.

`panel-comparison.json` independently compares eight saved views (26 item-view
comparisons): exact Thread/Turn/Item set, full canonical text, complete copy source,
and Qt Markdown rendering from the native source. All pass. Plain rendered text
may normalize Markdown line breaks, so it is compared with an independent
QTextDocument projection rather than raw Markdown bytes. `native-chain-summary.json`
also confirms all three native terminal items equal their projected Bridge items.
The final controlled recovery's before/after source and assertions remain in
`0736ae0e05234a08a453b7580f564ab5/missing-terminal-recovery.json`.

Actual images were opened and inspected: first-session `a2-panel.png` and
`restored-a-panel.png`, and final-session `source-final-a-panel.png`. Original
exports, intermediate failures and runtime operation receipts are retained. All
three owned Houdini/Bridge processes closed after capture; user processes were not
terminated or selected by process name.

## Validation and disposition

Nine reducer cases, seven native-history cases, ten Bridge cases and 56 focused
Panel/history/composer/model/conversation checks passed. Ruff is the static check.
Initial CI exposed a fixed 70 ms drawing-wait assertion on its slower UI runner;
the test now waits for the actual render event and still verifies one redraw for
the burst. Production timing was not changed to satisfy that test. The original
failed run remains `34318858276`; corrected code heads `e512725` and `c631342`
passed all five CI jobs (runs `34319801816` and `34320203607`).

**R1's technical merge gate is met.** The reproducible projection/ownership and
complete-reading defects tracked by PANEL-1 are fixed and passed real host
regression. The original user's exact version/event sequence remains unestablished;
that limitation and the original report are retained, not rewritten as observed
native data loss. Public release still requires R3/R4's actual-package user flow,
including message integrity and the other explicit release gates. This R1 result
does not authorize a public release or substitute for those later checks.
