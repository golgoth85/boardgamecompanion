# Pre-UI-redesign readiness

This document freezes the backend and workflow contracts that the next UI redesign
should treat as stable. It is intentionally about behavior and information
architecture boundaries, not visual layout.

## Core workflow status

The following capabilities are considered implemented and must remain available
through the redesign:

- local catalog and physical-copy management;
- camera-first barcode lookup/import with manual fallback;
- optional direct BGG XML API2 metadata enrichment and cached cover/description;
- manual PDF upload;
- known-source rulebook discovery with trust/review policy;
- scheduled guarded rulebook updates;
- page-preserving PDF ingest, deterministic chunking and embedding currentness;
- game-scoped RAG with server-owned provenance and exact page citations;
- Google-assisted manual rulebook search as a human-reviewed fallback.

The Gemini rate-limit acceptance check and Docker restart-policy cleanup are
explicitly outside this readiness gate.

## Rulebook search interaction contract

A game detail page exposes exactly one primary rulebook-search action.

1. First click runs the existing known-source discovery pipeline, preferring
   Italian then English and preserving the current trust/review policy.
2. If that completed run finds candidates, the same control remains a
   known-source refresh action.
3. If a completed run returns zero candidates, the same control switches to
   **Cerca PDF su Google** on the next click, including when one or more known
   providers reported a failure. Provider failures remain visible in status.
4. The Google click opens the already-hardened literal-title search in a new
   tab. It never imports, downloads, trusts or approves a document.
5. A manually downloaded PDF still enters through **+ Aggiungi PDF** and the
   normal archive/index/provenance path.

The zero-candidate fallback state is derived from persisted discovery state, so
a reload does not expose Google before the known-source attempt has completed.

## Backend trust boundaries the redesign must not weaken

- The browser never assigns document trust.
- Provider candidates continue through the existing resolver/review policy.
- RAG evidence identity, document/page metadata and citation provenance remain
  server-owned.
- Model-provided quotes are accepted only under the exact/unique whitespace-only
  canonicalization policy and are rendered as exact source substrings.
- Provider/model currentness checks remain mandatory.
- No implicit provider fallback is introduced.
- Barcode mappings remain local `barcode -> OwnedCopy -> BoardGame`.
- BGG metadata is cacheable enrichment, not a replacement for local catalog
  identity or physical-copy data.

## Live acceptance snapshot — 2026-10-02

Production catalog inventory contains 144 games. A real-collection survey included
base/expansion pairs such as 7 Wonders Duel / Pantheon, Black Rose Wars / Crono,
The 7th Continent / What Goes Up, Must Come Down, and Tiny Epic Dungeons / Stories.
Only 7 Wonders Duel had an archived official Italian rulebook at survey time.

The known-source acceptance sample exercised four base games and four expansions.
Two repeated live runs demonstrated that provider coverage is unstable rather than
universally absent: one run found exact official Italian candidates for Last Aurora
and Last Aurora: Frozen Steel (2 of 6 cases that require an official Italian source),
while a later retry found 0 of 6. The remaining cases were dominated by upstream
HTTP/browser-fallback failures across Repos/Asmodee/Pendragon-style sources. A separate
real-collection inspection of 7 Wonders Duel: Pantheon failed in the Repos browser
fallback before an official Italian candidate could be established.

This is an accepted product constraint, not a reason to add more publisher-specific
UI or game-specific scraping. It is the concrete reason the stable game-page contract
uses known-source discovery first and then exposes the human-reviewed Google/manual
path after a completed zero-candidate search.

The existing official Italian 7 Wonders Duel document has separately passed live
end-to-end RAG acceptance through parsing, chunking, Gemini embeddings, retrieval,
Gemini 3.8 Flash generation, strict JSON/provenance validation and exact page citation.
The accepted live answer identified the game as two-player and verified its support
quote against page 2 of the archived PDF.

The production rulebook-update endpoint returns HTTP 200; its persistent worker is
enabled with a 60-second poll and batch size 5. There were zero approved update targets
at this snapshot, so no synthetic target was created merely to exercise the scheduler.

The bundled local ZXing browser asset is served by production with HTTP 200. Chromium
CI exercises camera/scanner control paths without physical camera hardware; a real-phone
camera check remains UX acceptance rather than a backend redesign gate.

The legacy Floppy metadata PR is closed as obsolete. Direct BGG XML API2 enrichment is
the current boundary. Persistent Italian synopsis translation is intentionally deferred
until after the information-architecture redesign.

## Acceptance before visual redesign

The pre-redesign cleanup uses three complementary acceptance layers:

- exact-head Python and Chromium CI for the consolidated interaction changes;
- live known-source discovery against a stratified four-base/four-expansion
  sample through NAS Control;
- live real-collection checks for at least one base game and one expansion across
  archive/index/RAG paths, reusing existing bounded NAS Control operations.

The visual redesign may radically reorganize navigation and presentation after
these gates, but should avoid changing the stable API/domain contracts in the
same change set.
