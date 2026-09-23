# Literature foundation Goal gaps after operational closure

The foundation now has reviewed canonical identity, evidence-linked metadata, independent Vault storage, version/conflict/Radar review and verified acquisition of all currently available source PDFs. The foundation Goal is complete with these explicit, recoverable exceptions:

- 38 planned PDF sources were unavailable through both the configured local Zotero directory and the Web API at acquisition time. They affect 29 papers; 21 still have no owned primary PDF. They remain retryable `needs_recovery` states with source keys, filenames, titles and DOI in `20260923-missing-sources.json`.
- Eight historical parent-unresolved descriptors remain unassigned. Two are PDF descriptors and six are HTML; no canonical parent or file was guessed. Their conflict payloads and quarantine/reopen history remain auditable.
- Recovery from another Zotero backup or device needs a concrete source directory from the user/operator. A reviewed replacement upload can satisfy a paper's owned-asset need but does not prove byte identity with a missing original.
- NAS/WebDAV/S3 adapters, a garbage collector and automatic repair are deliberately absent. The storage port and opaque backend/key records permit a later adapter.
- Parsing, chunking, embedding, vector stores, RAG, citation/semantic/research maps and automatic knowledge extraction remain out of scope by design.

Acceptance evidence is in the six Change acceptance files and `docs/literature-foundation-acceptance.md`. Main capability specs are synchronized under `openspec/specs/` and `openspec validate --all --strict` passes for all 28 items. Missing source bytes remain a recoverable operational queue for a future backup/replacement upload; they do not invalidate the completed identity, evidence, Vault or provenance infrastructure.
