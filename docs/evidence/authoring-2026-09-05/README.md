# Authoring evidence — 2026-09-05

[runtime-faults.json](runtime-faults.json) contains explicitly selected receipt fields from developer-assisted Houdini 22.0.368 GUI fault runs. All three main source reports still say running; these are individual case records, not an overall acceptance pass. The source reports do not identify the executing commit SHA. This evidence does not replace a cold user workflow.

The cases cover surviving runtime ownership, queued cancellation, same-HIP reload epoch rejection, a deliberately discarded admission response, native capture dimensions/frame evidence, and reading an old native image from a different runtime.

Supervisor evidence limitation: 原始报告记录持有Popen句柄kill+wait、实际PID退出独立观察未包含。The kill/wait method is supplied by the lead; the source JSON event itself contains a terminated-PID annotation.

The fractional-frame mismatch and original image precede the frame-evidence follow-up. Operation 948f187b0add4fd88f2a9944304b2642 is a separate later capture recording configured_frame_range.

The original PNG for artifact 6d9da7b0740542f4a84999caba2a20a3 contains local machine username metadata in its Artist field, so it is not included in this public bundle. The original remains in the private .runtime artifact directory without transformation or re-encoding. The original manifest records 640 × 480 pixels, 126934 bytes and an existing digest; that summary is retained in the JSON only for correlation, and no new digest was computed. This bundle contains no public image for independent visual verification.

Only selected result fields are published. Workspace paths are represented by the workspace placeholder. Operation, runtime, scene epoch and artifact IDs remain available for correlation.
