# Local CI

This repository is governed by the mandatory Local CI policy in `golgoth85/local-ci-lab/docs/LOCAL-CI-ADOPTION-POLICY.md` and is listed in `docs/LOCAL-CI-REPOSITORY-REGISTRY.md`.

Current state: **historical BGC coverage; I3 profile-pending**.

Rules:
- ordinary development tests/validation must use the disposable Local CI I3 path once the repository profile is available;
- automatic GitHub-hosted development CI is not the default and must not be reintroduced silently;
- during migration, any retained GitHub-hosted development workflow is manual-only (`workflow_dispatch`);
- release/publish/deploy jobs requiring credentials are a separate trusted boundary;
- untrusted PR/source code must never execute directly on a persistent credential-bearing self-hosted runner;
- unknown profiles fail closed rather than falling back to `ubuntu-latest`.

For a new repository, register it in the Local CI repository registry before treating CI as configured.
