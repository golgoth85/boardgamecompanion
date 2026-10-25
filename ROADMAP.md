# BoardGameCompanion — roadmap

Aggiornamento: 2026-10-22. Fase: manutenzione e sviluppo del catalogo/AI; nessuna distribuzione implicata dalla riorganizzazione dei documenti.

## Stato
Catalogo/copie/barcode, ricerca e acquisizione regolamenti e RAG sono implementati. Main comprende provider AI aggiuntivi, ricerca DeepSeek/Groq secondo ruolo e descrizioni AI dei giochi. Per contratti di fase e attività di prodotto resta `docs/ROADMAP.md`; architettura in `docs/ARCHITECTURE.md`.

## Attività aperte
- Accettazione fisica Wake-on-LAN soltanto col PC predisposto dal proprietario: spento/sleep → risveglio → LM Studio pronto → operazione richiesta riuscita. Non attivarlo come prova documentale.
- Regolamenti ufficiali IT/EN al posto dei ripieghi, solo con identità esatta e provenienza verificata.
- Volume/retention delle notifiche e ulteriori priorità di prodotto da docs/ROADMAP.

## Decisioni conservate
- Non riaprire incidenti barcode/ricerca universale senza nuova evidenza. I backup WIP del 15 ottobre sono superati, non da importare integralmente: `docs/handoff/2026-10-17-residual-audit.md`.
- Prova Trail conclusa il 22 ottobre: non adottato come integrazione automatica; misure in `docs/TRAIL-PILOT.md`.
- Vecchia adozione NAS Control, provisioning/poller CI e attestazioni non sono gate applicativi. Deploy e percorsi nell'AGENTS; codice applicativo, commit documentali e verifiche runtime restano distinti.
