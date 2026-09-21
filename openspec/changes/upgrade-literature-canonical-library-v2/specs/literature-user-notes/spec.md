## ADDED Requirements

### Requirement: Canonical notes preserve legacy content
Migration SHALL associate existing My Notes with canonical paper identity while retaining note IDs, content, source and timestamps, including notes whose source item was removed.

#### Scenario: Read old notes after migration
- **WHEN** a user refreshes a canonical or legacy paper URL
- **THEN** all historical My Notes remain visible and distinct from source notes
