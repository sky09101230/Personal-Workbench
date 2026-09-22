## Purpose

Keep canonical Literature provenance independent from weakly grouped discovery history when users explicitly save Radar recommendations.

## ADDED Requirements

### Requirement: Radar Save associates only the selected recommendation
Saving a Radar recommendation SHALL resolve its current exported metadata through the common strong Literature identity policy and record only the selected recommendation as a canonical origin. Other grouped appearances SHALL remain unverified discovery evidence and MUST NOT become saved origins solely because they share a News group.

#### Scenario: Grouped historical recommendations lack identity snapshots
- **WHEN** the user saves one recommendation from a group with several historical appearances
- **THEN** only that recommendation becomes saved and the other appearances remain explicitly unverified evidence

#### Scenario: Another recommendation is explicitly saved later
- **WHEN** the user later saves another recommendation with compatible strong identity
- **THEN** it can resolve to the same canonical ID with its own origin through the common resolver

#### Scenario: Historical saved origins already exist
- **WHEN** the new handoff behavior is deployed
- **THEN** existing origin records and saved relationships are preserved rather than silently reassigned or removed
