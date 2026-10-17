# Ripresa dal checkpoint del 13 ottobre

Audit del 2026-10-17, senza modifiche applicative, dati, download di regolamenti,
deploy o azioni sul PC. Il prompt storico è stato confrontato con le istruzioni
operative correnti prima di intervenire.

## Autorità e concorrenza

- BGC `main` iniziale: `194016cbf0c2c2e2c441605b08d92c400c55011d`.
- NAS Control `main`: `e2b9049c70b133251a78437e099a314018318862`.
- Letti integralmente AGENTS remoto, `docs/ROADMAP.md`, README, LOCAL_CI,
  roadmap radice e architettura; lette anche le istruzioni `/workspace/AGENTS.md`
  e AGENTS remoto di NAS Control.
- Unica PR aperta rilevata: [#153](https://github.com/golgoth85/boardgamecompanion/pull/153),
  cambio del trigger Local CI condizionato all'attivazione del poller. Lasciata
  intatta: il relativo lavoro infrastrutturale non viene riaperto qui.
- Regime vigente: GitHub per il codice, UnraidClaw per i container,
  Local CI facoltativa, backup e test pertinenti. NAS Control a riposo.
  Non è stato avviato CloudCLI né usato Desktop Commander.

## Valutazione dei backup WIP

I due branch non sono stati uniti o cancellati. La decisione riguarda il recupero
integrale delle vecchie implementazioni, non l'equivalenza di ogni riga o dettaglio
di presentazione.

| Backup | HEAD valutato | Esito |
| --- | --- | --- |
| `backup/suggestions-v1-wip-20261015` | `bc3f4acc2eac8d24ea0367f2fc6a05b4ef42b802` | Superato: API2 hot, scoring, esclusione posseduti/espansioni, cache e pagina già presenti. |
| `backup/personal-ux-macro18-wip-20261015` | `da42244c41ba3491eb01138b44b537d5e98dc710` | Superato per le capacità di prodotto; incompatibile nei contratti di persistenza/API. |

I suggerimenti sono già entrati con `f5608f9`, poi corretti ed estesi con
`5aaf6cf`, `ad84085`, `9c3310a`, `5cf8b97` e `f5808d6`.
Il servizio corrente aggiunge confronti con i giochi posseduti, contenuti
editoriali e pool storico limitato. Reintrodurre il servizio WIP da 422 righe
eliminerebbe questi sviluppi; non costituisce una nuova feature aperta.

La UX personale corrente deriva da `5f5314c` (PR #109). Il WIP alternativo usa
`game_lists`, `game_list_items`, `wishlist_items`, mentre il modello adottato usa
`saved_game_lists`, `saved_game_list_items`, `personal_wishlist`. Riscrive anche
le migrazioni esistenti. Il payload personale WIP accetta voti interi 1–5,
mentre il prodotto corrente supporta mezze stelle e preserva le partite importate.
La wishlist WIP non conserva la validazione HTTP(S) senza credenziali del codice
corrente; i filtri lista sono meno validati. Router e componenti alternativi non
giustificano il recupero delle vecchie tabelle o un nuovo refactoring.

## Verifiche

Confronto di tutti i blob Git di `src/boardgamecompanion` con il pacchetto montato
in `/workspace/_prod/BoardGameCompanion/boardgamecompanion`: **70 file identici,
zero mancanti, zero modificati, zero file extra** (esclusi `__pycache__`).
Risultato uguale confrontando sia `7973d11dae98c7121998e0a73f2ced0290903348`
sia il `main` iniziale. Questo identifica i sorgenti applicativi montati; non è
una nuova attestazione dell'immagine o un nuovo deploy.

`GET /health`: HTTP 200, `status=ok`, schema 21.
`GET /api/notifications?limit=1`: `unread_count=1`. È un indicatore delle sole
notifiche non lette, non una misura del totale storico o della crescita. Non si
introduce una cancellazione automatica sulla base di questa osservazione.
La retention resta manutenzione da valutare con evidenza del volume nel tempo.
Risposta health originale e confronto ripetibile in
[`evidence/2026-10-17-runtime.json`](evidence/2026-10-17-runtime.json).

Test sul codice corrente, con dati temporanei e client finti, Python 3.14.8:

```text
python -m pytest -q -p no:cacheprovider tests/test_suggestions.py tests/test_personal_library.py tests/test_expansions.py tests/test_crowdfunding_notifications.py
25 passed, 1 warning in 2.99s
```

Warning: deprecazione del client httpx di Starlette. Il primo tentativo con
Python di sistema 3.11 non ha raccolto i test per dipendenze mancanti; il venv
iniziale sotto `/tmp` non consentiva il caricamento della libreria nativa
pydantic-core. Il venv isolato spostato sotto `/home/runtime/tools` ha completato
la verifica. Nessuna modifica ai requisiti del progetto. Non è una validazione
Universal Local CI né una prova browser; nessuna UI è stata modificata.

## Checkpoint risultante

Solo documentazione: riallineati AGENTS, README, le due roadmap e LOCAL_CI.
Nessuna PR applicativa, nuova CI, pubblicazione immagine o deploy da dichiarare.
Gli SHA di questa revisione documentale si ricavano dal commit del presente file;
la revisione funzionale montata resta `7973d11dae98c7121998e0a73f2ced0290903348`.
Le evidenze storiche barcode e ricerca restano valide e gli incidenti chiusi.

Il prossimo gate di prodotto resta l'accettazione fisica Wake-on-LAN:
`sleep/off -> wake da BGC -> PC online -> LM Studio pronto -> operazione AI riuscita`.
Richiede che il proprietario dichiari il PC predisposto o autorizzi il test fisico.
Non eseguito né simulato. La qualità delle fonti dei regolamenti rimane
manutenzione opportunistica; nessuna fonte è stata rivalutata o acquisita qui.
