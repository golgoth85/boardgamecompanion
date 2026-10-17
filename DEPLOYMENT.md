# Deploy tramite UnraidClaw

Aggiornato: 2026-10-17. Stato: adozione in corso, nessun deploy applicativo eseguito da questa attività.

## Identità e sorgente

- Repository: `golgoth85/boardgamecompanion`, ID numerico `1381144611`.
- Branch applicativo/di produzione: `main`. Rileggerne sempre la punta remota; non fissare nel profilo uno SHA diventato obsoleto.
- Container: `BoardGameCompanion`.
- Salute proposta: `http://127.0.0.1:8787/health`; verificarne HTTP 200 dal NAS senza esporre il corpo della risposta.
- Modalità prevista: `build`; sorgente/contesto `.`. Dockerfile relativo al contesto: `Dockerfile`.

Preservare rete host, /config e i mount import/manuals; nessuna chiamata ai provider AI durante l’adozione.

## Prerequisiti fidati

Local CI: `pytest-browser-v1`, template `python-browser-pytest-boardgamecompanion` v`1`, policy `localci-boardgamecompanion-browser-pytest-v1`. Identità rilevate dal registro sorgente di Local CI; verificarle contro l’authority live e il run esatto prima della registrazione.

Il percorso ordinario è `unraid_app_deploy`, con profilo registrato dal proprietario in `deployments.json` sotto il `FLASH_BASE` reale del servizio, verificato sul NAS come `/boot/config/plugins/unraidclaw`. Preservare tutti gli altri profili e il percorso comune dell’authority. Un JSON presente non dimostra che l’app sia adottata.

Per build/bind, predisporre il clone dedicato root:root sotto `/mnt/cache/appdata/unraidclaw/repositories/boardgamecompanion`, separato dai checkout di sviluppo e dalla produzione. Origin esatto `git@github.com:golgoth85/boardgamecompanion.git`. Accesso Git dedicato in sola lettura, persistente e senza prompt: il profilo contiene soltanto i percorsi `gitIdentityFile` e `gitKnownHostsFile`; le private restano sul NAS e non entrano nel workspace o nei log.

Dati, mount, rete, template e filesystem dello staging devono essere verificati sul runtime reale. Le migrazioni dei dati richiedono un piano specifico di backup/ripristino: il rollback del codice non le annulla. I limiti del profilo devono produrre un blocker esplicito, senza perdere impostazioni del container.

## Procedura obbligatoria per gli agenti

Applicare automaticamente la sezione «Deploy UnraidClaw e adozione obbligatoria dei progetti» di `/workspace/AGENTS.md`, anche quando il task riguarda una feature e non chiede espressamente la configurazione del deploy. Per i nuovi servizi svolgere onboarding CI e deploy prima di dichiarare il percorso pronto.

1. Fetch, branch/PR e contesto di produzione corretti; sviluppo soltanto nel clone.
2. Controlli del progetto e browser quando cambia la UI; Local CI esatta con PASS, CLEANED e cleanup attestato.
3. Merge soltanto nel mandato; rivalidare lo SHA completo della punta remota prima della distribuzione.
4. Richiedere l’anteprima nativa:

```json
{"name":"BoardGameCompanion","revision":"<SHA Git completo della punta autorizzata>","dryRun":true}
```

5. Salvare il payload strutturato, distinguendo anteprima e deploy effettivo. Solo con dry run riuscito e mandato applicativo inviare `dryRun:false`; verificare poi revisione, salute e pulizia dello staging.
6. Aggiornare `AGENTS.md`, questo file, `LOCAL_CI.md`, `ROADMAP.md` e il diario quando previsto. Una modifica solo documentale non richiede un nuovo deploy.

## Stato di questa adozione

Il problema comune `DEPLOY_NOT_CONFIGURED` è risolto con Komgarr. La sonda iniziale di questa app restituisce `DEPLOY_NOT_REGISTERED`. Inventario host, chiavi dedicate, attestazione Local CI esatta e dry run specifico sono ancora da completare. Non riportare lo stato come attivo sulla base di questa preparazione documentale.
