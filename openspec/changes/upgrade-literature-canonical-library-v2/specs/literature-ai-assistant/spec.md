## ADDED Requirements

### Requirement: Canonical AI identity compatibility
AI operations SHALL resolve legacy paper aliases before persistence and ownership checks, retain existing analyses/conversation/message IDs and bodies, and use canonical IDs for new data.

#### Scenario: Legacy conversation survives migration
- **WHEN** an existing conversation is opened through either its old paper URL or canonical paper URL after migration
- **THEN** both return the same retained messages and allow continued conversation

#### Scenario: Wrong canonical paper
- **WHEN** a conversation is requested under an unrelated canonical paper
- **THEN** access is rejected as resource not found

### Requirement: AI text is tied to the selected file
Cached PDF text SHALL identify the selected primary asset and be refreshed when that file changes.

#### Scenario: Replace primary PDF
- **WHEN** a different asset becomes the primary readable file
- **THEN** AI does not reuse text extracted from the previous asset
