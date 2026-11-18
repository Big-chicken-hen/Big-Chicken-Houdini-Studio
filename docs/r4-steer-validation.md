# R4 native steering validation

Recorded 2026-09-10 under the [final release approval](final-release-brief.md).
The fixed Codex 0.153.4 protocol and focused transport/Bridge tests below passed.
**Real Houdini model steering now passes in candidate `991cbce`; the final
Windows 11 standard-user installed workflow remains pending.** The actual model,
package and CI results are in the [frozen candidate record](r4-final-candidate.md).
The controlled results below remain separately identified.

This records the steering changes in `codex/windows-release-package`, PR #14,
on the implementation worktree based on `58923ca3c2000424132cae8d2e6eb99451460062`.
The native protocol/Bridge implementation is committed at `690362f`, original-account
recovery at `af5ee27` and Panel integration at `8292367`. Candidate `991cbce` includes
these changes; all five CI jobs passed. Its source/builder commit and exact installer
identity are recorded separately; no earlier package is the final steer candidate.
The separate [NET-1 validation](r4-net-validation.md) preserves its completed
package checks and original failure evidence.

## Actual fixed binary, controlled local provider

Both experiments used the actual native Codex binary from the NET-only package
`0.1.0-rc.1-a5731cf92197`, with Codex remaining **0.153.4**. A local Responses
fixture held and released responses to establish native Turn boundaries. Each
experiment used fresh dedicated state/cache and native cwd under the coordinating
checkout's `.runtime/reviews/r4-final/`; neither used a real account, external
model nor Houdini. Their results establish native protocol behavior, separately
from the Python transport/Bridge faults below and from model quality.

| Experiment | Observed result | Evidence |
| --- | --- | --- |
| Ordinary Turn | Three sequential steers with equal text and distinct client IDs all returned the original Turn ID. Native history retained the start ID and three steer IDs once each, in order; exactly one `turn/started` was observed. | [Native ordered inputs](evidence/r4-steer/native-controlled.json) |
| No active Turn / wrong target | Native rejected steering before a Turn, with an incorrect expected Turn ID, and after the original Turn completed. There was no fallback start. | [Same report](evidence/r4-steer/native-controlled.json) |
| Active Review | Native returned `-32600`, `cannot steer a review turn`, with `activeTurnNotSteerable.turnKind = review`; the controlled Review then completed. | [Special Turn refusals](evidence/r4-steer/native-special.json) |
| Active manual Compact | Native returned `-32600`, `cannot steer a compact turn`, with `activeTurnNotSteerable.turnKind = compact`; the controlled Compact then completed. | [Same report](evidence/r4-steer/native-special.json) |

The special-Turn fixture additionally checked `codex-cli 0.153.4` and recorded
closure of its owned native process and local HTTP worker. `review/start` and
`thread/compact/start` were enabled only in that fixture's policy to create the
test conditions; neither was added to the product allowlist. The fixture client
IDs are native protocol test inputs, not Studio's generation-prefixed IDs.

The [evidence inventory](evidence/r4-steer/README.md) identifies the original runs
and exact report transformation. No complete user/model messages, provider
payloads, authentication or raw native histories were copied into the repository.

## Focused implementation tests

These are controlled Python tests with temporary project-local state. They do not
run a real model or Houdini. Counts refer to the completed local runs at this
checkpoint, not to a claimed final candidate CI run.

| Test file | Passed | Main coverage |
| --- | ---: | --- |
| [Tracked stdio requests](../tests/test_codex_tracked_requests.py) | 11 | One frame per ticket; frozen input; timeout plus original late ACK; partial write/flush uncertainty; ACK precedence; callbacks outside client pending/write locks; process replacement, concurrent results, capacity/expiry and exact-item retirement. |
| [Versioned native contract](../tests/test_native_steer_contract.py) | 5 | Start/steer client identity fields; steer-only parameter surface; exact 0.153.4 rejection mapping; contradictory, wrong-version and generic errors remain unclassified. |
| [Bridge admission and recovery](../tests/test_bridge_steer.py) | 14 | Sequential equal-text inputs; duplicate/conflicting IDs; Stop during ACK wait and before forwarding; start/steer route fences; terminal before ACK; unchanged approval/settings/Runtime ownership; original-account/Thread recovery; stale connection/read rejection; durable snapshot faults. |
| [Existing Panel](../tests/test_ui.py), [Composer](../tests/test_ui_composer.py), [activity](../tests/test_ui_activity.py), [model settings](../tests/test_ui_model_settings.py) | 44 | Existing drafts, decisions, images, approval, receipt status and model controls; assertions updated for independent Send/Stop and exact native identity instead of matching text/images. |
| [Bridge recovery](../tests/test_bridge_steer_recovery.py) and [Panel recovery](../tests/test_ui_steer_recovery.py) | 8 | Restart with a different account counter, wrong account with the same counter, no selected Thread, original-ID read-only reconciliation, late account/history responses and preservation of the later draft. |
| [Composer steering](../tests/test_ui_steer.py) | 11 | Same-Turn ordered inputs, immutable snapshots, exact clientId, ACK/item/terminal ordering, independent Stop, IME preedit, active model images, approval boundaries, A/B/A and archived/deleted late results. |

