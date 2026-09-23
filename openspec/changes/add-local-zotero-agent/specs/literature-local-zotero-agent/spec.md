## Purpose

Allow explicitly authorized recovery of registered Zotero PDFs from the browser user's computer without moving the Workbench database or exposing local filesystem access.

## ADDED Requirements

### Requirement: Local access requires local authorization
The helper SHALL bind loopback only and require an expiring credential generated locally, exact allowed Origin and Host validation. It MUST reject arbitrary filesystem paths and disclose no library data before pairing. Restart SHALL revoke sessions.

#### Scenario: Unpaired or foreign origin
- **WHEN** an unpaired caller or an unapproved origin requests an attachment
- **THEN** access is denied without metadata or file disclosure

#### Scenario: Authorized session expires
- **WHEN** an expired session requests a file
- **THEN** re-pairing is required and no bytes are disclosed

### Requirement: Only registered stable files are exported
The helper SHALL read consistent Zotero snapshots without mutating Zotero and resolve exact account, library, parent and attachment keys. It SHALL reject filesystem escapes, linked files and missing files. It SHALL provide pre/post observations and checksums without absolute paths.

#### Scenario: Source changes during transfer
- **WHEN** the registered file or relationship changes during export
- **THEN** recovery cannot finalize and the outcome identifies a changed source

### Requirement: Local recovery is explicit bounded and recoverable
The UI SHALL relay explicitly selected attachments to the existing Workbench API, support partial per-file outcomes and enforce a 50 MiB per-file limit. It SHALL report connection and browser-permission failures separately from missing files and provide the existing explicit upload fallback.

#### Scenario: Browser blocks loopback access
- **WHEN** the browser denies access to the helper
- **THEN** the UI explains the connection limitation without reporting Zotero files as absent

#### Scenario: Oversized local PDF
- **WHEN** a selected PDF exceeds 50 MiB
- **THEN** it is rejected explicitly without partial association or truncation
