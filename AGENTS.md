# BoardGameCompanion

Regole comuni di infrastruttura e sviluppo: `/workspace/AGENTS.md`.

## Funzionamento
- Python/FastAPI in `src/boardgamecompanion/`, UI in `web/`, test in `tests/`. Gestisce catalogo BGG, copie fisiche/barcode, acquisizione di regolamenti e domande RAG con citazioni di pagina.
- SQLite e configurazione su `/config`; import su `/data/import`, regolamenti su `/data/manuals`. Nessuno stato persistente nel solo filesystem del container.
- LM Studio/Ollama per embeddings e generazione; provider testuali Gemini, DeepSeek e Groq; ricerca web Gemini o DeepSeek Search/Fetch secondo configurazione. Chiavi solo nel runtime.
- Runtime `BoardGameCompanion`, `http://192.168.1.55:8787/health`; template `unraid/boardgamecompanion.xml`. Codice `/workspace/_prod/BoardGameCompanion/boardgamecompanion` montato nel pacchetto Python: estrarre `src/boardgamecompanion` con `--strip-components=2`, scambiare con backup e riavviare. Dati in appdata/boardgamecompanion; import e manuali nella share Altro/boardgames.

## Invarianti e zone delicate
- `objectid` BGG è l'identificatore canonico; codici prodotto delle versioni BGG non sono UPC/EAN/ISBN. Catena: `barcode -> OwnedCopy -> BoardGame`; zero o più documenti per gioco.
- Deve funzionare senza token BGG, anche con import CSV; BGG solo via XML API2 approvata, senza scraping autenticato. Import idempotenti e metadati manuali preservati.
- Provenienza dei regolamenti sempre registrata: ufficiali prima della comunità, candidati normalizzati da adattatori isolati. Download automatico solo con identità esatta, fonte fidata e politica approvata (confidenza ufficiale 95–100, comunità 70, generica 40); altrimenti revisione.
- RAG conserva documento e pagina, esplicita conflitti e mancata risposta. Rete non fidata; guasti dei provider non bloccano il catalogo locale.
- Schema/migrazioni, import e acquisizioni reali, cancellazioni o sovrascritture di copie/documenti richiedono backup e il percorso delle zone delicate. Wake-on-LAN solo per operazioni autorizzate.

## Verifica e sviluppo
Test e browser: `python3 scripts/ci_local.py` (vedere `--list`/`--help`); nessuna attivazione CI necessaria. Architettura e contratti in `docs/ARCHITECTURE.md` e documenti di fase richiamati da `ROADMAP.md`, unico ingresso per stato e prossime attività.
