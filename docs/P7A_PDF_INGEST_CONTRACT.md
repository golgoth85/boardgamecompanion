# P7A — PDF parsing and page model

P7A starts only from an already archived game_documents PDF. It does not fetch
documents, discover rulebooks, chunk text, create embeddings, retrieve passages or
generate answers.

## Invariants

- The archived file is copied to a temporary parser snapshot only after its byte
  size and SHA-256 are revalidated against game_documents.
- Parsing runs in a separate Python process with a wall-clock timeout and Linux
  CPU/address-space limits. The production parser is pinned to pypdf 6.19.0.
- Extraction is page-preserving and non-summarizing. P7A stores the text returned
  by the parser for each exact 1-based PDF page.
- A page with no extractable text is stored as empty; P7A does not OCR it.
- A page-level parser exception is stored as error with bounded diagnostics and
  empty text. It is never silently represented as successful text extraction.
- Page IDs are deterministic for document_id + page_number and remain stable
  across forced re-parses. The parse-run ID records which parser execution produced
  the current text.
- Document language, type, version, edition and official/community provenance remain
  owned by game_documents and are returned alongside ingest status/page results.
- Parser diagnostics are bounded JSON. A failed parse is auditable in
  document_parse_runs and never replaces previously persisted pages.
- Repeating ingestion with the same immutable document and pinned parser is
  idempotent unless force=true.

## Persistence

Schema v6 adds document_parse_runs and document_pages. P7B may build chunks only
from this persisted page model while retaining page and document provenance.
