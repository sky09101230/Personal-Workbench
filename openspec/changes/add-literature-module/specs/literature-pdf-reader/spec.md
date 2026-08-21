## ADDED Requirements

### Requirement: Paper PDF access is served through the Workbench API
The system SHALL identify PDF attachments for a selected paper and expose read and download operations through `/api/literature/*` endpoints without exposing Zotero credentials to the browser.

#### Scenario: Stored PDF is available
- **WHEN** a paper has an accessible PDF attachment
- **THEN** the API SHALL stream the PDF with its content type and filename for the Reader and download action

#### Scenario: No accessible PDF exists
- **WHEN** a paper has no PDF attachment or its file cannot be retrieved through the configured provider
- **THEN** the API SHALL return an explicit unavailable result and SHALL NOT present a non-PDF attachment as a PDF

### Requirement: User can read a PDF in a dedicated Reader page
The system SHALL provide `/literature/papers/:id/reader` as a dedicated PDF Reader route that uses PDF.js and does not embed the PDF viewer in the Literature home view.

#### Scenario: Reader opens an accessible PDF
- **WHEN** a user activates Read PDF for a paper with an accessible PDF
- **THEN** the Reader SHALL render the document and show the paper title, a return-to-library action, and a download action

#### Scenario: User navigates the document
- **WHEN** a PDF is open in the Reader
- **THEN** the Reader SHALL support previous/next page navigation, page-number jump, zoom, and page-fit controls

### Requirement: Reader notes sidebar is read-only in V0.1
The Reader SHALL provide a toggleable sidebar for synced item Notes and annotation metadata when available, and SHALL NOT provide a custom PDF annotation editor.

#### Scenario: Notes sidebar is opened
- **WHEN** a user opens the Reader Notes sidebar
- **THEN** the system SHALL display synced item Notes and available annotation metadata for the selected paper

#### Scenario: User views an annotation
- **WHEN** annotation metadata is present
- **THEN** the Reader SHALL render it as read-only information and SHALL NOT create or modify annotations
