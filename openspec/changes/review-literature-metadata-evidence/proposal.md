# Proposal

## Why

The shared Literature resolver still replaces accepted metadata by source priority and can promote a preprint DOI during ingestion. A source refresh must instead preserve canonical values and produce an evidence-linked proposal that the user can inspect and decide.

## What Changes

- **BREAKING**: updates to existing bibliographic fields, including filling identity blanks or promoting a DOI, become proposals rather than source-priority overwrites.
- Link proposals and field decisions to stable evidence rows; retain conflicting proposals and enforce identifier ownership only at acceptance.
- Separate metadata completeness from review state and add explicit snapshot-based confirmation of current metadata.
- Extend existing metadata review UI with source evidence, conflict explanations, OpenAlex editing and current-snapshot confirmation.
- Additive schema upgrade with backup, existing dry-run migration support, replay and copied-real-data preservation acceptance.

## Capabilities

### New Capabilities

- `literature-metadata-evidence`: evidence-linked candidates, protected canonical fields and explicit metadata review decisions.

### Modified Capabilities

None in main specs. This supersedes source-priority mutation in unarchived V2 for new ingestion. Strong identity gates from `tighten-literature-identity-evidence` remain authoritative.

## Impact

Literature domain/workflow models, shared SQLite ingestion and review repository, existing review endpoints/UI, schema upgrade and regression/acceptance harnesses. No external metadata lookup or new dependency. No modification of other modules' tables or imports.

## Non-goals

Full identity-conflict resolution, preprint version-link management and Radar appearance validation form the next independent Change. Asset acquisition remains Change 4. No automatic merge/split, scholarly-verification claim, parsing or knowledge-base features.
