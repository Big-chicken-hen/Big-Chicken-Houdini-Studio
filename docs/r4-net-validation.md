# R4-NET-1 investigation and acceptance

The [final approval](final-release-brief.md) requires NET-1 to pass before native
steering integration and final installed-user acceptance. The original
`3150c15` failed package and [failure record](r4-validation.md) remain preserved.

## What the first correction proved

Candidate `79c1842e1693d77a96c050a6778485d069967a11` added one-terminal
delivery, copied response data before queued UI callbacks, explicit malformed
history failure, generation fencing and one bounded read-only recovery. Four
focused lifecycle faults failed against the previous implementation and passed
after the change. The 13 existing UI tests and 10 history tests passed locally.
CI run `34445856531` passed all 103 native UI tests; a separate Windows 3.10
backend job failed while its unchanged supervisor fixture read `status.json`
with `PermissionError`. CI as a whole was not green.

The actual package still failed in dedicated Houdini processes. Session
`9da3b15989774c02897de32a5e1f3164` recorded seven reply/history notices;
`f729c390cabb4b819b884efdd0552a24` recorded six. Each 90-second check retained
normal polling, two Panels, reconnect and close/reopen. In both sessions all
eight comparisons of the 14 native user/assistant messages passed canonical
source, copy source and rendered plain text checks. The draft survived. These
content checks do **not** turn either failed run into a pass.

Both sessions used the existing isolated TC3 native history in place, a HIP
copy, pinned Codex 0.153.4 and the actual packaged source. No model Turn ran.
The original native export contained two Turns and 98 items. No user state,
authentication, original HIP or global Houdini configuration was moved or copied.

## Observed reply identity failure

The first process was subsequently instrumented with scalar identities, request
paths and lifecycle state, without reading or retaining message bodies. It showed:

1. A `/state` completion read 2,310 bytes. 3.7 ms later an `/events` delivery
   referenced the same native reply address and read zero bytes. Both reported
   HTTP 200 / NoError; this was not evidence of a legitimate empty HTTP response.
2. Attach tracing showed the wrong identity already existed at `manager.get()`
   return: two unresolved requests shared one Python wrapper and native pointer.
3. A separate trace checked the input request URL. `get()` received `/events`
   but returned a wrapper whose own URL and request URL were `/state`.
4. Merely switching to `manager.finished(reply)` is insufficient. Its first
   callback also received that `/state` wrapper while `isFinished()` was false;
   the following callback received it when the actual `/state` request finished.

The production Python source never assigns one delivery's reply to another.
The selected scalar traces and allocation facts are [included for review](evidence/r4-net1/reply-identity.json).
Houdini loaded its own QtCore, QtNetwork, PySide and Shiboken; the package's Qt
DLLs were not mixed into that process. A controlled old-code regression also
failed when a real second HTTP request deliberately returned the first request's
still-active wrapper: the second callback received an empty-response failure.

## Binding boundary evidence and correction scope

A single diagnostic wrapper-map capture in the second process showed a valid
QNetworkReply registered under its main native address **and address +16**.
Read-only inspection of the installed Qt6Network DLL identified the HTTP reply
allocation as 16 bytes, including the constructor's RTTI identity. Thus the extra
binding entry is one past that actual allocation. Qt's binding map retrieves
wrappers by registered address. This supplies a concrete mechanism for a
neighboring object to resolve to the wrong wrapper; a failure-time map snapshot
of the colliding neighbor has not yet been captured.

The localized correction removes QNetworkReply from Studio's HTTP data path.
Python performs authenticated loopback HTTP in a background task; Qt receives
only copied Python results on its owning thread after transport cleanup.
Sockets retain the 45-second inactivity timeout and 18 MiB response bound.
Close shuts down the owned socket; HTTPConnection automatic reopening is disabled.
Stop uses an immediate, short-lived HTTP thread so an occupied ordinary task pool
cannot hold it behind a pending history read or input ACK. This is transport IO,
not an additional Houdini execution worker or message queue.
There is no change to Houdini's Qt installation, global binding map, icons,
history authority, message routing or runtime queue. No automatic request replay
is introduced. This correction remains subject to focused fault tests and two
fresh actual-package Houdini checks; the earlier successful content comparisons
cannot substitute for those gates.

Full local diagnostics remain under the coordinating checkout's
`.runtime/reviews/r4-final/gui/`, indexed by the session IDs above. They contain
request identity, timing and outcome facts rather than new telemetry or copied
authentication. The single wrapper-map diagnostic is not a product code path.

## Current acceptance status

The replacement's seven focused lifecycle tests and 13 existing UI tests pass,
as does Ruff. They cover aliased Qt return avoidance, overlapping reads,
duplicate completion, cleanup-before-delivery, cancellation during HTTP/1.0
body reading, lost/truncated responses without replay, invalid routes, and Stop
while the normal worker pool is occupied. Parent destruction and late queued
delivery also pass. Socket cancellation uses a bounded cancellable `recv_into`
around the standard library's HTTP parser; no custom HTTP parser or Win32 hook
was added.

Candidate `a5731cf92197f93d00f4254d469f5f37b153fa97` passed all CI jobs in run
`34449235075`. Its actual package is `0.1.0-rc.1-a5731cf92197`, with 229 files.
The two required fresh Houdini processes passed:

| Actual package run | Session / receipt | Result |
| --- | --- | --- |
| [A](evidence/r4-net1/package-a.json) | `a89dfce1e51741128a272df36cdf2339` / `59f3a4186770465dbcd219d708d7a296` | 90 s, 8 complete comparisons, zero transport notices |
| [B](evidence/r4-net1/package-b.json) | `a931f091a0b349a8b3b57a50d67638a6` / `2da534aef7f247418ad749390600b0dd` | 90 s, 8 complete comparisons, zero transport notices |

Each run used normal polling, long native history, two Panels, reconnect,
close/reopen and a preserved draft. All 224 per-message comparisons across
these 16 samples passed canonical/copy/render checks. Neither run recorded an
icon diagnostic or Panel script error. The [actual Panel capture](evidence/r4-net1/package-a.png)
was inspected; the previous TC3 partial-result warning remains visible as
historical evidence. Both owned GUI/Bridge processes were closed. Neither test
started a model Turn. No Api/reply instrumentation or transport replacement was
injected into these runs: they used the packaged production implementation.

**NET-1 passes its bounded technical gate.** Native steering and the final
Windows standard-user installed workflow remain separate gates. PR #14 stays
draft; this NET-only package is not the final release candidate and cannot
replace the final package's installed-user acceptance.
