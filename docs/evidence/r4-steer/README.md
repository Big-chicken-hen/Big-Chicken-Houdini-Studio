# R4 steering evidence inventory

These are reviewed copies of completed **actual Codex 0.153.4 + local controlled
Responses provider** reports. Both explicitly record `real_model: false` and
`houdini: false`. They contain protocol identities, native rejection errors,
counts, event method names and pass/closure flags, not complete user/model
messages, request/response content, credentials or authentication state.

| Repository file | Original coordinating-checkout report |
| --- | --- |
| [native-controlled.json](native-controlled.json) | `.runtime/reviews/r4-final/native-controlled/3a48e14fef1743a89bd78bf91088981b/report.json` |
| [native-special.json](native-special.json) | `.runtime/reviews/r4-final/native-special/e8e731f1694d4956bc00d69231f8416f/report.json` |

The only content transformation removes each original absolute `run` path and
adds its relative `source_report` path. JSON whitespace is normalized; all other
values are preserved. The original reports and isolated native stores remain in
place. Runtime fixture scripts are `native_steer_smoke.py` and
`native_steer_special_smoke.py` under `.runtime/reviews/r4-final/` in the coordinating
checkout. They are development fixtures, not installed product features.

The ordinary report proves three same-Turn steer acknowledgements and ordered
exact client-ID history; the special report proves actual Review/Compact
refusals without expanding the product method surface. See
[validation status](../../r4-steer-validation.md) for the separate Python fault
tests and the still-pending real Houdini/model and final standard-user gates.
# Final integrated evidence

Candidate `991cbce` adds `roof-model.json`, `roof-messages.json` and `roof-panel.png`
from real Houdini session `1a1837ae02d44a34a006a749d2572b02`; the raw native history,
HIP, full tool scripts and local receipts remain in the owned review directories.
`final-package-history.json` is the additional 90-second final-package NET regression
in fresh session `782443b4e1fb401f8a7f35464f31c129`. `candidate-ci.json` records all
five job results; `final-package-check.json` selects nonprivate fields from the
single actual-package diagnostic check. No results were replaced or fabricated.
See [the final candidate record](../../r4-final-candidate.md) for exact scope.
`roof-fresh-load.json` retains the separate H22 reload/geometry/control checks and
process record; the full per-face/point measurements stay in its named source report.
