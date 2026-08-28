## ADDED Requirements

### Requirement: Local My Notes storage
The system SHALL store Workbench-created paper notes in `literature_user_notes`, independently from synchronized Zotero Notes and annotations.

#### Scenario: Create a manual local note
- **WHEN** a user submits a non-empty local note for an existing paper
- **THEN** the note is stored with source `manual` and appears under My Notes

#### Scenario: Zotero library is synchronized
- **WHEN** a full or incremental Zotero sync replaces remote Notes and attachment metadata
- **THEN** existing My Notes, AI analyses, conversations, messages, and PDF text cache remain unchanged

### Requirement: Explicit Add to Notes
The system SHALL create a My Note from AI content only after the user explicitly activates Add to Notes for an AI result belonging to the current paper.

#### Scenario: Add an analysis to My Notes
- **WHEN** a user clicks Add to Notes on a persisted Overview, Deep Read, or selection result
- **THEN** the backend creates a local note with the appropriate AI source and does not write to Zotero

#### Scenario: Add an assistant message to My Notes
- **WHEN** a user clicks Add to Notes on a persisted assistant message for the current paper
- **THEN** the backend copies the answer into a local note with source `ai_chat`

#### Scenario: No explicit action
- **WHEN** AI analysis or conversation generation completes
- **THEN** no row is added to `literature_user_notes`

### Requirement: Zotero Notes and My Notes remain distinct
The Reader SHALL present synchronized Zotero Notes as read-only and local My Notes as a separate section without implying synchronization between them.

#### Scenario: Reader displays both note sources
- **WHEN** a paper has Zotero Notes and local My Notes
- **THEN** the sidebar labels and renders them in distinct views and exposes no Zotero editing control
