> **CLOUDCLI / CLAUDE CODE RUNTIME ACCESS:** Do not report that NAS or Home Assistant access is unavailable merely because no Home Assistant plugin, Desktop Commander, direct SSH surface, or direct NAS tool is present. Read `AGENTS.md` → **Canonical runtime access — including CloudCLI/Claude Code** and use the GitHub-mediated NAS Control path through `golgoth85/nas-control` / `main`, submitting runtime requests exclusively as owner-authored GitHub Issues according to `REQUESTS.md`. This note does not authorize starting CloudCLI where explicit user authorization is still required.

# CLAUDE.md

> **MANDATORY EXECUTION POLICY (2026-09-25):** Before doing any work, read and follow `AGENTS.md` at the repository root. Its GitHub-first, operator-minimal workflow policy has priority over older local/manual workflow instructions in this file. CloudCLI requires explicit prior user authorization and is reserved for coding/debugging that genuinely needs the real environment. Remote Desktop Commander is a last resort only when indispensable. The current phase/scope boundaries still control what actions are allowed.

Project-specific behavior is defined by the repository code, README/docs, and any more specific nested agent instructions. When instructions conflict on execution mechanics, `AGENTS.md` controls.

## Mandatory Local CI policy

For ordinary development testing and validation, this repository follows `LOCAL_CI.md` and `golgoth85/local-ci-lab/docs/LOCAL-CI-ADOPTION-POLICY.md`. Local CI is the default. Do not silently introduce or restore automatic GitHub-hosted development CI. Retained hosted workflows are manual fallback only during migration. Untrusted source must execute only inside the disposable I3 sandbox, never directly on a persistent credential-bearing runner. Release/publish/deploy with credentials remains a separate trusted boundary.
