# Migrazione 31 della Ludoteca

Il possesso viene calcolato per `objectid` BGG. Un gioco risulta posseduto se almeno una delle righe d’origine è posseduta. Restano le righe BGG per provenienza, commenti e stati importati. La migrazione conserva giochi, partite, profili, PDF, pagine, passaggi citabili, raccolte e wishlist. Un gioco già rimosso resta nel catalogo locale e mantiene il suo storico.

## Dati del vecchio inventario

La tabella `physical_copies` conteneva identificativo e origine della copia, barcode, lingua, edizione, editore, anno, acquisto, prezzo e valuta, condizioni, posizione, note e date di modifica. Questi valori si recuperano dal backup dello schema 30. Le note, le edizioni e la data di acquisizione a livello del gioco rimangono nei dati d’origine. La migrazione rimuove i campi d’inventario anche dalle colonne di `collection_entries` e dalle chiavi equivalenti nei dati CSV di origine indicizzati dal catalogo. Gli eventuali CSV originali già archiviati in `/data/import` rimangono disponibili.

I barcode manuali, compresi quelli corretti dall’utente su righe importate, diventano suggerimenti di riconoscimento del prodotto da verificare. I barcode derivati automaticamente dagli import precedenti restano nel backup e nei CSV originali. I codici prodotto delle versioni BGG sono distinti dai GTIN.

L’audit iniziale in produzione ha contato 157 righe d’inventario, tre barcode e zero note. Lingua, edizione, editore, anno, acquisto, prezzo, valuta, condizioni e posizione erano vuoti nelle 157 righe. L’audit a container fermo ripete questi conteggi prima del backup.

Per recuperare un campo storico, aprire una copia del backup con SQLite in sola lettura. `physical_copies.board_game_id` si collega a `board_games.id`. La colonna `physical_copies.notes` contiene le note delle singole righe. Il backup include dati privati e va tenuto in `/config/backups`.

## Backup, applicazione e ripristino

1. Conservare il codice della release schema 30 nel percorso di backup del deploy. Verificare la candidata in un’istanza isolata. Fermare soltanto `BoardGameCompanion`.
2. Con la candidata accessibile da `PYTHONPATH`, eseguire `python scripts/library_migration.py apply /config/boardgamecompanion.sqlite3 /config/backups/boardgamecompanion-pre-m31-<data>.sqlite3`. Il comando verifica lo schema, usa il backup SQLite coerente con WAL, confronta il backup con l’originale e applica la migrazione. Verifica integrità, chiavi esterne e impronte dei dati preservati, incluse partite, profili, pagine, passaggi e wishlist. L’output riporta soltanto totali e percorsi.
3. Installare la candidata pubblicata su `main` nel mount indicato in `AGENTS.md`. Avviare il container. Controllare `/health` allo schema 31, gli endpoint della Ludoteca e delle partite, il conteggio dei documenti e il caricamento della UI.
4. Per annullare la migrazione, fermare l’applicazione. Eseguire lo stesso script con `restore` e lo stesso percorso di backup. Lo script verifica e copia il database schema 30, conserva database e file WAL/SHM dello schema 31 in `/config/backups/rollback-m31` e installa il ripristino. Ripristinare il codice abbinato allo schema 30, avviare e controllare `/health`, possesso, partite e file PDF. Dopo un periodo d’uso della release 31, tenere conto delle nuove scritture conservate nella quarantena prima di sostituire il database attivo.

## Esito in produzione del 27 novembre 2026

La revisione `d9d6fe8` ha applicato lo schema 31. La revisione `c2a94c8` è attiva con lo stesso schema. Il backup SQLite `/config/backups/boardgamecompanion-pre-m31-20261127-d9d6fe8.sqlite3` è integro e leggibile allo schema 30. Il codice corrispondente al backup si trova in `/workspace/_prod/BoardGameCompanion/boardgamecompanion.backup-library-20261127-d9d6fe8`. Il backup del solo aggiornamento Impostazioni, compatibile con lo schema 31, è `/workspace/_prod/BoardGameCompanion/boardgamecompanion.backup-settings-20261127-c2a94c8`.

Il confronto ha conservato 174 giochi, di cui 173 posseduti, 31 partite, 3 sessioni, 4 profili, 170 documenti, 2.905 pagine, 6.896 passaggi indicizzati, una raccolta e cinque voci Wishlist. La migrazione ha ritirato 157 righe del vecchio inventario e conservato tre barcode come suggerimenti da verificare. Il ripristino è stato eseguito su un database sintetico dello schema 30, inclusa una nota manuale disponibile soltanto nel vecchio inventario.

Dopo il riavvio sono stati verificati `/health`, asset JavaScript del commit, possesso, proposte locali, diario, wishlist e apertura di un PDF. I controlli reali Chromium sono stati in sola lettura. I container temporanei `bgc-library-audit-20261127` e `bgc-library-m31-20261127` sono fermi. UnraidClaw ha negato la cancellazione. Lo script `/workspace/_prod/BoardGameCompanion/cleanup-ludoteca-m31-20261127.sh` rimuove soltanto quei container dal NAS.
