# BoardGameCompanion roadmap after P6B

This roadmap is based on the repository state after P6B, not on historical chat state.

## Architectural boundary: BGG and Floppy

BoardGameCompanion remains the owner of board-game-specific workflows: physical
copies, local barcode mappings, documents, rulebook lifecycle, retrieval and RAG.
Floppy remains the provider/catalog boundary for BGG metadata that it already exposes.

Current Floppy supports a BGG provider backed by the XML API2. It exposes generic
authenticated API routes for board-game search and detail. The provider currently
returns title, image, description, categories, rating/count, year, player range,
play time, minimum age, designers and publishers.

Floppy also owns BGG credential resolution, encrypted instance/user storage,
cache, outbound rate limiting, bounded retries and provider error handling.
Therefore BoardGameCompanion must not store a second BGG token at this stage.
The user-owned BGG token belongs in Floppy Settings > Metadata, or in Floppy's
BGG_API_TOKEN / BGG_API_TOKEN_FILE operator configuration. BoardGameCompanion
only needs its existing Floppy credential.

The current Floppy BGG provider does not request or expose BGG version data,
edition/language data, or version product codes. BGG XML API2 can return version
information when thing requests use versions=1, but that is not a reason to
duplicate the token in BoardGameCompanion. If edition-level enrichment becomes
necessary, prefer extending the Floppy provider/API boundary first.

BGG version product codes must not be treated as UPC/EAN/ISBN identifiers. The
local invariant remains:

barcode -> OwnedCopy -> BoardGame

and must continue to work even when Floppy or BGG is offline.

## Ordered work

### P3B — camera-first barcode hardening

Close the current browser-compatibility gap first. Native BarcodeDetector is only
an optimization; a local ZXing fallback is required. Manual input remains fallback.
### M1 — BGG metadata enrichment through Floppy

Add an explicit enrichment model/adapter in BoardGameCompanion that consumes
Floppy's BGG search/detail API without learning the BGG token.

Initial enrichment scope:
- cover image;
- description;
- player count;
- play time;
- rating and rating count;
- categories;
- designers;
- publisher;
- source/provenance and fetched/refreshed timestamps.

Refresh must be controlled and cached. CSV import remains independently usable.
Floppy/BGG outage must not make the local catalog unusable.

Edition, language, version and product-code enrichment are deferred until the
provider boundary exposes trustworthy data for them.

### P7A — PDF parsing and page model

Ingest archived PDFs only after archive safety. Preserve document identity, exact
page identity, faithful extracted text, language, version, edition, document type,
official/community provenance and parser diagnostics. No ingest-time summarization.
### P7B — chunking and index persistence

Persist chunks with game, document, page, language, version/edition, document type,
source/trust and deterministic content identity. No chunk may exist without provenance.

### P7C — embeddings and retrieval

Benchmark local embedding choices and vector storage before committing to Ollama
or Qdrant. Retrieval policy prefers current official documents in the requested
language, then official English, then explicitly marked community material.
Contradictory versions or editions are never silently mixed.

### P7D — answer generation and citations

Generate answers only from retrieved evidence, cite document and page, surface
official/community status and version conflicts, and return not-found rather than
fabricating an answer.

### P7E — query UI

Add the game-scoped query experience, evidence/citation navigation, document
version/language visibility, and explicit conflict/not-found states.

Every phase remains independently reviewable and follows the branch -> tests ->
PR -> exact-HEAD CI -> independent review -> merge gate.
