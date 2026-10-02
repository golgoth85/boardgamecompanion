# Pre-redesign acceptance — 2026-10-02

This document freezes the backend/product behavior that the upcoming UI information-architecture redesign must preserve. It records live acceptance evidence; it is not a promise that external publisher sites will remain stable.

## Catalog and collection

Live production catalog inventory: 144 games.

The real-collection sample used before the redesign includes base games and expansions such as:

- 7 Wonders Duel / 7 Wonders Duel: Pantheon
- Black Rose Wars / Black Rose Wars: Crono Expansion
- The 7th Continent / What Goes Up, Must Come Down
- Tiny Epic Dungeons / Tiny Epic Dungeons: Stories

At the time of the survey, only 7 Wonders Duel had an archived official Italian rulebook. This is why manual acquisition and a generic web-search fallback remain first-class behavior.

## Rulebook acquisition decision

A bounded live provider sample of four base games and four expansions was executed against the known-source adapters. The sample did not produce the required official Italian candidates; failures were dominated by upstream HTTP/browser-fallback failures across Repos/Asmodee/Pendragon-style sources.

A real-collection inspection of 7 Wonders Duel: Pantheon likewise failed in the Repos provider browser fallback before an official Italian candidate could be established.

These failures are treated as evidence that publisher-specific discovery cannot be the only user path. They are **not** a reason to add more game-specific scraping.

The stable product contract is therefore:

1. one **Cerca regolamento** action on the game page;
2. first click runs the known-source discovery pipeline (IT before EN);
3. if the run returns no candidates **or the provider pipeline cannot complete**, the same action becomes **Cerca PDF su Google**;
4. Google opens a human-reviewed search only;
5. Google never downloads, imports, approves or trusts a PDF automatically;
6. manual upload remains the final acquisition step when the automatic pipeline cannot archive a trusted document.

## RAG acceptance

The live production RAG path has been validated end-to-end on the archived official Italian 7 Wonders Duel rulebook:

- PDF parsing and page identity;
- deterministic chunks;
- Gemini embeddings;
- retrieval;
- Gemini 3.8 Flash answer generation;
- prompt-only JSON fallback after structured-output 503;
- citation whitespace canonicalization;
- exact source quote returned to the response;
- server-owned document/page/chunk provenance.

The accepted live answer identified 7 Wonders Duel as a two-player game and verified the cited quote against page 2 of the archived PDF.

Gemini rate/quota 429 responses remain an external availability condition and are not a reason to silently switch provider or weaken provenance.

## Update scheduler

The production rulebook-update API returns HTTP 200. The persistent worker is enabled with a 60-second poll and batch size 5. At the time of this acceptance snapshot there were no approved update targets, so there was no real target to advance through a scheduled refresh cycle.

## Barcode/camera

The barcode workflow remains camera-first where the browser provides a secure camera context, with native BarcodeDetector preferred and the bundled local ZXing fallback available. Manual barcode entry remains the terminal fallback.

Browser CI covers the scanner interaction paths without physical hardware. A physical-phone camera check is useful UX acceptance, but it is not a backend gate for the redesign.

## Backlog boundary

The old Floppy-based metadata PR is closed and obsolete: BGC now owns direct optional BGG XML API2 enrichment.

Persistent Italian synopsis translation is intentionally deferred until after the UI redesign. The source BGG description is already persisted; adding another translation provider/cache/presentation surface immediately before the redesign would increase UI state rather than stabilize it.

## Redesign boundary

The UI redesign may reorganize navigation, hierarchy and presentation, but it must not weaken:

- local catalog/copy ownership;
- barcode-to-owned-copy mapping;
- document provenance and review policy;
- manual PDF upload;
- staged known-source -> Google rulebook search;
- exact server-owned citation/page provenance;
- fail-closed RAG validation;
- explicit provider settings and lack of silent provider fallback.
