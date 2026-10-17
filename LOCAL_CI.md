# Local CI

Dal 2026-10-17 la **Universal Local CI è facoltativa e non blocca il deploy**,
secondo `AGENTS.md` e il regime semplificato in `/workspace/AGENTS.md`.
I test pertinenti restano richiesti. Le sezioni seguenti descrivono il contratto
esistente quando si usa la Local CI; non ne attestano la disponibilità attuale.
La PR #153 propone il passaggio al poller e resta aperta con il proprio requisito
di attivazione verificata, senza modificarlo in questa sessione.

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

## Entrypoint del repository: `scripts/ci_local.py` (2026-10-16)

Dal 2026-10-16 il repository contiene `scripts/ci_local.py`: l'elenco unico dei controlli della Local CI, solo con la libreria standard. Il runner del guest (revisione authority `d40i-repo-entrypoint-v11` di `golgoth85/local-ci-lab`, vedi `docs/D40I-REPO-ENTRYPOINT.md`) esegue **solo** `python scripts/ci_local.py` se il file e' regolare (ne' il file ne' `scripts/` sono symlink); altrimenti usa la funzione storica `boardgamecompanion_checks`.

**Quando vale.** Il runner vive nel template sigillato del repository: `ci_local.py` viene usato dal guest solo dopo la ricostruzione del template di questo repo con il runner d40i. Fino ad allora il guest continua a usare la funzione storica, che esegue gli stessi controlli (tabella sotto). Il trigger (`local-ci.yml`, in seguito il poller lato NAS) non cambia con questa modifica.

**Equivalenza con la funzione storica `boardgamecompanion_checks`** (`PYTHONPATH=<radice>/src`, `BGC_CONFIG_DIR`/`BGC_IMPORT_DIR`/`BGC_MANUALS_DIR` sotto `DATA_DIR`, `BGC_CHROMIUM_EXECUTABLE=/usr/bin/chromium`):

| Controllo | Comando | Timeout (s) |
|---|---|---|
| `pytest-application` | `python -m pytest -q -p no:cacheprovider tests --ignore=tests/e2e` | 720 |
| `pytest-browser-e2e` | `python -m pytest -q -p no:cacheprovider tests/e2e` | 900 |

Il comportamento comune: uscita 0 solo se tutti i controlli passano; budget complessivo di 1500 s (il runner concede 1700 s; la somma dei timeout per controllo, 1620 s, e' piu' larga, ma ogni controllo riceve al massimo il tempo residuo); riepilogo finale; nessuna rete; nessuna scrittura nella sorgente (che nel guest e' in sola lettura) e nessun `.pyc`. I test e2e fanno parte dell'entrypoint perche' il profilo del registro e' `pytest-browser-v1` (la storica li esegue solo con quel profilo).

**Prova a mano.** `python scripts/ci_local.py --list` elenca i controlli; `--only NOME ...` ne esegue alcuni; `--allow-missing-deps` (solo prove locali) tratta una dipendenza esterna mancante come `SKIP` invece che come errore: un `PASS PARZIALE` con controlli saltati non e' un PASS di CI. `--skip-e2e` salta i test browser (serve Chromium con Playwright).
