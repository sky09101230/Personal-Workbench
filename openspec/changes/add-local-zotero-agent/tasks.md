# Tasks

## 1. Transport and contract

- [ ] 1.1 Prove browser-to-loopback pairing and bounded PDF relay with a temporary helper from local HTTP and deployed HTTPS origins; record browser versions, permission denial and unsupported-origin fallback in acceptance notes before building the full UI.
- [ ] 1.2 Define versioned pairing, source observation, transfer intent and outcome contracts with limits and expiry; verify examples cover account/parent/source bindings and untrusted client provenance.

## 2. Independent local helper

- [ ] 2.1 Add apps/zotero-agent with explicit Windows launch/configuration and no API imports or Workbench DB access; verify a clean launch and shutdown.
- [ ] 2.2 Implement local pairing, session expiry, Origin/Host checks and loopback binding; verify unauthorized origins, missing credentials, expiry and restart revocation tests.
- [ ] 2.3 Implement consistent Zotero snapshot reads and exact registered-PDF export with pre/post hashes; test locked DB fixtures, missing/linked files, path traversal, reparse escape and source mutation without changing original files.

## 3. Literature transfer ingestion

- [ ] 3.1 Add Literature intent/upload/finalization contracts and composition-root wiring; test expiry, wrong paper/source/parent/account and stale descriptor rejection with isolated storage.
- [ ] 3.2 Reuse Vault verification and atomic source association for local relay; test invalid PDF, checksum mismatch, 50 MiB boundary, interruption, replay and concurrent finalization, including unchanged metadata/notes/roles.
- [ ] 3.3 Persist client-reported provenance and scoped acquisition outcomes; test exact failure clearing on success and temporary upload cleanup on abort/expiry.

## 4. User flow and acceptance

- [ ] 4.1 Add local pairing and source-mode selection to import/file views with per-file outcomes and retry; verify successful primary plus failed supplement and disconnected/denied agent behavior in a real browser.
- [ ] 4.2 Document helper installation, origin configuration, pairing, file limits and manual restart; verify the steps on Windows without copying the Workbench database.
- [ ] 4.3 Run focused backend/helper tests, frontend production build and strict OpenSpec validation; record a two-machine recovery acceptance with provider unavailable, replay deduplication and owned PDF reading after helper shutdown.
