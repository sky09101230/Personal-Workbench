# literature-identity-evidence

## Purpose

Protect Workbench canonical Literature identity by requiring strong evidence for automatic association while retaining uncertain imports and historical relationships for review.

## Requirements

### Requirement: Automatic canonical association requires agreeing strong evidence
Literature SHALL associate an incoming record with an existing canonical paper only through a known canonical identity, stable external reference, replayable import origin or compatible normalized scholarly identifier. All available strong matches MUST agree. Title, author, year, similarity and AI judgments MUST NOT automatically merge canonical papers. This requirement supersedes the title-fallback allowance in Literature V2 for future Literature ingestion.

#### Scenario: Equivalent DOI representations
- **WHEN** separate sources supply compatible canonical and URL forms of the same DOI
- **THEN** the imports resolve to one stable canonical ID and retain both sources

#### Scenario: Weak bibliographic collision
- **WHEN** a new import shares title, year and author with an existing paper without shared strong evidence
- **THEN** it requires review with candidate IDs and is not automatically associated with that paper

#### Scenario: Strong matches disagree
- **WHEN** an import's DOI and source reference or arXiv identifier resolve to different canonical papers
- **THEN** the operation reports an identity conflict without changing either paper's ownership or research relationships

#### Scenario: Preprint without DOI
- **WHEN** a preprint supplies a compatible arXiv identity without a formal DOI
- **THEN** it can be imported and replayed under a stable Workbench ID

#### Scenario: Unresolved document without a collision
- **WHEN** a new paper lacks scholarly identifiers and has no competing candidate
- **THEN** it can be retained as an incomplete paper without fabricating a DOI or claiming verification

### Requirement: Reviewable imports retain uncertainty
Weak-match and conflicting-identity outcomes SHALL expose the reason and candidate identities through the existing conflict response or durable review state. Failed staged uploads MUST retain their candidate evidence and staged bytes for correction and retry. Source preservation MUST NOT claim identifiers owned by another canonical paper.

#### Scenario: Staged confirmation needs review
- **WHEN** confirmation detects only weak identity evidence for a potential match
- **THEN** the item remains reviewable and a corrected strong identifier can be retried without reuploading or altering the candidate paper's Notes

#### Scenario: Ambiguous source sync
- **WHEN** a source sync cannot safely resolve an incoming source record
- **THEN** it retains independent source evidence and a conflict instead of silently merging unrelated canonical papers

### Requirement: File identity does not merge scholarly identities
PDF SHA-256 SHALL identify bytes and support replay of a recorded upload association. It MUST NOT merge two canonical papers or override contradictory scholarly identity evidence. Explicit file association to one paper MUST leave other paper identities unchanged.

#### Scenario: Same bytes under a different filename
- **WHEN** a previously imported PDF is uploaded again with a different filename and compatible metadata
- **THEN** the existing upload association can be reused without creating another file object or using the filename as scholarly identity

#### Scenario: Same bytes explicitly attached to two papers
- **WHEN** the user associates identical PDF bytes with two existing canonical papers
- **THEN** both canonical IDs remain separate and their associations can reference the same content identity

#### Scenario: Repeated bytes with contradictory DOI
- **WHEN** identical bytes are reimported with a DOI owned by a different canonical paper
- **THEN** the conflicting upload is reviewable and no canonical papers are merged

### Requirement: Historical identity audit is non-destructive
The system SHALL provide a repeatable read-only identity audit reporting historical weak-association evidence, identifier inconsistencies and unresolved records. Audit MUST NOT initialize schema, reassign IDs, merge or split papers, or modify Notes, AI history, tags, reading state, collections, sources, origins and assets. Absence of detected issues MUST NOT be represented as scientific verification.

#### Scenario: Audit existing canonical data
- **WHEN** the audit runs repeatedly on an existing library
- **THEN** it reports identity counts and risks while all existing records and relationships remain unchanged

#### Scenario: Legacy database lacks canonical schema
- **WHEN** the audit is pointed at a legacy database
- **THEN** it reports the missing canonical schema without migrating that database
