# Roadmap e cose da fare

Ultimo aggiornamento: 2026-10-15 (fase: manutenzione di prodotto dopo la chiusura dell'incidente barcode).

Il progetto ha già una roadmap dettagliata e documenti di fase: restano dove sono.
- Roadmap corrente: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Contratti di fase: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`P3B`](docs/P3B_BARCODE_CAMERA_CONTRACT.md), [`P7A`](docs/P7A_PDF_INGEST_CONTRACT.md), [`P7B`](docs/P7B_CHUNK_INDEX_CONTRACT.md), [`P7C`](docs/P7C_EMBEDDING_RETRIEVAL_CONTRACT.md), [`P7D`](docs/P7D_ANSWER_GENERATION_CONTRACT.md), [`P7E`](docs/P7E_QUERY_UI_CONTRACT.md), [`P7 remediation`](docs/P7_PHASE7_REMEDIATION.md), [`readiness UI`](docs/PRE_UI_REDESIGN_READINESS.md), [`publisher-first`](docs/PUBLISHER_FIRST_DISCOVERY.md)

## Ora
- [ ] Accettazione fisica del Wake-on-LAN (P1): solo quando il PC da gioco è davvero in sleep/off; sequenza `sleep/off -> wake da BGC -> PC online -> LM Studio pronto -> operazione AI riuscita`.

## Prossimo
- [ ] Sostituire i regolamenti di ripiego con fonti ufficiali IT/EN quando l'identità esatta è verificabile (P2, manutenzione).
- [ ] Tenere sotto controllo volume e retention delle notifiche mentre crescono i produttori in background.
- [ ] Allineare `README.md`, questo file e `docs/ROADMAP.md` ad ogni fase.

## Più avanti
- [ ] Lavoro di prodotto ordinario dalle priorità correnti di `docs/ROADMAP.md`. Non riaprire gli incidenti barcode e ricerca universale senza nuova evidenza di produzione.

## Fatto di recente
- Barcode `8034055580424` (Codenames) e `8034055581032` (Sagrada) risolti in produzione sulla revisione `7973d11` (2026-10-13), più ricerca universale con titoli localizzati/originali.
