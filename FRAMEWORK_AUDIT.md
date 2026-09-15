# Framework hardening audit

## Current baseline

- `apps/api/app/main.py` is the composition root and wires four independent modules.
- Each module owns SQLite infrastructure and domain/application/presentation layers.
- Providers use HTTPX clients with fixed per-provider timeouts; retry and error semantics are implemented inconsistently.
- Routers map module-specific exceptions to `HTTPException` independently, so error response shapes are not globally uniform.
- Refresh and AI endpoints execute work inline; there is no persisted task status or progress API.
- Frontend modules each implement request loading/error behavior locally.
- No shared event boundary exists between modules.

## Delivery phases

1. Shared request id, structured error envelope, task status types, and logging hooks.
2. Migration registry, backup/restore command, provider error taxonomy, timeout/retry policy.
3. Persisted local task executor and refresh/AI task endpoints with compatibility behavior.
4. Shared frontend request/task state and user-visible retry feedback.
5. Optional domain events for cross-module integrations, with module boundaries preserved.

## First implementation targets

- Add `app/core/errors.py`, `app/core/observability.py`, and `app/core/tasks.py`.
- Add a global FastAPI exception/request-id middleware in `main.py`.
- Add focused tests for error envelopes and task lifecycle before migrating module endpoints.

## Constraints

- Preserve existing uncommitted changes.
- Keep module imports one-way through application ports.
- Do not expose credentials or write them to artifacts.
- Do not restart running services automatically.
