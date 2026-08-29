# Paper Research Ingest Specification

## Purpose

Define strict external Research result ingestion, transactional News-owned provenance, Paper identity deduplication, latest-recommendation querying, and AI Research presentation in the existing Papers area.

## Requirements

### Requirement: Research ingest accepts a strict versioned contract
The system SHALL expose `POST /api/news/papers/research/ingest` and accept only supported schema-versioned payloads containing nonblank task and run keys, generated time, explicit agent provenance, a query plan, and a non-empty list of papers with required title, AI summary, recommendation reason, and at least one valid URL or supported identifier. Optional scores MUST be between zero and one, extra fields MUST be rejected, and clients MUST NOT control internal ids or persistence timestamps.

#### Scenario: Valid research payload
- **WHEN** a client submits schema version `1` with valid run provenance and papers
- **THEN** the endpoint validates and passes explicit domain values to the News service

#### Scenario: Invalid contract input
- **WHEN** a payload omits a required field, contains no papers, supplies an invalid score or DOI, uses an unsupported schema version, or includes an unrecognized field
- **THEN** the endpoint returns a validation error and writes no Research data

### Requirement: Objective papers and run-specific recommendations are persisted separately
The system SHALL store objective Paper metadata independently from Research Runs and Recommendations, and each Recommendation SHALL link exactly one Run to one Paper while retaining AI summary, recommendation reason, optional scores, topics, library relationship, and bounded source provenance.

#### Scenario: Five-paper run is ingested
- **WHEN** a valid run containing five distinct papers is submitted
- **THEN** SQLite contains one Research Run, five Papers, and five Recommendations without placing AI judgment fields on the Paper rows

#### Scenario: Two runs recommend the same paper
- **WHEN** two payloads with different run keys resolve to the same normalized Paper
- **THEN** SQLite contains one Paper, two Research Runs, and two historical Recommendations

### Requirement: Paper identifiers are normalized and deduplicated
The system SHALL resolve Paper identity in the order normalized DOI, arXiv id, OpenAlex id, then canonical title and publication year. DOI normalization MUST accept canonical DOI strings and recognized `doi:`, `doi.org`, and `dx.doi.org` forms, lowercase the result, and reject malformed DOI values.

#### Scenario: Equivalent DOI forms are ingested
- **WHEN** payloads identify a paper as `https://doi.org/10.x/y`, `doi:10.x/y`, and `10.X/Y`
- **THEN** all forms normalize to `10.x/y` and resolve to one Paper

#### Scenario: Paper has no DOI
- **WHEN** a paper supplies a valid arXiv id, OpenAlex id, or URL and title/year fallback metadata
- **THEN** the paper can be persisted and deduplicated without inventing a DOI

### Requirement: Research ingest is atomic and idempotent
The system SHALL perform Run, Paper, and Recommendation writes in one SQLite transaction, enforce uniqueness for `(task_key, run_key)` and `(run_id, paper_id)`, and treat replay of the same run identity as an upsert rather than a new event.

#### Scenario: Identical payload is posted twice
- **WHEN** the same five-paper payload is submitted twice with the same task and run keys
- **THEN** both requests succeed and final counts remain one Run, five Papers, and five Recommendations

#### Scenario: A critical write fails
- **WHEN** any Paper or Recommendation write fails during ingest
- **THEN** the transaction rolls back so no partial Run or partial paper set remains

### Requirement: Research results are queryable as a latest-recommendation Feed projection
The system SHALL expose `GET /api/news/papers/research` with bounded pagination and project the latest Recommendation per Paper into the existing FeedItem display contract while including research run provenance, AI summary, recommendation reason, optional scores, source, and topics. Older Recommendations MUST remain stored even when they are not the default projection.

#### Scenario: Same paper appears in multiple runs
- **WHEN** the research feed is queried after two runs recommended the same Paper
- **THEN** the response contains one item for that Paper using the newest Recommendation and identifies its Research Run

#### Scenario: API is recreated over the same SQLite file
- **WHEN** the News service and repository are reconstructed after a successful ingest
- **THEN** the research feed returns the previously ingested data

### Requirement: Existing Papers UI distinguishes AI Research results
The system SHALL show Research recommendations in the existing `/news` Papers area without changing GitHub Trending behavior. Each Research card SHALL identify `AI Research` and display available Paper metadata, AI Summary, recommendation reason, relevance score, and topics; novelty score and run/source provenance SHALL remain available in the response.

#### Scenario: User opens the Papers tab
- **WHEN** Research results and OpenAlex feed items are available with no Topic filter selected
- **THEN** the Papers area displays both sources and visually distinguishes Research recommendations from ordinary OpenAlex items

#### Scenario: User opens the GitHub tab
- **WHEN** the active News type is GitHub
- **THEN** existing period controls, refresh behavior, and repository cards remain unchanged

### Requirement: A real five-paper fixture proves the end-to-end data path
The system SHALL include a reusable acceptance payload containing five real papers relevant to diffractive or metasurface optical computing, with real DOI or canonical URLs and summaries/reasons consistent with the cited paper metadata.

#### Scenario: Acceptance fixture is replayed
- **WHEN** the fixture is posted once and then posted again unchanged against a temporary on-disk Workbench SQLite database
- **THEN** POST succeeds twice, GET exposes five Research cards with summaries and reasons, counts remain stable, and the data remains readable after repository recreation
