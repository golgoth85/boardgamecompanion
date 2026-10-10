# BoardGameCompanion — current roadmap

This document reflects the live application and repository audit completed on
2026-10-10. Older phase documents remain useful as architectural history, but
they must not be read as unfinished product milestones.

## Current product state

BoardGameCompanion is a standalone, self-hosted companion for a physical board-game
collection. The major product areas below are implemented on `main` and were
present in the live application during the audit:

- BGG collection synchronization, metadata enrichment, catalog search/filtering,
  rankings and Explore views;
- personal ratings, played/completed state, lists, wishlist, global search and
  notifications;
- barcode/copy workflow;
- game-centric detail pages;
- rulebook discovery, review, guarded acquisition, archival, scheduled updates,
  PDF ingest, chunking, embeddings, retrieval and grounded Q&A;
- YouTube tutorial discovery and persisted video metadata;
- personalized Suggestions for games not already owned;
- owned-catalog AI recommendations ("Consigliami un gioco");
- Gamefound/Kickstarter crowdfunding discovery;
- relevant-expansion discovery and notifications;
- LM Studio/Gemini provider configuration, diagnostics and Wake-on-LAN.

The full information-architecture/UI redesign is no longer a future phase: the
current UI already incorporates the redesign and subsequent simplification work.

## Rulebooks — completed core work

The 2026-10-10 live audit found 154 owned catalog titles and no uncovered title:

- 120 have an official Italian or English rulebook PDF;
- 10 have a usable fallback PDF while background discovery continues looking for
  a preferred official IT/EN source;
- 24 are curated cases where a normal standalone PDF is not expected or where
  rules are carried by another official artifact (components/cards, physical
  booklet, shared/external exact manual, etc.);
- `uncovered_total = 0`.

Periodic discovery now stops for games already resolved by an official IT/EN PDF
or a curated no-standalone-PDF classification, while fallback-only titles remain
eligible for improvement. Manual forced discovery remains available.

RAG was verified live end to end: LM Studio embeddings + Gemini generation returned
a grounded Italian answer from an official Italian rulebook with a page-level
citation and no version conflict.

Rulebook work is therefore maintenance rather than a product phase. Remaining
activity is opportunistic: replace the 10 fallback documents with preferred
official IT/EN sources when exact identity can be verified.

## Expansions — major-only policy

The game-detail expansion box intentionally does not mirror every BGG expansion
link. It first rejects obvious micro-content (promos, packs, accessories, minis,
replacement/media items, etc.) and then selects the materially relevant cohort
using BGG ownership relative to the most widely owned expansion for that base
game, with a bounded result set.

Live verification on Arena: The Contest reduced the linked expansion set to six
material expansions and filtered fifteen marginal entries.

## Residual roadmap

### P1 — Recommendation quality

#### Suggestions candidate universe

The Suggestions module is implemented, grounded and live, but its current discovery
pool is BGG Hot with a default candidate limit of 50. Expand the bounded candidate
universe beyond the current Hot list so "Per te" and "Più diversi" can discover
high-quality games outside short-term popularity.

Target properties:

- bounded/cached pool rather than full-database ingestion;
- deterministic exclusion of owned titles and expansions where inappropriate;
- diversity across mechanics, categories, weight, duration and age;
- stable scoring before AI editorial generation;
- rotation/pagination so refresh does not simply recycle the same small cohort.

#### Owned-catalog assistant constraints

"Consigliami un gioco" correctly restricts IDs to owned catalog entries, but the
AI currently interprets hard constraints itself. The live audit produced a
cooperative-game request that included Sagrada despite its metadata not declaring
the Cooperative Game mechanic.

Add deterministic constraint extraction/filtering or a strict post-validator for
hard requirements such as:

- cooperative vs competitive;
- player count;
- maximum duration;
- age;
- complexity/weight;
- requested/excluded mechanics or categories.

The model should explain/rank already valid candidates, not redefine their factual
properties.

### P1 — Tutorial coverage

The tutorial-video feature and YouTube integration are implemented and configured,
but persisted coverage is sparse: the audit found videos already stored for only
6 of 154 owned games.

Add bounded catalog-wide/background discovery with:

- IT first, then EN;
- official channels preferred where available;
- existing relevance/review/unboxing/playthrough filters retained;
- rate-limit-aware batching and retry;
- no requirement for the user to open each game page manually to populate videos.

### P1 — Crowdfunding relevance

Gamefound and Kickstarter/Apify are live, but the audit found a Kickstarter
Tabletop false positive that was not a board game. Add a board-game relevance
filter before ranking/notification so category noise cannot enter the normal
feed.

### P2 — CI coverage

Universal Local CI is the ordinary application gate, but the current BGC
`pytest-v1` profile runs Python tests with `tests/e2e` excluded. It also does not
make real Node/JavaScript syntax validation a required BGC gate.

Extend the trusted Local CI profile to include:

- JavaScript syntax validation;
- Playwright desktop/mobile E2E;
- the existing Python suite;
- the same exact-source-SHA and cleanup attestation guarantees.

Do not restore routine GitHub-hosted application CI.

### P2 — Container publishing

Trusted NAS image build and smoke tests work, and deployment can use the immutable
local image. GHCR push currently fails because the token used at the release
boundary lacks the required package-write scope.

Fix the GHCR credential/scope so immutable images can also be published normally.
This is an infrastructure issue, not an application blocker.

### P2 — Wake-on-LAN acceptance

The BGC endpoint successfully emits the magic packet and LM Studio is reachable
after the request. Complete one physical acceptance test with the gaming PC
actually asleep/off:

`sleep/off -> BGC wake -> PC online -> LM Studio ready -> AI operation succeeds`.

### P3 — Maintenance and documentation

- keep this roadmap and README aligned with the current UI terminology and runtime;
- periodically review the 10 fallback-only rulebooks for preferred official IT/EN
  replacements;
- keep notification volume/retention under review as background producers grow;
- continue removing obsolete historical branches/PRs rather than treating them as
  active roadmap items.

## Architectural invariants

- BGC remains standalone for core board-game workflows.
- BGG `objectid` is the canonical external game identity.
- BGG version product codes are not UPC/EAN/ISBN identifiers.
- The physical-copy invariant remains:

  `barcode -> OwnedCopy -> BoardGame`

- Rulebook auto-acquisition remains fail-closed: exact identity, trusted source and
  policy approval are required.
- Community or lower-confidence documents never silently replace authoritative
  sources.
- RAG answers remain grounded in archived evidence with page citations and explicit
  conflict/not-found behavior.
- External provider failures must degrade gracefully without making the local
  catalog unusable.

Changes continue to follow branch -> tests -> PR -> exact-HEAD Local CI -> merge.
