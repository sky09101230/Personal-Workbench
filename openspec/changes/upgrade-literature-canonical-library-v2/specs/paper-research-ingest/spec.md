## ADDED Requirements

### Requirement: Explicit canonical Library handoff
Radar SHALL retain its existing run, ingest and review behavior and offer explicit Save to Library for recommendations and verified alternatives. Radar SHALL be an ingestion origin, never an external-reference provider. Save SHALL preserve appearance history and recommendation evidence.

#### Scenario: Unreviewed daily run
- **WHEN** the daily Agent ingests a Radar result
- **THEN** no canonical Library paper is created automatically

#### Scenario: Save and refresh
- **WHEN** a user saves a recommendation and refreshes
- **THEN** the saved state persists, a repeated save is idempotent, and Radar review state is unchanged

#### Scenario: Multiple appearances
- **WHEN** a saved paper has appeared in multiple runs
- **THEN** its origin retains run identities, ranks, scores, reasons and summaries without duplicating the canonical paper
