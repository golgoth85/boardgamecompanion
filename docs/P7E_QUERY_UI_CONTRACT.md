# P7E — game-scoped query UI

P7E is the final implementation unit of Phase 7. It adds the browser experience
for the already-approved P7A-P7D backend contracts. It does not alter retrieval,
generation, trust ranking or citation semantics.

## Game-scoped experience

The query interface lives inside the existing game-detail page. It does not create
a second catalog or a global cross-game search surface.

The panel exposes:
- a free-text rules question;
- optional language, document-type, version and edition filters;
- current RAG readiness for archived documents;
- an explicit action to prepare the document index;
- grounded answer claims and support excerpts;
- server-owned citations with document and page navigation;
- explicit not-found and version-conflict states.
## Index preparation

The UI may orchestrate existing idempotent endpoints only:

1. POST /api/documents/{id}/ingest
2. POST /api/documents/{id}/chunks/build
3. POST /api/documents/{id}/embeddings/build

No P7E backend indexing shortcut is introduced. Failures remain visible and stop
the per-document sequence. Missing Ollama configuration is shown as configuration
state rather than hidden or retried indefinitely.

Readiness is determined from the current P7C embedding status for each archived
document. Adding a new PDF re-renders the game detail and therefore recomputes the
visible readiness state.

## Answer rendering

P7E renders only the structured P7D response. It does not parse or trust free-form
citation syntax from model text.

All model-derived answer text and verbatim support excerpts are HTML-escaped.
Document/source/version metadata is escaped as well.
Numeric citation buttons navigate to server-created citation cards. Citation
cards link to the archived PDF with a page fragment and may also scroll to the
corresponding document card in the current game detail.

Citation cards show:
- page number;
- document language;
- official/community/user-supplied trust state;
- document type;
- version and edition;
- source/provider identity.

Conflicting excluded version/edition cohorts are displayed separately and are not
presented as evidence used by the answer.

## Failure states

The UI distinguishes at least:
- no archived documents;
- incomplete index;
- missing RAG/Ollama configuration;
- no retrieved evidence;
- retrieved evidence insufficient for a supported answer;
- transport/backend failure.

A not-found response is not rendered as a generated answer.

## Browser validation

P7E adds Chromium E2E coverage for:
- grounded claims, citations and version conflict visibility;
- XSS-safe rendering of answer text;
- citation-to-page and citation-to-document navigation;
- incomplete-index to P7A/P7B/P7C preparation workflow;
- responsive mobile layout without horizontal overflow.

The E2E fixture may use a configured/shared Chromium executable when available,
while CI remains compatible with Playwright-managed Chromium.
