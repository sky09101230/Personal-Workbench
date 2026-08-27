# Repository Guidelines

## Project Purpose & Structure

Personal Workbench: a local, single-user research workbench with four strictly independent backend modules — Literature (Zotero-backed library reader), News (external feed discovery), Todo (project/task action workbench), and ProjectActivity (external real-work observation). FastAPI backend lives in `apps/api`, and the React + TypeScript frontend lives in `apps/web`.

`apps/agent` is an independently deployed device client, not a backend feature module. It observes local device/workspace activity and reports through the ProjectActivity API; it must not import `apps/api` internals or access the Workbench SQLite database directly.

Backend code lives in `apps/api/app`: keep shared configuration in `core/config.py`, and organize each feature under `modules/<feature>/` with `domain/` (dataclass models), `application/` (services, `Protocol` ports, stable error types), `infrastructure/` (SQLite cache, external providers, AI planners/summarizers), and `presentation/` (FastAPI router with Pydantic request/response contracts).

Composition rules:

- `app/main.py` is the composition root. It instantiates every provider/repository/planner/service and stores services on `app.state.<module>_service`; presentation code resolves services from `app.state` and must not construct implementations itself.
- Modules must not import each other's code. Provider-specific code belongs only in that module's `infrastructure/` (e.g. Zotero in `literature/infrastructure/providers/zotero/`; OpenAlex, GitHub trending, DeepSeek under `news/` and `todo/`).
- All four modules share one SQLite database (`DATABASE_URL`, default `sqlite:///./data/workbench.db`), but each module owns only its own `literature_*` / `news_*` / `todo_*` / `activity_*` tables, with its own `_SCHEMA_VERSION` migration handled inside that module's infrastructure layer. Never read another module's tables.
- API paths are `/api/<module>/*`; ids returned by the API are opaque — do not assemble or parse them.

Frontend source is in `apps/web/src`: page composition and path-based routing in `app/App.tsx` (plain `window.location.pathname` matching — no router library), shell and the module registry in `core/`, and feature UI in `modules/<feature>/` (a `<Feature>Page.tsx`, an `api.ts` fetch client, `types.ts` contracts, `components/`). A new module must be registered in `core/modules/registry.ts`. Global styles live in `src/styles.css`; modules ship their own scoped CSS file. Backend tests are in `apps/api/tests`.

## Spec-Driven Changes (openspec)

New features follow the OpenSpec workflow in `openspec/`: an active change lives in `openspec/changes/<change-name>/` containing `proposal.md`, `design.md`, `specs/`, and `tasks.md`; completed changes move to `openspec/changes/archive/YYYY-MM-DD-<name>/`, and accepted behavior is documented as capabilities under `openspec/specs/`. Check for an existing or archived change before designing something new.

## Build, Test, and Development Commands

Run commands from the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps\api\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --reload --env-file .env
npm.cmd --prefix apps\web install
npm.cmd --prefix apps\web run dev
npm.cmd --prefix apps\web run build
.\.venv\Scripts\python.exe -m pytest -q apps\api\tests --basetemp .venv\tmp\pytest -p no:cacheprovider
```

The API serves on port 8000; Vite serves on port 5173 and proxies `/api`. Use the repository-local pytest temp directory to avoid Windows user-temp permission issues. If pytest fails to clean `.venv\tmp\pytest` with a Windows permission error (another process holds it), run against a fresh `--basetemp .venv\tmp\pytest-<name>` instead of deleting locked files. A repo-root `start-workbench.cmd` launches both servers in Windows Terminal.

After changing code or configuration, do not restart the API or Vite server in the background. Tell the user which service needs a restart and let them restart it manually.

## Coding Style & Naming Conventions

Use four-space indentation and `snake_case` for Python functions, modules, and tests. Use two-space indentation, TypeScript types, `PascalCase` React components, and `camelCase` values in the frontend.

Keep the current layer boundaries: presentation depends on application services; application code depends on ports (`Protocol`s) and domain models, never on provider implementations; domain models are plain dataclasses (Pydantic appears only in `presentation/` request/response contracts). External HTTP calls live exclusively in infrastructure providers/planners/summarizers, so API keys never leave the backend. No formatter, linter, or coverage threshold is configured, so avoid introducing one incidentally.

## Testing Guidelines

Use pytest and name test files `test_*.py` and tests `test_*`. Add or update endpoint tests when changing API contracts. The established pattern: use the shared `override_service` fixture from `apps/api/tests/conftest.py` to swap a module's service on `app.state` for one built with fake/in-memory collaborators (tmp_path SQLite, stub planners/providers, injected clocks); it restores the original automatically after each test. Verify production frontend changes with `npm.cmd --prefix apps\web run build`. There is no frontend test runner yet; do not claim browser behavior is covered by pytest.

## Commits, Pull Requests, and Configuration

Feature work happens on `codex/<topic>` branches merged into `main` via pull requests. Commit subjects follow the established conventional style: short imperative with an optional scope, for example `feat(todo): add quick capture`, `test(news): cover trending provider`, `docs(openspec): archive change`. Keep pull requests focused; describe behavior, list verification commands, link the issue when applicable, and include screenshots for UI changes.

Never commit `.env`, credentials, SQLite databases (`*.db`), build output, or dependency directories — `.gitignore` already excludes them. Configuration comes from environment variables documented in `.env.example`: `DATABASE_URL`, `CORS_ORIGINS`, `ZOTERO_USER_ID`, `ZOTERO_API_KEY`, optional `OPENALEX_API_KEY`, and optional DeepSeek settings (`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`) shared by the news summarizer and todo planner. The browser only ever talks to `/api/*`; external services are called from backend infrastructure code.
