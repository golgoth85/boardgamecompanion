# P7C vector backend benchmark — 2026-09-24

Environment: NAS local Python, SQLite, float32 normalized vectors, brute-force
cosine/dot scoring. The benchmark intentionally includes SQLite BLOB fetch time.

- 384 dimensions / 500 vectors: 8.5 ms
- 384 dimensions / 2,000 vectors: 34.0 ms
- 384 dimensions / 5,000 vectors: 85.1 ms
- 768 dimensions / 500 vectors: 16.9 ms
- 768 dimensions / 2,000 vectors: 82.7 ms
- 768 dimensions / 5,000 vectors: 153.7 ms

Decision: retain SQLite for P7C because retrieval is game-scoped. The existing
Qdrant container belongs to another project and is not reused. No active Ollama
endpoint was visible from the NAS execution context, so no embedding-model latency
benchmark is claimed. Model choice remains explicit configuration rather than a
hard-coded default.
