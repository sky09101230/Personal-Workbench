## ADDED Requirements

### Requirement: Browser-local acquisition binds to an existing source
Literature SHALL accept paired-helper transfers through a short-lived intent bound to an existing paper, source asset, descriptor revision and role. It SHALL independently validate PDF bytes, size and checksums and atomically preserve source mappings and provenance. Client observations SHALL be labeled client-reported evidence, not independent proof of original byte identity. Available expected source checksums MUST agree. Replay SHALL reuse verified ownership without duplicate associations.

#### Scenario: Local recovery succeeds
- **WHEN** a stable local attachment and its bytes satisfy the bound intent and verification
- **THEN** the existing paper receives an owned asset with the same role and source mapping while metadata, notes and organization remain unchanged

#### Scenario: Stale or mismatched transfer
- **WHEN** an expired intent, changed descriptor, incorrect parent or checksum mismatch is submitted
- **THEN** no association is committed and the outcome identifies the failure

#### Scenario: Transfer interrupted or replayed
- **WHEN** a transfer is interrupted or a completed transfer is retried
- **THEN** no partial association is exposed and replay creates no duplicate owned association
