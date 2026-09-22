## Purpose

Bring external Literature PDF bytes into independently owned storage with stable source/version evidence, repeatable migration and preserved canonical research data.

## ADDED Requirements

### Requirement: Acquisition verifies a stable source and owned content
PDF acquisition SHALL validate source identity, parent and version before and after a bounded download, compare an available source checksum, and publish/verify a SHA-256 identified owned object. Source or checksum changes MUST prevent association. Streams MUST close on success and failure.

#### Scenario: Legacy descriptor has no version
- **WHEN** an eligible cached PDF has no content version
- **THEN** acquisition obtains fresh source observations and records the actual observed version while retaining the original descriptor

#### Scenario: Source changes during download
- **WHEN** the observed source version, parent or content checksum changes
- **THEN** no owned association is committed and the result reports a retryable source change

#### Scenario: Cloud file is absent but the registered local Zotero PDF exists
- **WHEN** an explicitly configured local Zotero directory has the matching account, user-library item and parent
- **THEN** the system can acquire its registered PDF through verified local snapshots without changing Zotero data, guessing a filename or persisting an absolute source path

### Requirement: Source acquisition preserves canonical and file relationships
Acquisition SHALL retain source descriptors and canonical IDs, metadata, Notes, AI, native organization and reading/deletion state. It SHALL preserve file roles and record the source-to-owned mapping and provenance atomically. Filename similarity MUST NOT determine asset or scholarly identity.

#### Scenario: Supplementary PDF is acquired
- **WHEN** a supplementary attachment is copied
- **THEN** it remains supplementary and neither canonical metadata nor the user's primary selection changes

#### Scenario: Two sources provide identical bytes
- **WHEN** equal PDF bytes are acquired for the same paper and role
- **THEN** the verified content/association can be reused while both source observations remain traceable

### Requirement: Migration is planned backed up and resumable
The default migration operation SHALL produce a no-network read-only plan. Explicit apply SHALL validate plan/source bindings, back up before writes, bound each batch and produce per-asset results. Replay SHALL reuse verified matching copies without another download. Interrupted publication/association MUST be safely retryable.

#### Scenario: Dry-run against the real library
- **WHEN** a migration plan is generated
- **THEN** source database and Vault stay unchanged and excluded/unassigned descriptors are reported

#### Scenario: Retry after publication but before database commit
- **WHEN** a previous attempt published verified bytes but failed to associate them
- **THEN** retry can reuse those bytes and create exactly one owned association with durable source evidence

### Requirement: Owned PDF reads are independent of the external provider
The Reader SHALL prefer an owned copy corresponding to a selected source attachment and otherwise prefer owned files within the same role. Owned bytes MUST remain usable without Zotero, and corrupt/missing local content MUST NOT be reported as verified.

#### Scenario: Zotero is offline after migration
- **WHEN** the user opens a migrated paper's primary PDF
- **THEN** the Reader serves the verified owned bytes, including ranges, without contacting Zotero
