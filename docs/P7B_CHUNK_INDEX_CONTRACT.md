# P7B — chunking and index persistence

P7B consumes only the current successful P7A page model. It does not parse PDFs,
create embeddings, query a vector store, retrieve passages or generate answers.

## Invariants

- A chunk never crosses a PDF page boundary.
- Chunk text is an exact substring of the persisted P7A page text. Character offsets
  are half-open from start_char to end_char and the stored character count must equal
  the offset span. Application validation also verifies the exact substring length.
- Every chunk persists document, parse-run and page provenance, including document
  SHA-256, page-text SHA-256, language, document type, version/edition, source
  metadata and the official flag.
- Composite foreign keys prevent a chunk from being attached to a page, parse run,
  document or game that do not belong together.
- P7A page replacement cascades deletion of dependent chunks. A stale index cannot
  survive a successful re-parse.
- Chunk IDs and chunk keys are deterministic for the same document bytes, page
  identity/text, character span, exact chunk text and chunker configuration.
- Rebuilding the same current page set with the same configuration is idempotent
  unless force=true. A forced rebuild preserves deterministic chunk IDs.
- Empty/error pages produce no chunks. They remain represented by P7A and are still
  included in the source-page-set digest for index freshness.
- The list API omits full chunk text; the exact chunk endpoint returns it.

## Chunker

The initial chunker is page-char-window version 1. It uses bounded character
windows with deterministic preferred breakpoints and overlap. Configuration is
persisted with every build and chunk so later benchmarking can change policy without
silently mixing incompatible index generations.

## Persistence

Schema v7 adds document_chunk_runs and document_chunks. P7C must consume these
persisted chunks and preserve their provenance; it must not reconstruct untraceable
text fragments.
