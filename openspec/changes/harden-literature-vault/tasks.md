# Tasks

## 1. Portable verified storage

- [x] 1.1 Configure the Vault root independently and expose integrity through the existing port; test default/override composition and unsupported backend behavior.
- [x] 1.2 Harden stage/finalize/open/cleanup containment and publish independent originals; test staging mutation, concurrent duplicates, redirected paths and inconsistent targets.
- [x] 1.3 Verify local bytes before ranges and add paper-scoped integrity API; test offline Reader, missing/corrupt states and response path privacy.

## 2. Operations and acceptance

- [x] 2.1 Add read-only inventory and dry-run/apply copy verification with pending-upload guards; test replay, failure, old keys and no DB/source mutations.
- [x] 2.2 Run real read-only inventory and on-disk relocation/Reader acceptance; document remaining remote assets and operator configuration/recovery steps.
- [x] 2.3 Run backend suite, strict OpenSpec validation and diff checks; record acceptance, update roadmap and commit this Change before proceeding.