The Client suite and Bridge suite each exercise **18 successive inputs with
missing RPC ACKs but exact native-item confirmation**. Confirmed inputs release
the RPC association and waiter, so the bounded unresolved-ticket store cannot
become a per-Turn send quota. Unknown inputs continue to block new admission.
This is fault-injection evidence; the actual native experiment above exercised
three accepted steers with normal native replies.

Cross-review and targeted fault tests identified and corrected two issues before
this checkpoint: confirmed native items formerly left old RPC tickets occupying
capacity, and a rejected admission could overwrite an unreadable pending-input
file after its storage fault was set. The latter test now preserves the original
bytes and verifies that no user-input frame is forwarded. Recovery tests also
keep an absent item unknown, reject a different account before reading history,
and ignore a read whose connection generation or account revision changes.

The Client/contract checks and focused static checks passed; the Bridge author
reported its 14-test pass and its recovery/retirement implementation was separately
reviewed. No GUI test or final installed-workflow pass is inferred from those runs.

## Send identity and late-result contract

The consumed fields and pinned upstream source are documented in the
[0.153.4 contract](../contracts/codex/0.153.4/README.md). `clientUserMessageId`
correlates with native `userMessage.clientId`; it is **not** a native idempotency
or retry guarantee. Equal text does not establish message identity.

Studio freezes start versus steer at the send boundary. It checks the current
connection/account/Thread and, for steer, the expected active Turn and Stop state
immediately before writing the prepared frame. Native `turn/start` can internally
steer, so Studio also retains its separate start-only admission checks. The Bridge
releases its admission locks before waiting for the original RPC response.

The same Studio message ID can return its existing record or a conflict; it cannot
write a second frame. The generation is part of that ID, so a reconnect cannot
rebind an old ID to a new send. Unknown snapshots remain in the bounded workspace
`pending-user-input.json` across reconnect/restart. Explicit recovery reads the
original Thread under the original account identity and verifies its workspace;
it does not resume, switch Thread, replay input or treat an absent item as rejection.

Only a matching native success or an exact native item establishes `accepted`.
Only a pre-forward refusal or a proven fixed-version native admission refusal
establishes `not_submitted`. Possible forwarding with no confirmed result remains
`unknown`, including generic RPC failures, process loss and timeouts.

The client retains at most 16 unresolved RPC associations for five minutes, with
expiry checked on later activity. Expiry reports uncertainty and does not discard
the Bridge's unknown input or authorize retransmission. After the Bridge records
exact native-item acceptance, `retire_confirmed()` releases the old association
and wakes its waiter with `CODEX_REQUEST_EXTERNALLY_CONFIRMED`; it creates no RPC
ACK/result callback. The Bridge returns its existing acceptance fact. A later ACK
is ignored for that retired ticket.

Acceptance does not establish that guidance has affected model reasoning or HOM.
Late ACKs cannot revive a terminal Turn, cancel Stop, restore a stopped Runtime
owner or clear a newer draft. Already accepted records are not downgraded by a
later transport error. Unneeded accepted payloads are released; unresolved
payloads and their uncertainty remain available for explicit reconciliation.

The Panel keeps an ACK-accepted frozen draft in memory until its exact native
item arrives; ACK alone already releases the next-send gate. This is proportional
to acknowledged inputs not yet echoed, not a per-Turn quota or second timeline.
Only pending/unknown snapshots reach the existing workspace state file. Text,
attachments and selection are frozen independently of the user's next editable
draft. Native IME preedit is inspected without overriding Qt input events; sending
or restoring a rejected draft cannot clear uncommitted candidate text.

An independent integration review found that a persisted account revision alone
cannot identify the account after process restart. The Bridge now verifies the
original account identity before exposing an unresolved payload, and supplies a
current connection/account binding for read-only recovery. Original message ID,
generation and revision never change. Even without a selected Thread, the existing
pending-input area can query that original ID without resume or switching; another
account sees only the unresolved-input blocker. Account changes retire the old
query/history callback without changing later drafts.

## Remaining release gates

| Gate | Current status |
| --- | --- |
| Fixed-version native ordinary/special Turn behavior | Passed as controlled protocol evidence above. |
| Focused Client, contract and Bridge faults | Passed locally; all candidate CI jobs passed at `991cbce`. |
| Integrated Composer/Panel acceptance | Focused offscreen integration passed (tables above); real host/model checks remain separate. |
| Real Houdini 22 model steering | **Passed.** Two additions accepted through normal Composer in the original Turn; three native inputs once each; all original wall/window/reference objects unchanged; 0.25 m eaves and symmetric 35-degree pitch. See the actual model/receipt/Panel evidence in the candidate record. |
| Final steer-enabled package | **Built and frozen.** `0.1.0-rc.1-991cbce9c90e`; source/builder/lock/SHA-256, package integrity and matching CI are recorded. |
| Windows 11 standard-user installed workflow | **Pending.** Use that same final package for official login, authoring with working-time steer, images, Save As/reopen/resume, diagnostics, upgrade, uninstall and retained data. No development-account substitute or copied authentication. |

PR #14 remains Draft until the standard-user gate passes. This document does not
authorize release or mark the unavailable standard-user environment as tested.
