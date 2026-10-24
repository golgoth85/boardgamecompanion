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

- Fatto: migrazione 22 (`bgg-reference-catalog`), importatore del dump,
  ricerca FTS con soglia, impostazioni `min_votes`/`include_expansions`, API
  `/api/reference/{status,search,import-dump,settings}`.
- Da fare: UI, worker API e dettagli su richiesta, segnali crowdfunding/hot/in
  uscita.

## Rilascio

1. Migrazione additiva con backup del DB.
2. Import del dump e verifica dei conteggi.
3. Ricerca e autocompletamento sul catalogo di riferimento.
4. Worker API; poi abbinamento crowdfunding.
