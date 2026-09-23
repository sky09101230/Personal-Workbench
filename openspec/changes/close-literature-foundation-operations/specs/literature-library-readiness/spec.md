## Purpose

Present truthful Literature ownership, acquisition and review readiness so users can distinguish independently usable files from unverified references and recoverable exceptions.

## ADDED Requirements

### Requirement: Explicit selected import attempts independent file ownership
Successful selective Zotero import SHALL attempt eligible PDFs through the shared acquisition workflow and return metadata and per-file outcomes separately. File failures MUST NOT hide a successfully imported canonical paper or claim missing bytes are owned.

#### Scenario: One attachment succeeds and another is unavailable
- **WHEN** an explicitly selected source paper has one retrievable PDF and one unavailable supplementary PDF
- **THEN** canonical import succeeds, the valid file is owned, and the supplementary failure remains visible and retryable

### Requirement: Library availability distinguishes ownership from references
The Library SHALL distinguish saved primary PDFs, saved other PDFs, source-only references, recovery-needed sources and absence of PDF descriptors. It MUST NOT present a remote descriptor as proof of an independently readable file. Current checksum verification SHALL remain distinguishable from stored ownership.

#### Scenario: Source-only paper
- **WHEN** a paper has remote descriptors but no owned PDF
- **THEN** its list/detail view identifies it as source-only or recovery-needed rather than an owned PDF

### Requirement: Acquisition state is durable scoped and retryable
Acquisition failures SHALL be recorded against the exact source descriptor, separately from scholarly conflicts. Success SHALL clear the current failure atomically with association. Stale failures MUST NOT describe changed sources. Users SHALL be able to retry a selected source attachment without moving canonical ownership.

#### Scenario: Restored source file
- **WHEN** a previously unavailable file is restored and the user retries that source
- **THEN** verified acquisition updates ownership/state and preserves metadata, Notes and all unrelated associations

### Requirement: Review audit respects decisions without deleting history
Read-only identity audit SHALL distinguish open conflicts, quarantined evidence and reviewed records while retaining every historical conflict. It MUST NOT count a resolved claim as a new unresolved identity merely because the historical row remains.

#### Scenario: Rejected claim is reviewed
- **WHEN** a consistent canonical identity is kept through a reasoned conflict decision
- **THEN** audit retains the event as reviewed history rather than reporting it as open

### Requirement: Managed storage metadata follows the configured backend
Application ingestion SHALL obtain managed backend identity through the file-store contract rather than deriving storage ownership from a physical local path. Changing the file-store implementation MUST NOT require a canonical data-model rewrite.

#### Scenario: Another configured managed backend
- **WHEN** an injected file store declares another backend name and supports the same contract
- **THEN** manual/staged/source ingestion records its backend and dispatches reads through that store with opaque keys
