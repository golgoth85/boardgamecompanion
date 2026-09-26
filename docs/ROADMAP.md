# BoardGameCompanion roadmap after P7 and P5 remediation

This roadmap is based on the repository state after P6B, not on historical chat state.

## Architectural boundary: BGG and Floppy

BoardGameCompanion remains the owner of board-game-specific workflows: physical
copies, local barcode mappings, documents, rulebook lifecycle, retrieval and RAG.
Floppy remains an optional collection synchronization integration, but is not a
dependency for BGG metadata or rulebook discovery.

BGC may use its own approved BGG XML API2 application token for exact-ID metadata
enrichment. The token is optional runtime configuration and is never committed.
BGC owns its cache, five-second rate gate, bounded retries and exact-identity
validation. CSV import and all local domain workflows remain usable without it.
Private BGG JSON APIs and authenticated scraping remain prohibited.

BGG version product codes must not be treated as UPC/EAN/ISBN identifiers. The
local invariant remains:

barcode -> OwnedCopy -> BoardGame

and must continue to work even when Floppy or BGG is offline.

## Ordered work

### P3B — camera-first barcode hardening

Close the current browser-compatibility gap first. Native BarcodeDetector is only
an optimization; a local ZXing fallback is required. Manual input remains fallback.
### M1 — direct optional BGG metadata enrichment

Use the official XML API2 from BoardGameCompanion for exact canonical IDs,
independently of Floppy.

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
BGG outage or an absent token must not make the local catalog unusable.

Edition, language, version and product-code enrichment are deferred until the
provider boundary exposes trustworthy data for them.

### P5 remediation — concrete provider discovery

Add isolated Repos Production, Asmodee Italia and RuleBook.org adapters; a
persistent bounded catalog scheduler; per-provider failure audit; IT/EN discovery;
and the existing resolver → P6A → P5B/P6B path. RuleBook.org remains community
trust and cannot be auto-promoted. A separate persistent worker automatically
runs the existing P7 ingest, chunk and embedding stages after archival.

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
