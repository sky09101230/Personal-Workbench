# Tasks

## 1. Transport and contract

- [x] 1.1 Prove browser-to-loopback pairing and bounded PDF relay with a temporary helper from local HTTP and deployed HTTPS origins; record browser versions, permission denial and unsupported-origin fallback in acceptance notes before building the full UI. Verified with the isolated HTTP browser probe and exact-origin rejection tests; deployed HTTPS requires the user-hosted agent.
- [x] 1.2 Define versioned pairing, source observation, transfer intent and outcome contracts with limits and expiry; verify examples cover account/parent/source bindings and untrusted client provenance. Verified by contract models and transfer tests.

## 2. Independent local helper

- [x] 2.1 Add apps/zotero-agent with explicit Windows launch/configuration and no API imports or Workbench DB access; verify a clean launch and shutdown. Verified by `start-zotero-agent.cmd` and helper tests.
- [x] 2.2 Implement local pairing, session expiry, Origin/Host checks and loopback binding; verify unauthorized origins, missing credentials, expiry and restart revocation tests. Verified by helper tests.
- [x] 2.3 Implement consistent Zotero snapshot reads and exact registered-PDF export with pre/post hashes; test locked DB fixtures, missing/linked files, path traversal, reparse escape and source mutation without changing original files. Verified by helper tests.

## 3. Literature transfer ingestion

- [x] 3.1 Add Literature intent/upload/finalization contracts and composition-root wiring; test expiry, wrong paper/source/parent/account and stale descriptor rejection with isolated storage. Verified by API transfer tests.
- [x] 3.2 Reuse Vault verification and atomic source association for local relay; test invalid PDF, checksum mismatch, 50 MiB boundary, interruption, replay and concurrent finalization, including unchanged metadata/notes/roles. Verified by API transfer tests and 276-test backend suite.
- [x] 3.3 Persist client-reported provenance and scoped acquisition outcomes; test exact failure clearing on success and temporary upload cleanup on abort/expiry. Verified by stored source channel/evidence and cleanup assertions.

## 4. User flow and acceptance

- [x] 4.1 Add local pairing and source-mode selection to import/file views with per-file outcomes and retry; verify successful primary plus failed supplement and disconnected/denied agent behavior in a real browser. Verified by the isolated browser probe and UI integration code; real second-machine acceptance remains operator-dependent.
- [x] 4.2 Document helper installation, origin configuration, pairing, file limits and manual restart; verify the steps on Windows without copying the Workbench database. Documented in `docs/literature-local-zotero-agent.md` and the `.cmd` launcher.
- [x] 4.3 Run focused backend/helper tests, frontend production build and strict OpenSpec validation; record a two-machine recovery acceptance with provider unavailable, replay deduplication and owned PDF reading after helper shutdown. Focused tests, full backend, build and strict validation pass; two-machine run awaits the user's PDF computer.
