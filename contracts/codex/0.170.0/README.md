# Codex 0.170.0 native integration

[integration.json](integration.json) contains the fields Studio consumes from
`codex app-server generate-json-schema` on the official Windows x64 binary at
OpenAI commit `29eb79e9866b3262a777fdf8195c1b9e63684c91`. Each request excerpt
has its own definition references. The exact binary remains enforced by
Launcher preflight. [Upstream release](https://github.com/openai/codex/releases/tag/rust-v0.170.0)

`model/list` returns the account's visible models, opaque cursors and the
model's supported and default reasoning efforts. The native effort schema
allows any nonempty string. Studio validates the selected effort using the
individual catalog row. The public request surface retains the existing model,
account, Thread, Turn and approval methods.

The existing steer request sends the clicked Thread and expected Turn, a client
message ID and the input list. Native success identifies the original Turn.
`userMessage.clientId` correlates the input with native events and history.
For a definite native refusal, Studio uses the exact supported-version error
forms. Possible forwarding without a confirmed result remains unknown and
requires read-only reconciliation. [Upstream steer handler](https://github.com/openai/codex/blob/29eb79e9866b3262a777fdf8195c1b9e63684c91/codex-rs/app-server/src/request_processors/turn_processor.rs#L1114)

The [0.153.4 contract](../0.153.4/README.md) records the first public preview's
protocol. See the [RC2 validation](../../../docs/rc2-model-catalog.md) for the
catalog comparison, persisted Thread upgrade and package checks.
