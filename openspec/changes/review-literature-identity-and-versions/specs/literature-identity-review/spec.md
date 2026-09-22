## Purpose

Provide explicit, evidence-backed human decisions for Literature identity and version uncertainty while preserving canonical ownership and existing research data.

## ADDED Requirements

### Requirement: Identity decisions require current evidence and explicit intent
Confirmation and correction SHALL require a current canonical snapshot, paper-owned supporting evidence and a user rationale. They MUST reject stale context and identifier ownership conflicts atomically. Confirmation SHALL require a scholarly identifier and SHALL be labeled as human review rather than external scientific verification.

#### Scenario: Another paper owns a corrected DOI
- **WHEN** a correction requests a DOI assigned to another canonical paper
- **THEN** the correction fails and neither paper's identifiers or research relationships change

#### Scenario: Current identity is confirmed
- **WHEN** the user confirms consistent accepted identifiers with evidence and no unresolved applicable conflict
- **THEN** a durable confirmation references the snapshot/evidence and identifies the record as human-confirmed published, preprint or other identified literature

#### Scenario: Confirmed metadata later changes
- **WHEN** the canonical metadata no longer matches the confirmed snapshot
- **THEN** the prior decision remains historical and current identity requires review again

### Requirement: Identifier correction preserves canonical ownership
Explicit correction SHALL preserve canonical IDs and all research relationships, update accepted identifier ownership transactionally, and retain superseded values in decision evidence. It MUST NOT automatically merge records or resolve unrelated conflicts.

#### Scenario: An erroneous unowned identifier is corrected
- **WHEN** a current-snapshot correction replaces an erroneous identifier with an unowned valid identifier
- **THEN** the paper retains its ID, Notes, AI and assets, and the former/current claims remain auditable

### Requirement: Conflicts have durable reversible review decisions
Rejected identity ingestion SHALL persist evidence without partial canonical writes. The conflict queue SHALL retain original payloads and reasoned decisions to keep a valid current identity, quarantine unassociated evidence or reopen review. A decision MUST NOT falsely claim that a quarantined asset has been recovered.

#### Scenario: Weak import is rejected
- **WHEN** an import has only a weak match
- **THEN** canonical records remain unchanged and a replay-safe conflict record identifies the candidates

#### Scenario: Orphan source attachment is quarantined
- **WHEN** a user classifies a parent-unresolved attachment with a reason
- **THEN** the payload remains available and can be reopened without assigning a guessed canonical parent

#### Scenario: Similar no-DOI papers are distinct
- **WHEN** a user explicitly decides that a weak-only import candidate must remain separate
- **THEN** an exact retry can create an independent canonical record without a DOI, while strong identifier collisions remain forbidden

### Requirement: Version relationships do not merge papers
The system SHALL support explicit preprint-to-publication links with evidence, current snapshots and rationale. Links SHALL retain two distinct canonical IDs and MUST NOT transfer identifiers or research data. Retraction SHALL preserve original relationship evidence and decision history.

#### Scenario: Preprint and publication are linked
- **WHEN** the user links a preprint and a separately identified published paper
- **THEN** their relationship is visible while Notes, PDF associations and canonical identifiers remain independent

#### Scenario: A relationship is retracted
- **WHEN** the user retracts a current relationship with a reason
- **THEN** it becomes inactive and its original evidence and retraction decision remain inspectable
