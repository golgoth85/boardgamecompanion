# AGENTS.md

## Mission

BoardGameCompanion is a self-hosted Docker/Unraid application for managing a physical board-game collection, locating and archiving rulebooks, and querying those documents with RAG.

## Non-negotiable domain rules

1. The BoardGameGeek `objectid` is the canonical external identifier when known.
2. The application must work without a BGG API token. BGG CSV import is a first-class path.
3. Never require authenticated scraping of BoardGameGeek.
4. Rulebook provenance must always be stored. A downloaded document is not trusted merely because its filename looks plausible.
5. Official publisher/localizer sources outrank community sources.
6. Community translations must be visibly marked as unofficial.
7. Do not write directly to Floppy's database. Integrate through its supported HTTP API.
8. Do not make Floppy the sole source of truth. The internal domain model must remain usable independently.
9. A board-game item may have zero, one or many documents.
10. RAG answers must retain document identity and page-level citation metadata.

## Persistent filesystem contract

- `/config`: database and application configuration.
- `/data/import`: inbound collection exports such as BGG CSV.
- `/data/manuals`: rulebooks and related documents.

Never store persistent state only inside the container filesystem.

## Rulebook confidence

Initial policy:

- official publisher: 100
- official localizer/distributor: 100
- official mirrored/uploaded source: 95
- known community source: 70
- generic discovery result: 40

Only high-confidence results may become unattended downloads. Lower-confidence results must enter a review queue.

## Provider architecture

Rulebook discovery must use isolated provider adapters. Do not put publisher-specific parsing logic in generic resolver code.

Every provider should return normalized candidates containing at least:

- source/provider
- URL
- language
- document type
- official/unofficial status
- confidence
- edition/version clues when available

## Development rules

- Keep changes small and testable.
- Add tests for import parsing, matching, provider normalization and destructive state changes.
- No feature may silently overwrite a user's manual or collection metadata.
- Imports must be idempotent.
- Preserve unknown CSV fields where practical instead of discarding potentially useful source data.
- Secrets belong in environment variables or runtime configuration, never in the repository.
- Prefer additive schema migrations.
- Treat network content as untrusted input.

## Git workflow

- Work on feature branches.
- Keep `main` deployable.
- Do not force-push `main`.
- Do not merge failing CI.
- Use conventional, scoped commit messages where practical.

## Initial milestones

P0. Foundation: Docker, health endpoint, CI/GHCR, Unraid template.
P1. BGG CSV importer and internal catalog.
P2. Floppy synchronization adapter.
P3. Physical-copy/barcode model and scanner workflow.
P4. Rulebook document model, storage and manual upload.
P5. Official rulebook provider framework and IT/EN resolver.
P6. Review queue and scheduled document update checks.
P7. RAG ingestion and page-cited Q&A.

## Mandatory execution policy — GitHub-first, operator-minimal

This policy has top workflow priority for all current and future development, remediation, review, and maintenance phases in this repository. It overrides older execution/workflow instructions where they conflict, but it never overrides an explicit scope or safety boundary in the current user mandate.

