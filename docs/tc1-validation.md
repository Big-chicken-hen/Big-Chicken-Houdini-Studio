# TC-1 validation and remaining acceptance

Status: implementation and isolated preparation are ready for review. **The paired
model authoring test has not run; this PR is not ready to merge.** On 2026-09-08 the
user deferred the isolated official login and asked to finish the remaining preparation.

The governing scope is [tc1-brief.md](tc1-brief.md). Baseline main is
`1e9f0f4dc43465bd221b3e0832a5e75d6cd1aa66`, rechecked against origin/main on 2026-09-08.
Candidate code is this PR's feature commit; pin its SHA before the paired run.

## Source and protocol checks

The focused regression run passed 62 tests in `test_inspection.py`, `test_lookup.py`,
`test_operations.py`, `test_capture.py`, and the first 18 TC-1 tests. After adding the
receipt/detail and evidence-counting cases, the final TC-1 run passed all 20 tests.
Together these cover 64 distinct tests. Ruff passed for `src`, `scripts`, and `tests`.

Covered behavior includes:

- Production stdio dispatcher → Adapter → operation queue for canonical and legacy
  metadata inputs. Malformed and mixed branches, missing required fields, and boolean
  integers reject before admission. The seven tools and MCP protocol version stay unchanged.
- Label/alias discovery, deterministic paging, hidden/deprecated filtering, unknown
  lifecycle states, absent replacement metadata, and exact legacy-type queries.
- Parameter discovery without value evaluation or dynamic menu execution; values
  evaluate only the requested page. Ordinary per-view/per-parameter failures remain
  visible alongside successful results. Failed execution pre-observations block mutation.
- Useful large summaries, including a 32-view batch, retain identities and actual rows.
  Returned cursors refer to the first row not sent. Sanitized raw detail remains available
  through the same receipt; static HOM results do not promise an operation receipt.
- Bounded local/embedded help, selected archive member reads, explicit missing/oversize/
  invalid/outside-root/network-target outcomes, and redaction before help pagination.
- Existing receipt, scene epoch, lost-response/no-replay, Stop, and capture-restore faults.

These tests exercise controlled fake HOM and protocol fixtures. They do not establish
model-side usage, Houdini GUI appearance, or the authoring quality gate.

## Real Houdini execution

An isolated hython run used **Houdini 22.0.368** and preferences under the checkout's
review directory, with the required `__HVER__` token in `HOUDINI_USER_PREF_DIR`.
The successful run verified:

- Actual installed categories and keyword metadata; exact Box and existing legacy Copy
  type metadata; their actual built-in help text from the installed `nodes.zip`.
- Installed lifecycle/deprecation facts and the installed replacement identity returned
  by HOM. No type blacklist or recommendation table was introduced.
- A temporary HDA's actual embedded Help section and registered alias. A later query
  reflects definition removal instead of cached Help. Houdini may retain an undefined
  type entry after uninstall, so registry presence is checked against current HOM.
- Real connection source/output/input indices, child pagination, `height#` template
  versus `height1`/`height2` instances and values, and object-local geometry bounds for
  a nondefault OBJ transform.

The four-item metadata read took about **0.105 seconds** in this one local run. This is
a backend timing observation, not an end-to-end latency or efficiency claim.
The local evidence is `.runtime/reviews/tc1/backend-houdini.json`; the isolated probe
script and its earlier observations remain beside it. Raw local evidence is not published.

## Dedicated authoring fixture

[`scripts/tc1_fixture.py`](../scripts/tc1_fixture.py) creates only
`.runtime/reviews/tc1/fixture/source.hip`, refusing to overwrite an existing fixture.
It has an uneven curved walkway, an existing guide curve with an editable adjustment,
two existing post modules with parameter/multiparm controls, two materials, a camera,
an unrelated preserved asset, and a position marker for round two. Walkway and guide
objects have nondefault transforms. **There is no target railing network.**

The fixture was saved, then loaded and cooked in a fresh H22 process: **21 nodes,
zero node errors**. This checks input integrity, not final railing quality. No GUI
capture or model-side visual review has been performed for this fixture yet.

## Resume procedure after isolated login

1. Use the local `Start TC1 Acceptance.vbs` under `.runtime/reviews/tc1` for the ordinary
   official login. Its data and cache roots are `acceptance/state` and `acceptance/cache`.
   It uses the existing Codex **0.153.4** executable. Do not copy, reset, or move normal
   account/history data. The user has deferred this step for now.
2. Freeze the candidate SHA. Prepare baseline and candidate copies of the same fixture,
   distinct workspaces and fresh native Threads, with the same H22 build, native Codex
   executable, model and effort. Record advertised and actually confirmed model settings.
   Use the ordinary production Bridge/Runtime/tools; do not pass this brief or an expected
   node list to the authoring model. Keep all test state inside this checkout's review root.
3. Send the first natural-language task verbatim from the approved brief. Keep the complete
   native response, operation receipts and overall/local visual results. Record wall time
   at turn submission. If the model requests extra approval, preserve that request for
   review; do not silently grant unrelated privileges or manufacture a successful result.
4. Save a round-one HIP snapshot. Through a separate, recorded tester operation, apply
   `move_curve()` from the fixture script: move existing guide points 29–36 by local
   `(0, 0, -0.5)` and select the opening-location marker. This changes the existing curve
   without building or correcting any railing. The tester operation is excluded from
   model-call counts. Stay in the same native Thread/HIP and send the second approved task.
5. Save the round-two HIP and full history. In a fresh load, inspect/cook the completed
   network and verify actual geometry, controls, original assets/materials/camera,
   preserved artist delta, continuity of the original network and the real opening.
   Review images and the model's use of their evidence; node presence alone is insufficient.
6. Export `Bridge.read_thread()` to a local JSON file and run
   `scripts/tc1_evidence.py THREAD_JSON RECEIPT_DB`. It reads the dedicated review inputs
   without writing the ledger. It counts native model MCP items once, distinguishes
   inspect views and metadata requests, and correlates receipt timings. HTTP polling and
   unrelated tester receipts do not inflate counts. Review API guesses, unnecessary
   roundtrips and first useful action latency manually; the script leaves them unverified.

Keep both complete runs, including failures. Publish only the minimal sanitized comparison.
The approved efficiency/quality alternatives are still **unmeasured**: 20% fewer discovery/
observation calls at equal quality, eliminating baseline API guesses without more total
calls, or completing both rounds where baseline fails with no obvious avoidable roundtrips.
After all gates pass, request Pro review. **Do not merge on the basis of these preparations.**
