# Proposal

## Why

Workbench has a local file-store port and content-addressed files, but its root is tied to the database location and reads do not verify integrity. Staged and finalized files can share a writable inode. These gaps must close before migrating real Zotero PDFs into independently owned assets.

## What Changes

- Independently configure the Literature Vault root, keeping the existing default and keys.
- Publish independent immutable originals; reject unsafe paths, inconsistent bytes and unsupported storage dispatch.
- Verify checksums before file/range delivery and report missing/corrupt/remote-only assets explicitly.
- Add read-only inventory and a dry-run-first, resumable copy/verify relocation command without deleting source files or rewriting paper IDs/keys/configuration.

## Capabilities

### New Capabilities

- `literature-vault`: portable managed asset keys, independent local storage, integrity inspection and safe relocation.

### Modified Capabilities

None in main specs. Reuses and strengthens file ownership behavior in the completed unarchived V2 canonical capability.

## Impact

Existing file-store Protocol and Local Filesystem adapter, composition/configuration, file-serving errors, Literature integrity endpoint and operational CLI, regression tests and operator documentation. No new dependency or frontend redesign. No schema rewrite.

## Non-goals

No NAS/WebDAV/S3 implementation, automatic service restart, source attachment acquisition, garbage collection, destructive repair, metadata workflow or scientific PDF parsing. The later asset migration Change will acquire remote files.
