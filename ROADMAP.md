# Roadmap e cose da fare

Ultimo aggiornamento: 2026-10-18 (fase: provider AI aggiuntivi e semplificazione impostazioni; prossimo gate di prodotto: accettazione fisica Wake-on-LAN).

Il progetto ha già una roadmap dettagliata e documenti di fase: restano dove sono.
- Roadmap corrente: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Contratti di fase: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`P3B`](docs/P3B_BARCODE_CAMERA_CONTRACT.md), [`P7A`](docs/P7A_PDF_INGEST_CONTRACT.md), [`P7B`](docs/P7B_CHUNK_INDEX_CONTRACT.md), [`P7C`](docs/P7C_EMBEDDING_RETRIEVAL_CONTRACT.md), [`P7D`](docs/P7D_ANSWER_GENERATION_CONTRACT.md), [`P7E`](docs/P7E_QUERY_UI_CONTRACT.md), [`P7 remediation`](docs/P7_PHASE7_REMEDIATION.md), [`readiness UI`](docs/PRE_UI_REDESIGN_READINESS.md), [`publisher-first`](docs/PUBLISHER_FIRST_DISCOVERY.md)

## Ora
- [ ] Local CI: aggiunto `scripts/ci_local.py` (2026-10-16), l'elenco unico dei controlli, equivalente alla funzione storica del guest (`boardgamecompanion_checks`). Il guest lo usa solo dopo la ricostruzione del template del repo con il runner d40i (`local-ci-lab`); fino ad allora usa la funzione storica. `local-ci.yml` resta finche' il poller lato NAS non e' attivo.
- [ ] Accettazione fisica del Wake-on-LAN (P1): solo quando il PC da gioco è davvero in sleep/off; sequenza `sleep/off -> wake da BGC -> PC online -> LM Studio pronto -> operazione AI riuscita`.

## Prossimo
- [ ] Sostituire i regolamenti di ripiego con fonti ufficiali IT/EN quando l'identità esatta è verificabile (P2, manutenzione).
- [ ] Tenere sotto controllo volume e retention delle notifiche mentre crescono i produttori in background.
- [ ] Allineare `README.md`, questo file e `docs/ROADMAP.md` ad ogni fase.

## Più avanti
- [ ] Lavoro di prodotto ordinario dalle priorità correnti di `docs/ROADMAP.md`. Non riaprire gli incidenti barcode e ricerca universale senza nuova evidenza di produzione.

## Fatto di recente
- 2026-10-18: aggiunti DeepSeek e Groq per le funzioni testuali; DeepSeek Search/Fetch come alternativa web a Gemini. Impostazioni con priorità a caselle/frecce, scelta dei modelli e verifica della chiave; nessun cambio allo schema o all'indice embeddings. Attivazione reale dopo inserimento della chiave del proprietario e salvataggio della preferenza.
- Valutati i due backup WIP del 2026-10-15: versioni alternative superate dalle funzioni già su `main`, da non importare. I branch restano conservati; dettagli e prove in [`docs/handoff/2026-10-17-residual-audit.md`](docs/handoff/2026-10-17-residual-audit.md).
- Barcode `8034055580424` (Codenames) e `8034055581032` (Sagrada) risolti in produzione sulla revisione `7973d11` (2026-10-13), più ricerca universale con titoli localizzati/originali.

## Infrastruttura corrente

Il regime semplificato del 2026-10-17 sostituisce l'adozione obbligatoria: Local CI facoltativa, codice da commit pubblicato, backup del codice e deploy tramite mount e riavvio UnraidClaw. Vedi `AGENTS.md` e `/workspace/AGENTS.md`. La PR #153 sul poller CI resta separata e condizionata alla sua effettiva attivazione; non è un gate di prodotto.

Verifica in sola lettura del 2026-10-17: i 70 file del pacchetto montato coincidono con `7973d11dae98c7121998e0a73f2ced0290903348`; `/health` restituisce HTTP 200, `status=ok`, schema 21. L'audit non ha eseguito deploy né modifiche ai dati.
