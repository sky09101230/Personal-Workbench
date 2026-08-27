## Context

ProjectActivity has four write endpoints used by the separately deployed Agent and three read-only project query endpoints. The router currently resolves the service directly, while global settings are loaded once from environment variables. Authentication is an HTTP ingress concern and must not alter service, domain, repository, or schema contracts.

## Goals / Non-Goals

**Goals:**
- Protect only the four Agent ingest POST routes with a configured bearer token.
- Fail closed with 503 when the server token is absent, and return standards-compatible 401 responses for credential failures.
- Preserve public health and query GET behavior and ensure rejected requests never call business methods.

**Non-Goals:**
- No authentication for health or query GET endpoints.
- No changes to ProjectActivity application semantics, persistence, frontend, token rotation, or additional auth schemes.

## Decisions

- **Router dependency for ingress auth:** Add a small `require_agent_token` FastAPI dependency in `project_activity.presentation`, attached only to ingest routes. This keeps authorization before service invocation and avoids coupling `ProjectActivityService` to HTTP headers. A middleware or service-level check would broaden scope or violate layer boundaries.
- **Settings-backed secret:** Add `workbench_agent_token: str = ""` to the frozen `Settings` dataclass and load/strip `WORKBENCH_AGENT_TOKEN`. The dependency reads the app's configured settings value (with a request-independent closure/dependency) rather than reading environment variables per request, matching existing composition.
- **Credential handling:** Parse the `Authorization` header as exactly the Bearer scheme plus a non-empty token, compare with `secrets.compare_digest`, and raise `HTTPException(401, headers={"WWW-Authenticate": "Bearer"})` on malformed or mismatched credentials. If the configured token is empty, raise 503 before credential comparison. Error details remain generic and contain no token.
- **Test isolation:** Tests override the dependency or app settings in-process and use explicit headers; they do not rely on `.env`. Existing public endpoint tests are updated to supply a test token only where ingest is exercised.

## Risks / Trade-offs

- [Risk] A process restart is required for environment token changes because settings are loaded at import/startup. → Mitigation: document the environment variable and rely on normal deployment restart semantics.
- [Risk] Strict header parsing may reject unusual but non-standard authorization formatting. → Mitigation: support case-insensitive `Bearer` scheme and a single non-empty credential token, while keeping malformed input 401.
- [Risk] Existing Agent callers without a token will receive 401 after deployment. → Mitigation: configure `WORKBENCH_AGENT_TOKEN` and update Agent deployment before enabling protected ingest.
