# Design

## Context

See proposal.md for motivation. Existing acquisition owns verified PDF bytes separately from Zotero descriptors. The browser currently invokes server-side acquisition. Repository guidance reserves apps/agent for ProjectActivity observation; this Literature helper must instead be independently packaged under apps/zotero-agent and must not import API internals or access Workbench SQLite.

## Goals / Non-Goals

Goals: recover selected existing Zotero source assets from the browser's computer; reuse canonical associations and Vault validation; Windows-first explicit launch.

Non-goals: full offline metadata ingestion, background synchronization, arbitrary directory upload, automatic startup, a general device platform, or changing ProjectActivity.

## Decisions

- Use a small independently launched Python helper with an explicit Zotero directory and exact allowed Workbench origin. No desktop shell framework is needed. The helper generates a high-entropy, short-lived pairing secret locally, shown to the user for entry into Workbench; an API-issued credential alone cannot authorize local access. Sessions stay in browser memory, expire and are revoked on helper restart. Validate Host and Origin on every request, reject wildcard/null origins and rate-limit pairing. Bind 127.0.0.1 only.
- Use the existing registered-file snapshot approach as the behavioral model. Read a private consistent copy of Zotero DB/WAL/journal; never write original files. Resolve account/library, parent key and attachment key. Reject linked files for this first version, traversal and symlink/reparse escapes. Return no absolute paths or database contents.
- Browser obtains an exact source transfer intent from Literature API, asks the paired agent for observations and bytes, then uploads bytes to that API intent. API binds intent to existing paper/source/role and descriptor revision, expires it, computes its own hashes and validates PDF structure before atomic association. Agent observations are client-reported provenance, not cryptographic proof of Zotero authorship. Record that trust level explicitly; require available source checksum agreement, and never call an unverified replacement byte-identical recovery.
- Use sequential bounded transfers initially, maximum 50 MiB per browser-relayed PDF consistent with current browser uploads. Return an explicit oversized outcome; do not silently truncate. A bounded Blob relay is acceptable initially; no claim of constant-memory end-to-end streaming. Pre/post agent observations bind transfer to stable source version and file hash; failed or changed observations prevent commit. Clean temporary upload state on failure/expiry and reuse existing Vault objects on replay.
- Add “Connect local Zotero” and explicit local/server transfer selection to existing import and file recovery views. Existing metadata import remains server-side; local mode supplies eligible attachments for resulting existing canonical papers. Partial results distinguish disconnected agent, denied permission, missing source, changed source, oversized file and acquired/already-owned.

## Risks / Trade-offs

- Browser loopback access policy varies by browser and deployment origin -> first implementation task is an actual HTTP/HTTPS browser compatibility spike, including local-network permission denial. Do not recommend disabling browser security. Unsupported origins receive actionable fallback to explicit file upload.
- Same-origin malicious scripts can misuse an active session -> short expiry, memory-only secrets, explicit selected transfers and bounded requests; pairing is not protection against a compromised Workbench origin.
- Local metadata cannot prove identity independently -> server-issued intent, exact bindings, available source checksums and explicit client-reported provenance. No title matching or silent remapping.
- Large PDFs exceed browser limit -> report limit and preserve server-side 256 MiB acquisition/manual operational alternatives.

## Migration Plan

Ship additive Literature endpoints and disabled-until-connected UI, then helper launcher and instructions. No migration of real files is automatic. Add only Literature-owned persistence if transfer intents require it, using the existing migration mechanism. Verify with temporary Zotero fixtures and isolated Vault/database. Rollback disables local mode; existing owned objects remain readable and server-side acquisition remains available. Users restart services manually.
