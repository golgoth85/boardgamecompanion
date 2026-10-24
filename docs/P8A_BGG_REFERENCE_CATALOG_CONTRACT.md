# P8A — Catalogo di riferimento BGG

## Scopo

Dare a BGC una copia locale dell'anagrafica BGG (non solo della collezione
personale) da usare per ricerca, autocompletamento, risoluzione di barcode e
titoli, wishlist e abbinamento delle campagne crowdfunding, anche senza rete.

Il catalogo di riferimento è separato da `board_games`: un titolo entra in
`board_games` solo per azione dell'utente (copia fisica, wishlist, import
collezione). Le funzioni che oggi leggono `board_games` (catalogo, suggerimenti,
espansioni, discovery regolamenti, notifiche) non vedono il catalogo di
riferimento.

## Fonti

1. **Avvio (una tantum)**: `boardgames_ranks.csv` dai Data Dumps BGG, scaricato
   dal proprietario e posato in `/data/import`. BGC non lo scarica mai da sé.
2. **Aggiornamento continuo**: solo XML API2 (`/thing?...&stats=1`) con token
   applicativo, tramite il limitatore condiviso `bgg:xmlapi2`.
3. **Senza token**: il catalogo resta fermo all'ultimo import; nessun errore
   bloccante, stato visibile nelle impostazioni.

## Modello dati (migrazione additiva)

`bgg_reference_games`
- `bgg_id` INTEGER PRIMARY KEY
- `name`, `year_published`, `is_expansion`
- `rank`, `bayes_average`, `average`, `users_rated`
- `wishing`, `owned_count` (solo da API, NULL se mai interrogato)
- `thumbnail_url`, `image_url`, `description`, `details_json` (solo da API)
- `admission_reason`: `votes` | `crowdfunding` | `hot` | `upcoming` | NULL
- `admission_until` (scadenza delle ammissioni per segnale)
- `source` (`dump` | `api`), `dump_imported_at`, `api_checked_at`, `next_check_at`
- `removed_at` (ID sparito da BGG: marcato, mai cancellato)

Indice FTS5 su `name` (più titoli alternativi quando noti da API).

`bgg_reference_sync_state`: massimo ID visto, cursori dei job, budget del
giorno, ultimo errore. Tutto su `/config`.

Si importano **tutte** le righe del dump, anche sotto soglia: la soglia è un
filtro di lettura, quindi cambiarla non richiede né cancellazioni né nuove
richieste a BGG.

## Ammissione

Un titolo è visibile nel catalogo di riferimento se vale almeno una regola:

1. `users_rated >= bgg_reference_min_votes` (impostazione runtime, default 100).
2. **Crowdfunding**: campagna attiva o in arrivo (Gamefound/Kickstarter, modulo
   `crowdfunding`) abbinata in modo univoco a un `bgg_id`. Resta ammesso per
   `bgg_reference_crowdfunding_grace_days` dopo la chiusura (default 540, per
   coprire produzione e consegna).
3. **In uscita**: anno di pubblicazione ≥ anno corrente − 1 oppure assente, con
   `wishing >= bgg_reference_min_wishing` (default 50).
4. **Hot**: presente nella lista hot BGG; resta ammesso 90 giorni.

Un titolo già in `board_games` è sempre risolvibile, a prescindere da queste
regole. Quando un titolo raggiunge la soglia voti, `admission_reason` passa a
`votes` e la scadenza non conta più.

Abbinamento campagna → `bgg_id` fail closed: solo titolo normalizzato esatto e
univoco tra i candidati recenti/non pubblicati; altrimenti nessun
collegamento (la campagna resta visibile come oggi, senza `bgg_id`).

## Job in background

Un solo worker, budget giornaliero di richieste (`bgg_reference_daily_budget`,
default 1500), precedenza alle richieste interattive.

| Coda | Cosa | Frequenza indicativa |
|---|---|---|
| Nuovi ID | `/thing` sugli ID oltre il massimo visto, fino a 3 lotti vuoti consecutivi | giornaliera |
| Candidati | titoli recenti/non pubblicati sotto soglia: aggiorna voti e `wishing` | settimanale |
| Ammessi | titoli visibili: rank, voti, peso | a rotazione, giro ≤ 14 giorni |
| Segnali | lista hot, campagne crowdfunding | a ogni scansione esistente |

I titoli sotto soglia più vecchi di due anni non vengono ricontrollati.

