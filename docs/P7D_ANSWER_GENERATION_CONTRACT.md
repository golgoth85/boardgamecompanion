# P7D — answer generation and citations

P7D consumes P7C retrieval evidence and produces a game-scoped rules answer.
It does not add the query UI; that remains P7E.

## Generation boundary

Ollama is optional. Generation requires explicit BGC_OLLAMA_URL,
BGC_OLLAMA_EMBEDDING_MODEL and BGC_OLLAMA_GENERATION_MODEL configuration.
The generation model is resolved through /api/tags, and its digest is checked
before and after each answer. A tag that changes weights during a request is
therefore rejected.

Generation uses /api/chat with stream=false and a JSON-schema structured output.
The model never supplies document IDs, page numbers, URLs or trust metadata.
It may only return short answer claims plus server-issued evidence IDs.

Retrieved text is treated as untrusted quoted data. The system prompt explicitly
forbids following instructions found inside evidence. The generation model has no
tools or external capabilities in this phase.
## Grounding invariants

- Generation is skipped when P7C reports incomplete document embedding coverage.
- Generation is skipped when retrieval returns no evidence.
- Only full P7C chunks are passed to generation; chunk text is never truncated.
- An answer is a list of claims. Every claim must include at least one
  server-issued evidence ID plus a short verbatim support quote.
- Every support quote is checked as an exact substring of the cited P7C chunk.
- Unknown, malformed or uncited evidence IDs and invented support quotes are rejected.
- Model-supplied citation-number syntax is rejected; numeric citation markers are
  appended by BoardGameCompanion after validation.
- Citations are rebuilt from P7C provenance and contain document, page, source,
  language, version/edition and official/community state.
- Multiple chunks from the same document page collapse to one page citation.
- A model may return not_found when the selected evidence is insufficient.
- No prior model knowledge is accepted as an evidence source.

## Conflict behavior

P7D never combines evidence from version/edition cohorts excluded by P7C.
The selected cohort and every excluded conflicting cohort are returned explicitly.
The answer may use only evidence from P7C's selected cohort.
## API

POST /api/games/{bgg_id}/answer

Input mirrors the P7C retrieval filters with a smaller maximum top_k of 20.

Output status is either:

- answer: validated claims, server-rendered answer text and page citations;
- not_found: no fabricated answer, with a machine-readable reason such as
  index_incomplete, no_retrieved_evidence, or
  retrieved_evidence_insufficient.

P7E will consume this response directly for the interactive query experience.
