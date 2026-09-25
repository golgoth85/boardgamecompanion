# P7C — embeddings and retrieval

P7C consumes only current P7B chunks. It does not generate natural-language
answers; answer synthesis and citation formatting remain P7D.

## Storage decision

A NAS-local synthetic benchmark on 2026-09-24 measured brute-force SQLite scans
including vector fetch and cosine scoring:

| Dimensions | Candidates | Total |
| ---: | ---: | ---: |
| 384 | 500 | 8.5 ms |
| 384 | 2,000 | 34.0 ms |
| 384 | 5,000 | 85.1 ms |
| 768 | 500 | 16.9 ms |
| 768 | 2,000 | 82.7 ms |
| 768 | 5,000 | 153.7 ms |

Retrieval is scoped to one board game, so these cardinalities are already above
the expected chunk count for normal rulebook sets. P7C therefore stores normalized
float32 vectors in SQLite and does not add Qdrant as a runtime dependency. A
dedicated vector service can be reconsidered only if measured per-game candidate
counts or latency materially exceed this envelope.

The NAS currently exposes no active Ollama endpoint to this runtime. The embedding
model is therefore deliberately not defaulted. The operator must configure both
BGC_OLLAMA_URL and BGC_OLLAMA_EMBEDDING_MODEL. Ollama model identity is pinned at
runtime using the local-model digest returned by its model-list endpoint.

## Invariants

- Only chunks from the current P7B chunker configuration are eligible.
- The embedding fingerprint includes provider, resolved model, model digest,
  requested dimensions, endpoint and non-truncating input policy.
- Ollama requests use the batch embed endpoint with truncation disabled. Oversized
  input must fail rather than silently changing evidence.
- Vectors are normalized, finite float32 little-endian values. Stored byte length,
  SHA-256 and normalization are checked on retrieval.
- Embeddings are foreign-keyed to both the exact P7B chunk and its chunk run.
  P7A/P7B invalidation therefore cascades to vectors.
- The P7B chunk set is revalidated under BEGIN IMMEDIATE after embedding generation.
  A concurrent chunk change aborts persistence.
- A second idempotence check under the write lock prevents duplicate non-force
  embedding runs.
- Retrieval never mixes embedding model digests or embedding configurations.

## Retrieval policy

Candidates are first filtered to the requested game and current chunker/model
fingerprints. Trust/language priority is then applied:

1. official material in the requested language;
2. official English;
3. other official material;
4. user-supplied material;
5. explicitly marked community material.

Unclassified non-official sources are excluded. The first tier with candidates
above the requested similarity threshold is selected. Within that tier, chunks
from conflicting version/edition cohorts are not mixed: one cohort is selected by
best semantic score, with publication date as a deterministic tie-breaker. The
response exposes the selected tier/cohort and excluded conflicting cohorts.

P7D must consume these evidence objects directly so document/page provenance is
not lost before answer generation.
