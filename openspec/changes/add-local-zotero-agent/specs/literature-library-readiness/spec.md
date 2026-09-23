## ADDED Requirements

### Requirement: Users distinguish local and server recovery
The import and file views SHALL offer explicit local-helper recovery for selected existing Zotero sources, including those resolved by server-side metadata import. They SHALL distinguish helper connection errors, missing files and verified ownership per attachment. Successful association SHALL clear the exact source failure atomically; connection failure SHALL NOT replace a source's state with a false missing-file result.

#### Scenario: Local PDF exists but server cannot read it
- **WHEN** the user selects local recovery and the paired helper exports a matching registered PDF
- **THEN** the existing paper becomes independently readable after API verification without moving its database

#### Scenario: Mixed attachment outcomes
- **WHEN** a selected paper's primary PDF succeeds and supplementary file fails
- **THEN** the UI reports both outcomes and permits retry of only the failed source