## Descrizioni e dettagli

Il dump contiene solo nome, anno, rank, medie e voti. Il resto arriva da
`/thing?stats=1`, che restituisce già nella stessa risposta descrizione,
immagini, titoli alternativi (anche italiani), giocatori, durata, età, peso,
autori, editori, categorie, meccaniche e sondaggio sul numero di giocatori:

- ogni risposta dei job viene salvata per intero, senza richieste aggiuntive;
- aprendo un titolo mai interrogato, una richiesta singola su richiesta
  dell'utente (stesso limitatore), con il dato del dump mostrato subito;
- immagini come URL della CDN BGG, mai scaricate in massa;
- traduzione AI della descrizione e riassunto di gioco solo dopo la promozione
  in `board_games`, con i servizi esistenti;
- titoli alternativi indicizzati nel FTS dopo la prima risposta API.

## Impostazioni (pagina impostazioni, salvate in `app_settings`)

- `bgg_reference_min_votes` (≥ 0, nessun massimo, default 100; 0 mostra tutto)
- `bgg_reference_min_wishing` (0–10000, default 50; 0 disattiva la regola 3)
- `bgg_reference_crowdfunding_grace_days` (0–1095, default 540)
- `bgg_reference_include_expansions` (default sì)
- `bgg_reference_daily_budget` (0–5000, default 1500; 0 sospende il worker)

## Import del dump

- Idempotente: upsert per `bgg_id`; un import più vecchio dei dati API non li
  sovrascrive (confronto `dump_imported_at` / `api_checked_at`).
- Validazione dell'intestazione e delle colonne; righe malformate scartate e
  contate, mai import parziale silenzioso.
- Automatico: all'avvio e poi ogni ora BGC controlla
  `/data/import/boardgames_ranks.csv`; importa solo se il contenuto (sha256) non
  è già in `import_runs`. Nessuna azione dell'utente. Il file non viene
  spostato né cancellato. `/api/reference/import-dump` resta per forzare.

## Fuori scope

- Download automatico del dump o qualsiasi accesso autenticato a BGG.
- Download di immagini o richieste dedicate solo alle descrizioni.
- Promozione automatica in `board_games`.
- Scansione completa dell'intervallo ID come avvio alternativo al dump.

## Test richiesti

Parsing del dump (intestazioni, quote, righe malformate), idempotenza
dell'import, filtro soglia, scadenza delle ammissioni per segnale, abbinamento
campagne (univoco / ambiguo / assente), cursore nuovi ID e arresto sui lotti
vuoti, rispetto del budget, comportamento senza token, nessun effetto su
`board_games`.

## Stato

- Fatto e distribuito (2026-10-24, `d151b02`): migrazione 24
  (`bgg-reference-catalog`), importatore del dump in lotti da 5000 righe con
  import automatico, ricerca FTS con soglia, impostazioni
  `min_votes`/`include_expansions`, API
  `/api/reference/{status,search,import-dump,settings}`. Produzione: 182.377
  titoli, 23.601 visibili con soglia 100.
- Limite noto: i nomi del dump sono solo quelli principali BGG; titoli
  italiani (es. «Castelli della Borgogna») non si trovano finché non arrivano
  i titoli alternativi da `/thing`.
- Fatto (distribuito 2026-10-24, `28d290e`, schema 25): UI. Scheda «Catalogo di riferimento» nelle
  impostazioni (soglia voti, espansioni, stato import); gruppo «Catalogo BGG»
  nella ricerca globale con wishlist (`source_kind=bgg`) e «Collezione»
  (`POST /api/reference/{bgg_id}/collection`: crea riga `board_games` e voce
  collezione `own=1`, idempotente, senza sovrascrivere).
- Fatto (distribuito 2026-10-24, `28d290e`, schema 25): dettagli su richiesta. Migrazione 25
  (`bgg-reference-alt-names`: colonna `alt_names`, FTS a due colonne
  ricostruito). `GET /api/reference/{bgg_id}` restituisce la riga e, solo se
  mai interrogata, fa una `/thing?stats=1` singola (stesso limitatore e token
  dei job); salva descrizione, immagini, titoli alternativi, rank/voti/wishing e
  `details_json` (metadati del parser più `raw_xml`, l'XML completo
  dell'item con sondaggi inclusi: lo spazio sul NAS non è un vincolo; l'API
  non lo restituisce) e valorizza `api_checked_at`. Senza
  token o con BGG in errore risponde comunque con i dati del dump
  (`detail_error`). UI: scheda dettagli aperta dal titolo nei risultati.
