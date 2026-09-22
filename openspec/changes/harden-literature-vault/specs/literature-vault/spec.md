## Purpose

Keep Workbench-owned literature files independently located, content-identified, integrity-verifiable and portable without changing paper or asset identities.

## ADDED Requirements

### Requirement: Storage location is independent of canonical data
Managed assets SHALL use backend, key and checksum identity without machine-specific absolute paths in domain records. The local Vault root SHALL be independently configurable while preserving the current default and existing keys. Unsupported backends MUST fail explicitly.

#### Scenario: Root changes after verified copy
- **WHEN** an operator copies and verifies managed objects and configures the new root
- **THEN** existing canonical and asset IDs and storage keys continue to open the same bytes without database rewrites

#### Scenario: Existing installation has no root override
- **WHEN** the API starts with an empty Vault-root setting
- **THEN** it uses the existing DB-adjacent asset directory and recognizes legacy flat files

### Requirement: Published assets are independent stable content
Finalized PDF bytes SHALL be independent of staging and filenames, identified by SHA-256 and atomically published without overwriting an inconsistent existing object. Managed file operations MUST reject escaping keys and redirected child paths.

#### Scenario: Staging is altered after publication
- **WHEN** a retained staged file is modified or removed after its original was published
- **THEN** the published original bytes remain unchanged

#### Scenario: Concurrent identical publication
- **WHEN** two uploads publish identical bytes
- **THEN** they reuse one verified content object without partial output or identity changes

#### Scenario: Redirected storage child
- **WHEN** a managed object or child directory redirects outside the configured Vault
- **THEN** read, write and cleanup operations reject it without accessing or deleting the external object

### Requirement: Integrity is checked before file delivery
The store SHALL verify checksum integrity before serving a local PDF or range and expose path-free inspection results with state, byte count and checksum. Missing, corrupt, invalid and unreadable local assets SHALL be distinguishable from verified assets and remote-only descriptors. Inspection MUST NOT repair data or fetch remote files.

#### Scenario: Corrupt PDF range request
- **WHEN** stored bytes no longer match the expected checksum
- **THEN** the request fails explicitly before delivering PDF bytes and inspection reports corruption

#### Scenario: Source is offline
- **WHEN** a verified owned asset is opened while Zotero is unavailable
- **THEN** the local bytes and byte ranges remain accessible without contacting Zotero

### Requirement: Inventory and relocation are non-destructive
The system SHALL provide read-only inventory and a dry-run-first copy/verify relocation operation. Apply SHALL preserve source files and database identities, verify every copied object and support repeat execution. Relocation MUST NOT silently switch configuration, delete files or proceed with unresolved staging or invalid owned source assets.

#### Scenario: Dry-run
- **WHEN** inventory or a relocation plan runs without explicit apply
- **THEN** source, destination, database and configuration remain unchanged

#### Scenario: Repeated verified copy
- **WHEN** a successful relocation copy is repeated
- **THEN** verified destination objects are reused and source bytes and database records remain unchanged

#### Scenario: Pending upload or missing owned file
- **WHEN** relocation sees an upload needing staging or an owned source object that cannot verify
- **THEN** it reports the blocking condition and leaves source/configuration unchanged
