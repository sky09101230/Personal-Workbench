## 1. Configuration and ingress dependency

- [x] 1.1 Add `workbench_agent_token` to Settings, load it from `WORKBENCH_AGENT_TOKEN`, and document the empty example value.
- [x] 1.2 Implement a ProjectActivity presentation dependency that enforces configured Bearer authentication with `compare_digest`, generic 401/503 responses, and no token disclosure.
- [x] 1.3 Attach the dependency only to the four ingest POST routes, leaving health and query GET routes public.

## 2. Verification

- [x] 2.1 Extend API tests for public endpoints, all authentication failure/success cases, all ingest routes, unconfigured-token fail-closed behavior, and no business invocation on failures.
- [x] 2.2 Run the full API pytest command, strict OpenSpec validation, `git diff --check`, and inspect git status.
- [x] 2.3 Commit as `feat(project-activity): secure agent ingest endpoints` and push `codex/secure-project-activity-ingest`.
