## Purpose

Make Workbench the durable owner of literature identity, metadata, organization and files across external sources and explicitly reviewed discoveries.

## ADDED Requirements

### Requirement: Workbench owns canonical papers
The Library SHALL contain only explicitly imported or saved papers with opaque Workbench IDs, independent of external provider IDs and availability.

#### Scenario: Zotero removes an item
- **WHEN** full or incremental source sync removes a previously imported item
- **THEN** its reference is detached while the paper, native state and research data remain

#### Scenario: User deletes from Library
- **WHEN** the user removes a Library paper
- **THEN** it disappears from Library queries and later source sync does not restore it

### Requirement: Identity resolution is deterministic and conflict safe
The system SHALL normalize DOI/arXiv/stable IDs, use conservative corroborated title/year fallback, resolve repeats idempotently and expose conflicting identity evidence without silent merging.

#### Scenario: Radar matches a Zotero paper
- **WHEN** a reviewed candidate and an existing source paper share a compatible normalized DOI
- **THEN** one canonical paper retains both source reference and Radar origin

#### Scenario: Conflicting formal identifiers
- **WHEN** identical titles carry conflicting formal DOIs
- **THEN** ingest reports an explicit conflict and does not merge the records

#### Scenario: Repeated or concurrent import
- **WHEN** the same stable import identity is submitted more than once
- **THEN** one canonical paper and one corresponding origin are retained

### Requirement: Metadata retains provenance
Canonical values SHALL retain source evidence, typed date evidence and explainable conflicting candidates, and weaker evidence MUST NOT overwrite stronger evidence.

#### Scenario: Distinct publication dates
- **WHEN** preprint and online-publication dates differ
- **THEN** both remain recorded with their semantic types

#### Scenario: Weak metadata update
- **WHEN** lower-confidence metadata disagrees with an existing canonical value
- **THEN** the canonical value remains and the alternative evidence is inspectable

### Requirement: Paper and assets are independent
A paper SHALL support zero or multiple independently identified files, roles and storage sources, including manually uploaded PDFs and Zotero attachments.

#### Scenario: Manual PDF without full metadata
- **WHEN** a valid PDF is uploaded without known scholarly identifiers
- **THEN** an incomplete paper and local asset are created and the Reader can stream and download it

#### Scenario: Multiple assets
- **WHEN** a paper has primary and supplementary PDFs
- **THEN** the primary is selected by default and individual assets can be opened with byte-range support

### Requirement: Native Library organization
The UI SHALL provide Library, Radar and Import, with paper search, tags, year, reading state, native collections and concise source/file indicators independent of Zotero configuration.

#### Scenario: Source collection changes
- **WHEN** a source collection is renamed or removed after import
- **THEN** its external metadata changes without deleting the imported native collection or user membership

#### Scenario: No Zotero configuration
- **WHEN** a user opens Library without Zotero credentials
- **THEN** saved papers and PDF import remain available

### Requirement: Existing data migrates recoverably
Migration SHALL back up populated databases, be atomic and repeatable, preserve legacy data and aliases, and report counts, conflicts and unresolved records.

#### Scenario: Existing database
- **WHEN** a legacy database is migrated
- **THEN** papers, references, collections, notes, attachments and native AI content remain accessible through canonical or legacy IDs

#### Scenario: Failure and retry
- **WHEN** migration fails mid-transaction
- **THEN** it rolls back and a later retry can safely complete using the original data