1. **GitHub is the primary work surface and source of truth.** Use GitHub-native/connected capabilities first for repository inspection, branches, file edits, commits, pull requests, diffs, reviews, CI status/logs, and merges when the current phase authorizes them.
2. **Minimize operator involvement.** Do not ask the user to copy/paste scripts, relay command output, or perform routine Git/GitHub steps when an available connected tool can perform the same operation. Within the currently authorized phase, carry routine steps through autonomously.
3. **Respect the phase boundary.** Autonomy applies only to the phase currently authorized. Do not start a subsequent phase, broaden product scope, deploy, publish, merge, mutate production data, or perform another action that the current mandate reserves for later approval.
4. **Independent reviews remain read-only.** A review/re-review agent must not modify the reviewed branch, remediate findings, or alter runtime state unless the user explicitly changes the mandate.
5. **Remote Desktop Commander is a last resort.** Use it only when the required operation is genuinely impossible through GitHub, CI, available connectors/tools, or another non-interactive route and access to the real NAS/PC/GUI/filesystem/runtime is indispensable. Never select it merely out of convenience.
6. **CloudCLI requires explicit prior user authorization.** Use CloudCLI only when coding/debugging truly requires the real environment and GitHub/CI cannot provide sufficient evidence or execution. Do not use CloudCLI for ordinary repository editing, Git operations, documentation updates, or routine inspection.
7. **Prefer reproducible automation over ad-hoc terminal work.** When real-environment execution is recurring, encode it in versioned scripts or GitHub Actions/self-hosted-runner workflows where safe, rather than repeatedly asking the user to execute shell fragments.
8. **Manual user steps are exceptional.** If no automated route exists, explain why the manual step is unavoidable and provide the smallest safe self-contained command block. Do not split a routine operation into many copy/paste exchanges.
9. **Ask only for decisions that require human authority or information.** Examples: a product/scope choice not determined by the current mandate, destructive/irreversible production action, secret/credential input, or an explicit approval gate. Do not ask for confirmation of routine reversible steps already covered by the phase.
10. **Verify before claiming completion.** Check the exact branch/SHA, relevant diff, CI/tests, and any required runtime evidence. At handoff report the exact state, what was verified, unresolved limitations, and the next permitted step.
11. **Do not silently substitute environments.** GitHub/CI evidence is preferred for source-level work. If correctness depends on NAS/Windows/Home Assistant/other real runtime behavior, state that dependency and obtain the required authorization before using CloudCLI; use Remote Desktop Commander only if indispensable under rule 5.
12. **Keep secrets and production state out of GitHub.** Use repository secrets/environments or runtime secret stores. Never commit tokens, passwords, private runtime databases, or sensitive generated state.

### Default execution order

GitHub inspection → scoped branch/worktree → implementation or read-only review as mandated → automated tests/CI → PR/review evidence → merge only if authorized → real-environment validation/deploy only if authorized and necessary.

If a task can be completed reliably without involving the user in mechanical steps, it should be.

## Source-integrity invariant — no local-only source changes

This invariant is mandatory for every coding agent, including CloudCLI/Claude Code, Codex, ChatGPT, self-hosted runners, and future agents.

1. **A production/runtime checkout is never a development workspace.** Do not edit application source in a directory whose files are consumed directly by a running service/container/plugin/runtime. Use a dedicated task branch and a separate worktree/clone.
2. **Every source change must become a GitHub commit before handoff or deployment.** A change is not durable, shareable, reviewable, or complete while it exists only as an uncommitted/unpushed local filesystem edit.
3. **Push before deploy.** The exact code intended for runtime must first exist on GitHub at a named branch and immutable commit SHA. Runtime actions must record/verify that SHA.
4. **No deploy from a dirty tree.** Do not restart/redeploy merely to activate uncommitted source edits. If a runtime checkout is dirty, treat that as source-integrity drift and stop normal deployment.
5. **Never erase drift to make Git look clean.** If a production/runtime checkout contains local-only changes, preserve them first on a rescue branch/commit and push them to GitHub before reset, checkout, pull, rebase, replacement, or cleanup.
6. **Agent isolation is mandatory.** One task/agent = one branch/worktree. Two agents must not write concurrently to the same working tree. Handoff occurs through pushed commits/PRs, not shared uncommitted files.
7. **Start from remote truth.** Before editing, fetch origin and verify the intended remote branch/SHA. A clean worktree whose HEAD differs from GitHub is still drifted.
8. **End with remote truth.** Before claiming completion, verify that the final intended commit exists on GitHub and report its branch/SHA. If a task intentionally remains read-only, say so instead.
9. **Runtime verification is separate from source publication.** Tests or behavior observed from locally modified runtime files do not prove that GitHub contains those changes.
10. **Local-only emergency fixes are temporary quarantine states, not a workflow.** If an emergency runtime edit is unavoidable, immediately capture the exact source delta on a dedicated rescue/fix branch, test it, push it, and only then continue normal work.

For repositories with a NAS bridge, the bridge should compare both the technical Git workspace and, where available, the real runtime checkout. A green technical mirror must never be interpreted as proof that production is synchronized.

## Shared NAS control bridge — canonical runtime access path

This repository participates in the shared GitHub-mediated NAS control architecture. This policy does not override repository-specific review, deployment, or production safety gates.

### Canonical path

