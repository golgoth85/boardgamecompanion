# Phase 7 independent-review remediation

This document records the bounded remediation performed after the independent
Phase 7 review. It does not replace the P7A-P7E contracts and does not authorize
Phase 8.

The remediation branch starts from the merged Phase 7 baseline
`c777bbc4f8649f3d5410935b6c2b791223330d4d`.

## H-1 — archive bytes remain bound to PDF provenance

Archived PDF bytes are no longer trusted merely because the database still
contains the original SHA-256 and size.

`DocumentStore.create_verified_snapshot()` opens the archived file safely,
copies it to a temporary snapshot while hashing it, and requires its actual
size and SHA-256 to match the current `game_documents` provenance.

P7A performs this verification twice:
1. for the parser snapshot;
2. again under the final `BEGIN IMMEDIATE` transaction immediately before a
   successful parse run/pages are committed.

The document download endpoint also serves a verified snapshot and deletes it
after the response. If the archived file was externally replaced, the endpoint
returns a conflict instead of serving bytes under stale provenance.

## M-1 — non-force P7A concurrency

A non-force ingest performs its original optimistic current-run check before
parsing, then repeats the same complete-run check under the final
`BEGIN IMMEDIATE` transaction.

Only the request that wins the serialized commit creates the succeeded run.
Another request that parsed the same unchanged document while waiting for the
lock reuses that run with `created=false`.

Current-run selection only considers succeeded runs with their complete page
set. `finished_at` is assigned inside the serialized commit section.

## M-2 — page/chunk substring invariant

A persisted chunk is valid only if all of these still hold:
- its page exists;
- document ID, parse run, page number and page SHA match the chunk provenance;
- the current page text still hashes to the declared page SHA;
- `start_char:end_char` is in bounds;
- `chunk.text == page.text[start_char:end_char]`.

The invariant is checked by the P7B read path, P7C embedding-source validation
and P7C retrieval candidate validation. Matching chunk hashes and deterministic
IDs alone are not sufficient.

## H-2 — coverage starts from eligible documents

Retrieval coverage no longer derives its denominator from existing chunks.
It starts from trusted, filter-eligible `game_documents` for the requested
game.

For every eligible document:
- no current P7B source means the document is missing;
- current P7B but no embedding run matching provider/model digest/config/input
  set means the document is missing;
- only a fully current P7B/P7C state counts as embedded.

The trusted coverage scope and candidate scope are aligned:
official documents, user-supplied manual uploads, and explicitly community
sources. Unclassified non-official sources remain excluded by retrieval policy.

Therefore adding a new eligible document, reparsing a document, rebuilding its
chunks, or changing trust/language/version/edition cannot make that document
silently disappear from the coverage denominator.

## H-3 — request-time currentness

P7C creates a currentness snapshot containing:
- game identity;
- embedding provider/model/digest/config;
- query document filters;
- a digest of per-document P7B/P7C readiness;
- a digest of the complete candidate set, including embedding run, chunk/run,
  document metadata digest, parse/page identity, chunk text digest, vector
  digest/dimensions and publication timestamp.

After the external query-embedding call P7C recomputes coverage and candidates.
Any change aborts the request with an `EmbeddingConflict`.

Before returning a retrieval response, P7C validates the response snapshot
again against current storage.

P7D validates the same P7C currentness snapshot after the external generation
call and again at the answer response boundary. Claims/citations are not
returned if evidence, document metadata, page/chunk identity, embeddings or
the embedding model changed while generation was in flight.

## Required adversarial regression evidence

The remediation test suite must independently cover:
- replacing archive bytes after the parser snapshot but before P7A commit;
- attempting to download archive bytes that no longer match provenance;
- simultaneous non-force P7A ingests;
- coordinated chunk text/hash/key/ID tampering that no longer matches its page;
- a new eligible document with no current chunks;
- an invalidated official document while lower-trust evidence remains ready;
- source invalidation during query embedding;
- evidence invalidation during answer generation.

A successful implementation CI is not the Phase 7 re-review. The remediation
PR must remain unmerged until a separate fresh independent reviewer verifies
these closures and the cross-phase trust boundary.
