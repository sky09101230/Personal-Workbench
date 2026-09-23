# Proposal

## Why

The Literature Zotero connector currently reads local Zotero attachments from the API service machine. When Zotero and the browser are on a different computer, the browser can show the attachment record but the API cannot read the PDF bytes, leaving otherwise recoverable sources in `needs_recovery`. A local, read-only Zotero agent will allow the user to recover selected attachments from the computer that actually stores them without moving or exposing the Zotero database.

## What Changes

- Add a small local Zotero agent that exposes read-only item and registered-PDF operations on loopback only.
- Add short-lived pairing and origin checks so only the Workbench UI can use the local agent.
- Add a browser-to-agent-to-API recovery flow for selected existing Literature source assets.
- Preserve the existing `paper_id`, source asset identity, role, provenance, checksum validation and idempotent ownership rules.
- Show agent connection state and per-attachment results in the Zotero import/recovery UI.
- Keep the current server-side Zotero connector and manual PDF upload paths as fallbacks.

## Capabilities

### New Capabilities

- `literature-local-zotero-agent`: Securely pair with a local read-only Zotero agent and stream explicitly selected registered PDF attachments to Workbench.

### Modified Capabilities

- `literature-asset-acquisition`: Allow a verified local-agent observation/stream as an additional source channel while retaining source stability, checksum and provenance requirements.
- `literature-library-readiness`: Allow retry of an exact source through the paired local agent and report agent unavailable, source unavailable and successful ownership distinctly.

## Impact

- Independent `apps/zotero-agent` package/process and Windows launch/configuration path; leave the ProjectActivity device agent separate.
- Literature API contracts and acquisition application ports for agent observations and streamed bytes.
- Literature import/recovery UI and local-agent pairing state.
- New unit, API, browser acceptance and security tests; no new external service or database module dependency.
