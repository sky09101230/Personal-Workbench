# literature-metadata-evidence

## Purpose

Make Literature canonical metadata changes explicit, evidence-linked and reviewable while preserving source observations, existing identity and research relationships.

## Requirements

### Requirement: Existing bibliographic metadata is protected from source overwrites
New source observations SHALL preserve existing canonical bibliographic fields and propose differing non-empty values, including previously blank fields. Source priority and same-source replay MUST NOT silently overwrite accepted values. New records SHALL retain source evidence without claiming scientific verification.

#### Scenario: Higher-priority refresh disagrees
- **WHEN** a higher-priority source supplies a different title or year for an existing identity
- **THEN** the original canonical values remain and an evidence-linked proposal is available for review

#### Scenario: Preprint gains a publication DOI
- **WHEN** an observation matched by arXiv or stable reference supplies a new formal DOI
- **THEN** the DOI is a candidate until review and is not silently promoted or indexed as accepted

### Requirement: Proposals and accepted fields reference durable evidence
Proposals SHALL retain supporting evidence IDs and acceptance decisions SHALL retain before/after values and deciding evidence IDs. Equivalent source replay SHALL not duplicate or reopen the same proposal decision. Historical provenance without an exact decision pointer SHALL remain distinguishable rather than fabricated.

#### Scenario: Repeated rejected source suggestion
- **WHEN** an identical source candidate is observed again against the same canonical snapshot after rejection
- **THEN** its evidence remains traceable and the rejected proposal is not reopened

#### Scenario: Accepted correction
- **WHEN** a user accepts a valid current proposal
- **THEN** the changed fields and identifier index update atomically and the field choices reference the recorded user decision

### Requirement: Conflict and staleness are checked at decision time
Syntactically valid conflicting proposals SHALL be retained for inspection and rejection or correction. Acceptance MUST reject ownership conflicts and stale snapshots without changing canonical identity, metadata or proposal decision. Ordinary metadata review MUST NOT erase an unresolved identity conflict.

#### Scenario: Candidate identifier belongs to another paper
- **WHEN** a proposal contains another canonical paper's DOI
- **THEN** the proposal remains reviewable with a conflict explanation and cannot claim that DOI on acceptance

### Requirement: Completeness and review status are independent
The system SHALL expose metadata review state separately from completeness. Confirming current metadata SHALL require the current snapshot, no pending proposals and no unresolved canonical identity conflict; it SHALL record user evidence without changing bibliographic values. Reviewed metadata MUST NOT be presented as externally or scientifically verified.

#### Scenario: Complete imported metadata
- **WHEN** an imported record has title, authors and year but has not been reviewed
- **THEN** it is complete and unreviewed rather than verified

#### Scenario: Explicit current metadata confirmation
- **WHEN** a user confirms an unchanged current metadata snapshot with no pending proposal or identity conflict
- **THEN** its populated fields are marked reviewed with a durable user decision while paper ID and field values stay unchanged

### Requirement: Existing data survives additive workflow upgrade
The schema upgrade SHALL back up existing canonical databases, support dry-run and replay, and preserve historical bibliographic values, IDs, Notes, AI, assets, source and native relationships. Dry-run MUST NOT mutate the source database.

#### Scenario: Existing version-2 library
- **WHEN** the evidence workflow upgrades an existing canonical library
- **THEN** the evidence-link schema and migration report are added while all historical data values remain intact
