# BoardGameCompanion — current roadmap

Stato operativo riesaminato il 2026-10-17; verifica funzionale storica del 2026-10-13,
confermata per identità dei sorgenti montati e salute nel nuovo audit.
Older phase documents remain useful as architectural history, but
they must not be read as unfinished product milestones.

## Current product state

BoardGameCompanion is a standalone, self-hosted companion for a physical board-game
collection. The major product areas below are implemented on `main` and have
production evidence:

- BGG collection synchronization, metadata enrichment, catalog search/filtering,
  rankings and Explore views;
- personal ratings, played/completed state, lists, wishlist, global search and
  notifications;
- barcode/copy workflow, including verified exact-GTIN resolution and fallback
  provider matching;
- bidirectional localized/original title aliases in universal search;
- game-centric detail pages;
- rulebook discovery, review, guarded acquisition, archival, scheduled updates,
  PDF ingest, chunking, embeddings, retrieval and grounded Q&A;
- bounded catalog-wide YouTube tutorial discovery with IT-first/EN fallback;
- personalized Suggestions with a bounded rotating/history-aware candidate pool;
- owned-catalog AI recommendations ("Consigliami un gioco") with deterministic
  hard-constraint filtering before model ranking;
- Gamefound/Kickstarter crowdfunding discovery with board-game relevance filtering;
- relevant-expansion discovery and notifications;
- LM Studio/Gemini provider configuration, diagnostics and Wake-on-LAN;
- browser-capable Universal Local CI with Python, JavaScript and Playwright coverage;
- trusted immutable container publication and deployment through the NAS control
  plane, including GHCR publication.

The full information-architecture/UI redesign is no longer a future phase: the
current UI already incorporates the redesign and subsequent simplification work.

## Rulebooks — completed core work

The 2026-10-10 live audit found 154 owned catalog titles and no uncovered title:

- 120 have an official Italian or English rulebook PDF;
- 10 have a usable fallback PDF while background discovery continues looking for
  a preferred official IT/EN source;
- 24 are curated cases where a normal standalone PDF is not expected or where
  rules are carried by another official artifact (components/cards, physical
  booklet, shared/external exact manual, etc.);
- `uncovered_total = 0`.

Periodic discovery stops for games already resolved by an official IT/EN PDF or a
curated no-standalone-PDF classification, while fallback-only titles remain eligible
for improvement. Manual forced discovery remains available.

RAG was verified live end to end: LM Studio embeddings + Gemini generation returned
a grounded Italian answer from an official Italian rulebook with a page-level
citation and no version conflict.

Rulebook work is therefore maintenance rather than a product phase. Remaining
activity is opportunistic: replace fallback documents with preferred official
IT/EN sources when exact identity can be verified.

## Barcode and universal search — incident closed

The production barcode incident for the two Italian GTINs is closed on deployed
functional revision `7973d11dae98c7121998e0a73f2ced0290903348`.

Live structured post-deploy evidence confirms:

- `8034055580424` → Nome in Codice / Codenames → BGG `178900`,
  `owned_game`, `verified_catalog`, confidence `1.0`;
- `8034055581032` → Sagrada → BGG `199561`,
  `owned_game`, `verified_catalog`, confidence `1.0`;
- L5R regression barcode remains BGG `184151`, confidence `1.0`;
- 7 Wonders Duel remains BGG `173346` through UPCitemdb, confidence `0.842`.

Universal search also remains production-verified for localized/original aliases:
`Codenames` and `Nome in Codice` resolve to the same owned game.

Do not reopen either incident without new production regression evidence.

## Expansions — major-only policy

The game-detail expansion box intentionally does not mirror every BGG expansion
link. It rejects obvious micro-content (promos, packs, accessories, minis,
replacement/media items, etc.) and selects the materially relevant cohort using
BGG ownership relative to the most widely owned expansion for that base game,
with a bounded result set.

Live verification on Arena: The Contest reduced the linked expansion set to six
material expansions and filtered fifteen marginal entries.

## Recently completed roadmap items

The following items were previously listed as future work but are now implemented
and should remain in regression/maintenance scope rather than the active roadmap:

- Suggestions candidate expansion/rotation and history-aware reuse prevention;
- deterministic hard constraints for the owned-catalog assistant;
- bounded background tutorial discovery;
- crowdfunding board-game relevance filtering;
- browser-capable Universal Local CI using profile `pytest-browser-v1`, including
  Python, JavaScript and Playwright coverage while preserving exact-source-SHA and
  cleanup attestation;
- trusted immutable container publication, including working GHCR publication.

## Residual roadmap

### P1 — Wake-on-LAN physical acceptance

The BGC endpoint emits the magic packet and LM Studio is reachable after a wake
request. The remaining acceptance is intentionally physical and should only be run
when the operator places the gaming PC into a real sleep/off state:

`sleep/off -> BGC wake -> PC online -> LM Studio ready -> AI operation succeeds`.

Do not simulate this by restarting services on an already awake machine.

### P2 — Rulebook source quality

Continue opportunistically replacing fallback-only rulebooks with preferred official
IT/EN sources when exact title/edition identity can be verified. This is maintenance,
not a blocker for normal product use.

### P2 — Operational maintenance

- keep this roadmap, README and AGENTS.md aligned with current runtime behavior;
- keep notification volume/retention under review as background producers grow;
- preserve exact deployed revision tracking separately from later docs-only `main`
  commits;
- remove or close superseded branches/PRs rather than treating them as active work;
- retain raw structured post-deploy evidence for runtime-sensitive regressions.

## Architectural invariants

- BGC remains standalone for core board-game workflows.
- BGG `objectid` is the canonical external game identity.
- BGG version product codes are not UPC/EAN/ISBN identifiers.
- The physical-copy invariant remains:

  `barcode -> OwnedCopy -> BoardGame`

- Rulebook auto-acquisition remains fail-closed: exact identity, trusted source and
  policy approval are required.
- Community or lower-confidence documents never silently replace authoritative
  sources.
- RAG answers remain grounded in archived evidence with page citations and explicit
  conflict/not-found behavior.
- External provider failures must degrade gracefully without making the local
  catalog unusable.

## Riesame operativo del 2026-10-17

I backup `backup/suggestions-v1-wip-20261015` e
`backup/personal-ux-macro18-wip-20261015` sono stati valutati: le capacità di
prodotto sono già presenti in versioni successive; il backup UX usa anche tabelle
e contratti incompatibili con quelli correnti. Non importarli né considerarli
milestone aperte. Branch conservati, nessuna cancellazione.
Prove e limiti: [audit del checkpoint](handoff/2026-10-17-residual-audit.md).

Le regole operative correnti sono in `AGENTS.md` e `/workspace/AGENTS.md`:
branch, test pertinenti, pubblicazione GitHub e merge secondo l'annullabilità;
Local CI facoltativa. Il deploy usa il pacchetto montato e UnraidClaw, con backup
del codice e verifica runtime. Il precedente protocollo obbligatorio è superato.
