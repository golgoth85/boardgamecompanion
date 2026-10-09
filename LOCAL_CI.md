# Local CI

This repository uses **Universal Local CI** as the default development-validation path.

Current trusted contract:
- generic entrypoint: `localci_repo_ci`;
- repository identity: `golgoth85/boardgamecompanion` / GitHub ID `1381144611`;
- command profile: `pytest-v1`;
- immutable template: `python-pytest-boardgamecompanion` v2;
- policy identity: `localci-boardgamecompanion-pytest-v2`;
- trusted registry: `golgoth85/nas-control:ops/nas-control/localci-repositories.json`;
- Python pytest profile does not require Node merely because static JavaScript assets are present; JavaScript files remain bounded and counted, while Node validation belongs to profiles that explicitly contract for it.

Automatic PR routing:
- `.github/workflows/local-ci.yml` sends only PR number, exact head SHA, base repository and numeric repository ID to the repository-scoped `localci-dispatcher`;
- the dispatcher never checks out or executes PR code and has no Docker socket or host-root mount;
- source acquisition, authority resolution, policy/template selection and execution happen in NAS Control;
- PASS requires matching repository/SHA/profile, guest `LOCALCI_RESULT_V1` PASS and cleanup attestation.

Result semantics:
- `PASS`: application checks passed;
- `APPLICATION_FAIL`: guest/infrastructure completed correctly but application checks failed;
- `INFRASTRUCTURE_FAIL`: transport, authority, policy/template, QEMU, scheduler or result-protocol failure.

Rules:
- ordinary development tests run in the disposable credentialless I3 guest;
- unknown repositories, stale activation markers or mismatched numeric IDs fail closed;
- PR code cannot select its own template, policy, profile or resources;
- automatic GitHub-hosted development CI is not the ordinary path;
- any retained hosted development workflow must remain manual-only;
- release/publish/deploy jobs requiring credentials are a separate trusted boundary;
- infrastructure failures must not silently fall back to hosted CI.

The activation E2E reference is added only after the v2 enrollment has completed successfully.
