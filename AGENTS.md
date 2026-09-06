# Big-Chicken Houdini Studio development

This is a new repository. The old HIA checkout is reference material, never a write target.
The architectural acceptance briefs are `docs/pro-diagnosis.md` and `docs/stage-readiness-review.md`.
Read `docs/rebuild-brief.md` before changing a subsystem. Do not replace this effort with a generic agent platform.

- Resolve the installation root from this checkout or HIA_PROJECT_ROOT. Installation resources and dependencies remain under it. Normal user state and disposable cache use separate platform roots, resolved by the launcher and passed explicitly to children. Preserve containment for each root. Development fixtures, previews and logs stay in this checkout's .runtime; tests must never use real user state.
- Existing .runtime workspaces, native history, authentication and referenced artifacts are durable legacy data. Access them explicitly in place; do not automatically move, delete, renumber or rewrite them. Saving or renaming a HIP does not move its active workspace, ledger or native cwd.
- Preserve all user data and unrelated changes. Do not reset, clean, delete, move or overwrite user files. Use short-lived branches and commit only owned files; preserve public main history.
- Never modify the Houdini installation or user configuration. The launcher supplies child-only environment settings, project-local Houdini preferences and temporary directories.
- All local services bind 127.0.0.1 and use a fresh launcher-session token. Do not put tokens in files, command lines, results or logs.
- Codex is the only reasoning/content system. Keep native Codex Thread/Turn history and automatic compaction. No second agent, planner, recovery prompt generator, automatic memory or summarizer.
- The runtime owns scene identity and operation receipts. Validate observed scene_epoch inside the main-thread execution callback. Never silently refresh an observation before a write.
- Persist receipts before responding. Re-query operation_id; never replay scripts to recover a missing response. General HOM external effects are unknown and automatic_retry_safe is false even after Undo.
- All scene reads/cooks/captures/writes share one bounded queue. Health reads cached state without HOM. Codex Stop and Houdini execution are distinct facts.
- Keep checks targeted and optional. No mandatory lookup, whole-scene snapshot, screenshot or repeated validation for deterministic edits.
- Knowledge import/FTS and explicit workspace decisions are independent of live Houdini and never block startup. Do not index plugin-development documents as default scene knowledge. No embedding dependency in the core release.
- Panel and launcher must be substantially new interactions and layouts, not a skin over the old UI. Panel projects facts; it does not infer HOM completion from Codex events.
- Launcher and Panel follow docs/ui-presentation-brief.md and the user's explicit corrections. Product icons use only the approved Lucide Outline 0.468.0 SVG subset at f12b0de177fbc2a6795e99be065887e72b237123, with original geometry and bundled license notices. No custom icons, graphic logo, emoji or QStyle.SP_* product fallback; missing icons fall back to text. Native OS dialogs and title bars keep their system icons. Do not add unapproved controls, a legacy-context browser or profile-switching UI.
- This PR's presentation correction does not reopen storage, native protocol, permission policy or Houdini capability scope. Page transitions project existing facts and cannot create a probe, login or launch. Keep PR #5 draft until its real official-login and ordinary Houdini Panel acceptance is complete; do not transfer that gate to another PR.
- Do not control Houdini with Computer Use. Native Qt offscreen UI review is allowed for development, and does not constitute a real Houdini GUI test.
- Use a small meaningful fault-test set, one static check and focused UI checks. Do not repeatedly run full test suites, compute arbitrary hashes or create process-heavy verification scaffolding. Report what is actually verified and what remains unverified.
