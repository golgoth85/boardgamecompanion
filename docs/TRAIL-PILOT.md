# Prova locale di Trail Code

Data: 2026-10-22. Sorgenti misurati: `4383c81` di `main`.

Esito: utile come strumento facoltativo di orientamento e per leggere le firme
dei simboli. Non è dimostrato un risparmio di token o di tempo complessivo degli
agenti. Non attivare automaticamente altri componenti.

## Configurazione e uso

- `@trailhq/trail-code@0.23.1`, Node 22.23.2, Python 3 del container.
  Installazione isolata in `~/.local/share/trail-code-0.23.1`, con lock npm locale;
  nessuna dipendenza aggiunta all'applicazione o all'immagine Docker.
- Solo analisi strutturale di `src/` e `tests/`: 116 file Python/JavaScript,
  2.879 simboli più 116 nodi file, 8.167 archi. Nessun passaggio LLM o LSP.
- Il wrapper usa `/temp/boardgamecompanion/trail-code-local/<hash-del-percorso-checkout>`.
  Ogni worktree ha un indice distinto; le interrogazioni verificano la freschezza.
  Il checkout è individuato dal percorso dello script, non dalla directory corrente.
- Prima delle scritture verifica mount `/temp`, scrivibilità e `system.LOCATION`
  dei genitori esistenti, rifiutando cache e `disk2`. Nessun ripiego locale.
  Nella prova: mount `fuse.shfs`, collocazione `disk3`.
- `DO_NOT_TRACK=1` disabilita la telemetria; npm offline impedisce il controllo
  periodico della versione sul registry durante l'uso del wrapper.
- Nessun `trail init`, hook, statusline, MCP, import delle conversazioni,
  memoria automatica, workspace Trail o modifica alle configurazioni degli agenti.
- Il wrapper ammette solo comandi strutturali; non espone `--deep` o invii.
  Filtra il banner che chiede di dichiarare risparmi stimati rispetto a file interi.

Dal checkout da esaminare:

```bash
python3 scripts/trail_local.py build
python3 scripts/trail_local.py build --check
python3 scripts/trail_local.py map
python3 scripts/trail_local.py ask "barcode resolution owned copy lookup"
python3 scripts/trail_local.py ask "answer generation validate citations retrieval current" --source
python3 scripts/trail_local.py skeleton src/boardgamecompanion/barcode_resolution.py
python3 scripts/trail_local.py callers EmbeddingRetrievalService.validate_retrieval_current
python3 scripts/trail_local.py status
```

`ask` restituisce quattro riferimenti con firme; `--source` include il codice
e può produrre estratti lunghi. `build` ricrea la mappa se manca. Lo strumento
non è un requisito per sviluppare, testare o distribuire l'applicazione.

Per reinstallare, verificare prima `/temp` secondo le regole NAS, poi:

```bash
DO_NOT_TRACK=1 npm install \
  --prefix "$HOME/.local/share/trail-code-0.23.1" \
  --cache /temp/boardgamecompanion/trail-install/npm-cache \
  --ignore-scripts --omit=dev --no-audit --no-fund --save-exact \
  @trailhq/trail-code@0.23.1
```

La rete serve per l'installazione. `--ignore-scripts` evita anche il postinstall
di telemetria; nella prova i parser funzionano senza rebuild. Eliminare la sola
cache npm di installazione a fine operazione.

## Misure e verifica

Una esecuzione per variante dopo la costruzione dell'indice. Tempi reali e byte
UTF-8 su stdout, non token fatturati. Ogni `ask` controlla anche la freschezza.
Grep usa nomi di simboli già noti; Trail una domanda e quattro risultati. Le
operazioni non restituiscono contenuto identico e non sono task completi di un agente.

| Caso | grep: secondi / byte | Trail sintetico: secondi / byte | Trail con codice: secondi / byte |
| --- | --- | --- | --- |
| Barcode | 0,039 / 2.396 | 2,412 / 678 | 2,442 / 3.222 |
| RAG | 0,044 / 2.050 | 2,823 / 1.294 | 3,212 / 11.358 |
| Risveglio LM Studio | 0,050 / 2.221 | 3,194 / 635 | 3,484 / 6.896 |

Domande Trail, nell'ordine:

1. `barcode resolution owned copy lookup`
2. `answer generation validate citations retrieval current`
3. `LMStudioEmbeddingProvider wake endpoint ready`

Grep: `grep -R -n -E --include='*.py' --include='*.js' '<pattern>' src tests`:

1. `BarcodeResolver|lookup_barcode|lookupScannerBarcode`
2. `AnswerGenerationService|validate_retrieval_current|answer_game_question`
3. `LMStudioEmbeddingProvider|_ensure_endpoint_ready|def wake\(`

I dodici riferimenti restituiti puntano a intervalli esistenti. La lettura diretta
conferma endpoint e scanner barcode, generazione e validazione RAG, preparazione
del provider e endpoint/UI di risveglio. Alcuni hit sono meno utili: una classe
di errore per il barcode e una validazione dei chunk per il RAG.

`skeleton barcode_resolution.py`: 3.169 byte di firme contro 26.341 del file
intero. Utile per orientarsi; non contiene i corpi delle funzioni.

Limite concreto: `callers validate_retrieval_current` trova una chiamata nello
stesso file ma omette quattro usi in `answer_generation.py`, segnalando ambiguità
con omonimi nei test. Anche qualificando il nome con `EmbeddingRetrievalService`
quelle chiamate mancano. L'assenza di archi non dimostra assenza di dipendenze:
verificare con ricerca testuale e lettura del codice.

Decisione: mantenere l'uso facoltativo con risposte sintetiche. In questi esempi
restituiscono meno testo, mentre `--source` lo aumenta; entrambe le varianti sono
più lente di grep. Non sono stati misurati task completi, costi API o consumo
effettivo degli agenti: nessuna percentuale di risparmio token è attribuibile alla prova.

## Stato locale e annullamento

Validati `build --check`, `map` (anche lanciato fuori dal checkout), `status`,
`ask` con e senza sorgenti, `skeleton` e `callers`. Verificato il rifiuto di
`--deep`, file esterni e combinazioni di argomenti non ammesse. Nessuna modifica
al codice dell'app: non eseguiti pytest applicativi o prove browser.

Restano installati il programma e la mappa richiesta (circa 15 MiB), separati
dai file temporanei del confronto. Cache npm di prova ed estratti del confronto
vengono rimossi dopo aver conservato questo resoconto leggero.
Nessun servizio applicativo importato, avviato o chiamato; nessun Wake-on-LAN.
Nessun cambiamento a UI, dati, immagine, mount o configurazione di produzione.
Il revert del commit del pilot annulla l'integrazione nel repository;
programma e indice locali restano inerti se non invocati.
