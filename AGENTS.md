# BoardGameCompanion

Contesto generale (infrastruttura, GitHub, regole operative): `/workspace/AGENTS.md`.

## Scopo
Applicazione self-hosted (Docker/Unraid) per gestire una collezione fisica di giochi da tavolo: catalogo da BoardGameGeek, copie fisiche e codici a barre, ricerca e archiviazione dei regolamenti, domande sui documenti con RAG e citazione di pagina. Funzioni attuali e architettura: `README.md`, `docs/ARCHITECTURE.md`.

## Funzionamento
- Python, `src/`, test in `tests/`, immagine da `Dockerfile`, immagine pubblicata su `ghcr.io/golgoth85/boardgamecompanion` (tag `sha-<commit>`).
- Produzione: container `BoardGameCompanion`, porta 8787, template `unraid/boardgamecompanion.xml`. Config in `/mnt/user/appdata/boardgamecompanion` (`/config`, database SQLite); import CSV in `/mnt/user/Altro/boardgames/import`, regolamenti in `/mnt/user/Altro/boardgames/manuals`.
- Stato persistente solo su `/config`, `/data/import`, `/data/manuals`: mai solo nel filesystem del container.
- Provider AI: LM Studio (embeddings, con Wake-on-LAN) e Gemini (generazione); Ollama supportato. Segreti solo in variabili d'ambiente o config di runtime.
- Local CI: profilo `pytest-browser-v1` (Python, JavaScript, Playwright); dettagli in `LOCAL_CI.md`. Facoltativa, non blocca il deploy. Deploy (dal 2026-10-17): il pacchetto Python è montato in sola lettura da `/workspace/_prod/BoardGameCompanion/boardgamecompanion` sulla cartella del pacchetto in `site-packages`; si aggiorna estraendo `src/boardgamecompanion` dal commit pubblicato e riavviando con `unraid_docker_restart BoardGameCompanion`; controllo su `http://192.168.1.55:8787/health` (schema DB atteso 21 salvo migrazioni). Dipendenze o Dockerfile nuovi richiedono un rebuild sul host. Ricette e stato: «Deploy semplice» in `/workspace/AGENTS.md`.

## Regole di dominio
1. L'`objectid` di BGG è l'identificatore esterno canonico; i codici prodotto delle versioni BGG non sono UPC/EAN/ISBN.
2. Deve funzionare senza token BGG: l'import CSV è un percorso di primo livello. Mai scraping autenticato di BGG; accesso BGG solo via XML API2 approvata.
3. Invariante della copia fisica: `barcode -> OwnedCopy -> BoardGame`. Un gioco può avere zero, uno o più documenti.
4. Provenienza dei regolamenti sempre registrata. Fonti ufficiali (editore/localizzatore) battono quelle della comunità, che vanno marcate come non ufficiali. Download automatico solo ad alta confidenza (ufficiale 95-100, comunità 70, scoperta generica 40); il resto va in coda di revisione. Acquisizione fail closed: identità esatta, fonte fidata, politica approvata.
5. Provider di scoperta come adattatori isolati con candidati normalizzati; niente parsing specifico di un editore nel resolver generico.
6. Le risposte RAG mantengono identità del documento e citazione di pagina, con comportamento esplicito su conflitti e "non trovato".
7. Il contenuto di rete è input non fidato. Un guasto di un provider esterno non deve rendere inutilizzabile il catalogo locale.

## Regole di sviluppo
Modifiche piccole e testabili; test per parsing, matching, normalizzazione dei provider e cambi di stato distruttivi. Import idempotenti; nessuna sovrascrittura silenziosa di metadati manuali; migrazioni di schema additive. Feature branch, `main` sempre distribuibile, niente force-push, niente merge con CI rossa. Codice applicativo: test locali (Local CI se c'è e funziona), poi evidenza di pubblicazione e runtime. Nei report separare la revisione funzionale distribuita dagli HEAD successivi solo documentali.

## Zone delicate

Toccare queste parti **non** si annulla con un semplice revert: prima backup o prova su una copia; se non basta, PR e review consigliata al proprietario (regola «Quanto rigore» in `/workspace/AGENTS.md`). Tutto il resto: si va dritti.
- Migrazioni dello schema SQLite in `/config` (devono restare additive; backup del DB prima).
- Import CSV e acquisizione dei regolamenti in `/data/manuals`: download automatici, sovrascrittura di metadati manuali, cancellazione di copie o documenti.
- Invarianti di dominio (`objectid` BGG, catena `barcode -> OwnedCopy -> BoardGame`, provenienza dei regolamenti).

## Documenti
`README.md`, `ROADMAP.md`, `docs/` (contratti di fase P3B-P7E, `ARCHITECTURE.md`), `LOCAL_CI.md`. Storico dell'handoff 2026-10-13 e delle regole pre-ristrutturazione: `docs/archive/AGENTS-pre-restructure-2026-10-15.md`.

## Deploy (regime semplificato, 2026-10-17)

Il protocollo di adozione obbligatoria del 2026-10-17 è **sostituito** dal regime semplificato in `/workspace/AGENTS.md` («Deploy e controlli»): Local CI facoltativa e non bloccante, deploy dal container con il codice montato dal host e riavvio, backup dei dati prima di toccarli. Il testo precedente resta nella storia di git.

## Checkpoint del 2026-10-17

Audit in sola lettura: pacchetto montato identico nei 70 file a `7973d11dae98c7121998e0a73f2ced0290903348`, salute HTTP 200 e schema 21. Gli HEAD successivi documentali/CI non identificano un nuovo deploy applicativo. I due branch `backup/*-wip-20261015` sono stati valutati e superati dalle implementazioni correnti: non importarli integralmente. Evidenze e motivazioni: `docs/handoff/2026-10-17-residual-audit.md`. Prossimo gate di prodotto: accettazione fisica Wake-on-LAN, solo con PC predisposto dal proprietario; nessun test fisico autorizzato da questo checkpoint.