ChatGPT / connected GitHub tooling → `golgoth85/upscaler` branch `ops/nas-control` → GitHub Actions workflow `NAS Control` → self-hosted runner `github-runner-nas-control-v2` / label `nas-control` → authenticated local agent `nas-control-agent` → typed operations against Unraid / approved project workspaces / LAN services.

### Security boundary

- The active runner is intentionally least-privilege. It mounts only its runner state RW plus the NAS-control token RO.
- The runner does **not** receive `/var/run/docker.sock` and does **not** mount `/mnt/user/appdata` directly.
- `nas-control-agent` is the only NAS-control component with Docker-socket access.
- The agent exposes a typed allowlist; there is no generic host-root shell.
- The base `/mnt/user/appdata` mount inside the agent is read-only.
- Only the explicitly listed project workspaces below are overlaid read-write.
- Generic file reads block likely secret/token/credential/key material.
- Docker state-changing operations require explicit confirmation.
- Never weaken this boundary for convenience; add a narrow typed capability instead.

### Selective RW project workspaces — active and verified

The following development workspaces are mounted RW in `nas-control-agent` and were verified with `mounted=true` and `writable=true` through the least-privilege runner:

- `upscaler` → `/mnt/user/appdata/github-runner-worktrees/upscaler`
- `boardgamecompanion` → `/mnt/user/appdata/github-runner-worktrees/boardgamecompanion`
- `bookarr` → `/mnt/user/appdata/bookarr/repo`
- `cwsync.koplugin` → `/mnt/user/appdata/github-runner-worktrees/cwsync.koplugin`
- `komix.koplugin` → `/mnt/user/appdata/github-runner-worktrees/komix.koplugin`
- `home-assistant` → `/mnt/user/appdata/github-runner-worktrees/home-assistant`

These paths are development/source workspaces. Do not substitute runtime/config directories for them.

### Controlled workspace write operations

The agent supports typed workspace operations including:

- `workspace_list`
- `workspace_status`
- `workspace_read_file`
- `workspace_create_branch`
- `workspace_write_file` with SHA-256 precondition
- `workspace_apply_patch`
- `workspace_diff`

Write protection rules:

- direct writes on `main`, `master`, `deploy/current`, and `production` are forbidden;
- task branches created by the bridge must use `chatgpt/...`;
- direct `.git` manipulation is forbidden;
- secret/token/credential/key paths remain forbidden;
- a technical RW capability never overrides an explicit read-only review mandate;
- source changes still follow the repository's commit/review/merge/deploy gates.

### Other active typed capabilities

The hardened control agent can perform controlled Docker list/inspect/logs/start/stop/restart operations, appdata listing/read operations, Git status inspection, TCP/HTTP probes, Home Assistant discovery/probe, LM Studio model probing, and NAS filesystem capacity reporting.

`disk_space` is active and reports the Unraid `/mnt/user` user-share filesystem. At the activation verification on 2026-09-25 it reported 70.93 TiB total, 58.70 TiB used, 12.23 TiB free, 83% used. Treat these numbers as a point-in-time observation; query `disk_space` again for current capacity.

### Current verified LAN endpoints

- Unraid main web surface: `192.168.1.55:1234`.
- Home Assistant: `192.168.1.147:8123`; reachability verified. Authenticated HA actions still require the dedicated token/secret boundary.
- LM Studio: `192.168.1.249:1234`; when the PC and LM Studio server are running, `/v1/models` returns HTTP 200 with OpenAI-compatible model data.
- Tailscale is installed on the Flint 2 router; Tailscale on Unraid is disabled. Do not expect a local Unraid `tailscaled` socket.

### Execution preference

1. Use GitHub-native repository operations for source-level work when sufficient.
2. Use the NAS control bridge for runtime inspection and authorized workspace edits.
3. Prefer the selective RW workspace operations over direct runtime/config mutation.
4. Do not ask the operator to use Termius for routine operations supported by the bridge.
5. Remote Desktop Commander is not the preferred route and may be unavailable due to quota.
6. CloudCLI still requires explicit prior user authorization.
7. Never let bridge capabilities bypass an independent-review read-only mandate, no-deploy/no-merge instruction, or explicit phase gate.