- Fatto (distribuito 2026-10-24, `28d290e`, schema 25): worker API (`bgg_reference_worker.py`),
  un ciclo ogni ora (`bgg_reference_api_poll_seconds`, disattivabile con
  `bgg_reference_api_worker_enabled`). Senza token non fa nulla
  (`status: no_token`). Budget giornaliero in richieste (ogni `/thing` da 20 ID
  è una richiesta), contatore UTC in `bgg_reference_sync_state`. Code in ordine:
  1. nuovi ID oltre il massimo visto, una scansione al giorno, stop dopo 3
     lotti vuoti; il cursore resta sull'ultimo ID reale, quindi la coda vuota
     si riprova il giorno dopo; accettati solo `boardgame`/`boardgameexpansion`;
  2. candidati (anno ≥ anno corrente − 1 o assente, voti sotto soglia), ricontrollo
     ogni 7 giorni; con `wishing ≥ min_wishing` ammissione `upcoming` per 30
     giorni, mai sopra un'ammissione crowdfunding/hot; i titoli sotto soglia più
     vecchi non vengono toccati;
  3. rotazione degli ammessi per voti (`next_check_at` +14 giorni).
  Ogni risposta è salvata con l'XML completo; un ID assente da un lotto non
  vuoto è marcato `removed_at` (mai cancellato), una risposta completamente vuota
  rinvia il lotto di 6 ore. Impostazioni `min_wishing` e `daily_budget` in API e
  UI; `/api/reference/status` include lo stato del worker.
- Fatto e distribuito (2026-10-24, `4805f7e`, nessuna migrazione, schema 25): segnali. A ogni giro del worker,
  prima delle code BGG e anche senza token, le campagne già in cache del modulo
  `crowdfunding` (nessuna richiesta di rete) sono abbinate fail closed:
  titolo normalizzato uguale al nome o a un titolo alternativo di **un solo**
  titolo recente/non pubblicato non rimosso; ambiguo o assente → nessun
  collegamento. Campagne `failed`/`canceled`/`suspended` ignorate.
  L'abbinamento dà `crowdfunding` fino a chiusura (o oggi, se non ancora
  lanciata) + `bgg_reference_crowdfunding_grace_days` (UI nella scheda); i
  collegamenti sono in `bgg_reference_sync_state` (`crowdfunding_matches`),
  esposti come `bgg_id` in `GET /api/crowdfunding` e contati in
  `/api/reference/status` (`worker.crowdfunding_matched`). Lista hot
  (`/hot?type=boardgame`, una richiesta al giorno nel budget): ID sconosciuti
  inseriti via `/thing`, ammissione `hot` per 90 giorni. Le ammissioni per
  segnale valgono solo sotto soglia voti e vince la scadenza più lontana (una
  `upcoming` di 30 giorni non accorcia una `crowdfunding`/`hot`). Nessuna
  scrittura su `board_games`.
  Primo giro in produzione: 28 campagne abbinate (27 attive su 74), visibili
  da 25.404 a 25.418; la lista hot parte col budget del giorno dopo.
- Osservato in produzione (2026-10-24, primo giorno): budget 1500/1500 usato,
  29.865 titoli interrogati, solo `boardgame`/`boardgameexpansion`, 1 ID
  marcato rimosso, 1.798 ammissioni `upcoming`, nessun errore. La coda
  candidati conta circa 29.000 titoli (anno recente o assente).
- Fatto e distribuito (2026-10-24, `7680a7b`): ricontrolli scaglionati. Ogni ID ha i propri giorni del
  ciclo (`(giorno + bgg_id) % giorni_ciclo == 0`); dopo un controllo il
  successivo cade sul primo di questi entro il ciclo (da 1 a 7/14 giorni). Il
  primo giro in blocco si distribuisce quindi sul ciclo seguente e poi resta
  distribuito: a regime circa 210 richieste/giorno per i candidati e 90 per gli
  ammessi, su 1.500. Le date già fissate (candidati al 31/10) restano: quel
  giorno è l'ultimo picco.

## Rilascio

1. Migrazione additiva con backup del DB.
2. Import del dump e verifica dei conteggi.
3. Ricerca e autocompletamento sul catalogo di riferimento.
4. Worker API; poi abbinamento crowdfunding.
