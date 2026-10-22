# BoardGameCompanion

Regole generali (infrastruttura, GitHub, deploy, zone delicate): `/workspace/AGENTS.md`.

## Scopo
Applicazione self-hosted (Docker/Unraid) per gestire una collezione fisica di giochi da tavolo: catalogo da BoardGameGeek, copie fisiche e codici a barre, ricerca e archiviazione dei regolamenti, domande sui documenti con RAG e citazione di pagina. Funzioni attuali e architettura: `README.md`, `docs/ARCHITECTURE.md`.

## Funzionamento
- Python, `src/`, test in `tests/`, immagine da `Dockerfile`, immagine pubblicata su `ghcr.io/golgoth85/boardgamecompanion` (tag `sha-<commit>`).
- Produzione: container `BoardGameCompanion`, porta 8787, template `unraid/boardgamecompanion.xml`. Config in `/mnt/user/appdata/boardgamecompanion` (`/config`, database SQLite); import CSV in `/mnt/user/Altro/boardgames/import`, regolamenti in `/mnt/user/Altro/boardgames/manuals`.
- Stato persistente solo su `/config`, `/data/import`, `/data/manuals`: mai solo nel filesystem del container.
- Provider AI: LM Studio (embeddings, con Wake-on-LAN), Ollama e Gemini; DeepSeek e Groq per generazione. Ricerca web selezionabile fra Gemini e DeepSeek Search/Fetch. Segreti solo in variabili d'ambiente o config di runtime.
- Local CI: profilo `pytest-browser-v1` (Python, JavaScript, Playwright); dettagli in `LOCAL_CI.md`. Facoltativa, non blocca il deploy. Deploy: ricetta nella tabella «Deploy» di `/workspace/AGENTS.md`; salute su `:8787/health` (schema DB atteso 22 salvo migrazioni). Dipendenze o Dockerfile nuovi richiedono un rebuild sul host.

- Orientamento facoltativo: `python3 scripts/trail_local.py build`, poi `map`, `ask "domanda"`, `skeleton <file>` o `callers <simbolo>`. Configurazione e limiti in `docs/TRAIL-PILOT.md`; nessun hook automatico. Il grafo dei chiamanti può essere incompleto: verificare sempre gli usi nei sorgenti prima di una modifica.

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
- Migrazioni dello schema SQLite in `/config` (devono restare additive; backup del DB prima).
- Import CSV e acquisizione dei regolamenti in `/data/manuals`: download automatici, sovrascrittura di metadati manuali, cancellazione di copie o documenti.
- Invarianti di dominio (`objectid` BGG, catena `barcode -> OwnedCopy -> BoardGame`, provenienza dei regolamenti).

## Documenti
`README.md`, `ROADMAP.md`, `docs/` (contratti di fase P3B-P7E, `ARCHITECTURE.md`), `LOCAL_CI.md`. Ultimo checkpoint (audit del 2026-10-17, prossimo gate: accettazione fisica Wake-on-LAN solo con PC predisposto dal proprietario): `docs/handoff/2026-10-17-residual-audit.md`; i branch `backup/*-wip-20261015` sono superati: non importarli integralmente. Storico dell'handoff 2026-10-13 e delle regole pre-ristrutturazione: `docs/archive/AGENTS-pre-restructure-2026-10-15.md`.
