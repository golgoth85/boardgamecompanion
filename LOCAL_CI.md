# Local CI

This repository uses **Universal Local CI** as the default development-validation path.

Current trusted contract:
- generic entrypoint: `localci_repo_ci`;
- repository identity: `golgoth85/boardgamecompanion` / GitHub ID `1381144611`;
- command profile: `pytest-browser-v1`;
- immutable template: `python-browser-pytest-boardgamecompanion` v1;
- policy identity: `localci-boardgamecompanion-browser-pytest-v1`;
- trusted registry: `golgoth85/nas-control:ops/nas-control/localci-repositories.json`;
- This browser profile includes Python tests, Node JavaScript syntax checks and isolated Chromium/Playwright E2E; browser and backend failures remain distinguishable.

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

Historical enrollment #2137 used the former pytest-only v2 contract; it is not evidence for the current browser profile. NAS Control #3851 on 2026-10-13 independently reported the current browser v1 profile active and CI available.

Configuration and activation snapshot: [NAS Control #3851](https://github.com/golgoth85/nas-control/issues/3851), [run 38427508177](https://github.com/golgoth85/nas-control/actions/runs/38427508177), 2026-10-13. This confirms infrastructure availability, not PASS for any new commit. The trusted server registry remains authoritative; application documentation cannot choose its own profile.
