# BoardGameCompanion — roadmap

Aggiornamento: 2026-10-24. Fase: P8A catalogo di riferimento BGG completata (schema 25). Restano le attività residue sotto.

## Stato
Catalogo/copie/barcode, ricerca e acquisizione regolamenti e RAG sono implementati. Main comprende provider AI aggiuntivi, ricerca DeepSeek/Groq secondo ruolo e descrizioni AI dei giochi. Per contratti di fase e attività di prodotto resta `docs/ROADMAP.md`; architettura in `docs/ARCHITECTURE.md`.

## Attività aperte
- **P8A catalogo di riferimento BGG** (`docs/P8A_BGG_REFERENCE_CATALOG_CONTRACT.md`). Distribuito il 2026-10-24 (`d151b02`, schema 24): tabella `bgg_reference_games` separata da `board_games`, import automatico di `/data/import/boardgames_ranks.csv` (182.377 titoli, 23.601 visibili con soglia 100), API `/api/reference/*`. UI fatta (impostazioni + ricerca + azioni wishlist/collezione, distribuita con `28d290e`; ripristinato anche `app.css` troncato da `3abc8f9`). Dettagli `/thing` su richiesta e titoli alternativi nel FTS fatti (migrazione 25, distribuita). Worker API con budget distribuito (2026-10-24, `28d290e`, schema 25; backup `/config/backups/boardgamecompanion-pre-m25-20261024T115652Z.sqlite3`). Segnali crowdfunding (abbinamento fail closed, grace configurabile) e lista hot distribuiti (2026-10-24, `4805f7e`, senza migrazione; 28 campagne abbinate al primo giro). Ricontrolli scaglionati per ID distribuiti (`7680a7b`; fine del picco settimanale dei ~29.000 candidati; ultimo picco il 31/10): con questo P8A è completa. Pulizia temporanei: container fermi `bgc-backup-m25-20261024` e `bgc-stats-p8a-20261024`. Backup DB pre-migrazione: `/config/backups/boardgamecompanion-pre-m24-20261024T074728Z.sqlite3`.
- Accettazione fisica Wake-on-LAN soltanto col PC predisposto dal proprietario: spento/sleep → risveglio → LM Studio pronto → operazione richiesta riuscita. Non attivarlo come prova documentale.
- Regolamenti ufficiali IT/EN al posto dei ripieghi, solo con identità esatta e provenienza verificata.
- Volume/retention delle notifiche e ulteriori priorità di prodotto da docs/ROADMAP.

## Decisioni conservate
- Non riaprire incidenti barcode/ricerca universale senza nuova evidenza. I backup WIP del 15 ottobre sono superati, non da importare integralmente: `docs/handoff/2026-10-17-residual-audit.md`.
- Prova Trail conclusa il 22 ottobre: non adottato come integrazione automatica; misure in `docs/TRAIL-PILOT.md`.
- Vecchia adozione NAS Control, provisioning/poller CI e attestazioni non sono gate applicativi. Deploy e percorsi nell'AGENTS; codice applicativo, commit documentali e verifiche runtime restano distinti.
