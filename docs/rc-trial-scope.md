# RC trial scope and user correction

The [new Pro audit](rc-trial-review.md) authorizes daily RC trials and a package for
named external testers. PR #14 remains Draft until the standard-user workflow and
final Pro Go. The earlier `991cbce` candidate remains preserved as rollback/evidence.

The user's direct correction takes precedence over the audit's proxy wording:

> Clash 是一定要的，但是端口号用户的可能不同，pro模型说的关闭clash测试啥的不需要。

For this trial, a working user-configured Clash connection is a prerequisite for
external Codex services. Each user keeps their own address/port and account.
Studio uses native Codex's existing system/environment routing; it never injects
the developer's proxy port, installs/configures Clash, changes global proxy
settings or silently bypasses a bad external proxy. No Clash-off or no-Clash
environment test is required or performed. Internal authenticated IPv4 loopback
stays direct. Focused test-process proxy-variable fixtures use only local test
servers and test tokens; they do not change the user's Clash or global environment.

Authorized product changes are limited to shared Houdini compatibility policy,
explicit Untested launch confirmation, bundled/explicit Codex provenance and
missing read-only identity facts in existing details/diagnostics. Preserve exact
Codex 0.153.4, native Qt/icons, HTTP implementation, Tool Surface, prompts, consent,
history/steer, queue and receipt semantics. Actual host facts are collected once
at normal registration, not added to every model context or operation.

First inventory the Owner environment read-only. Preserve data, authentication,
referenced paths and all release evidence; do not automatically migrate old roots.
After the bounded product changes and targeted regression/CI pass, build and freeze
a new RC with its own source, builder, build ID and checksum. Prepare one tester
directory with the installer, sidecar and two short Chinese instruction/result
documents. Sending to named testers is permitted; public release is still gated.
