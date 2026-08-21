# Repository Guidelines

## Project Structure & Module Organization

This monorepo contains the FastAPI backend in `apps/api` and the React + TypeScript frontend in `apps/web`. Backend code lives in `apps/api/app`: keep shared configuration in `core/`, and organize each feature under `modules/<feature>/` with `domain/`, `application/`, `infrastructure/`, and `presentation/` layers. Wire providers and routers in `app/main.py`; provider-specific Zotero code belongs only in `infrastructure/providers/zotero/`.

Frontend source is in `apps/web/src`. Put application composition in `app/`, reusable shell and module registry code in `core/`, and feature UI in `modules/<feature>/`. Backend tests are in `apps/api/tests`.

## Build, Test, and Development Commands

Run commands from the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps\api\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --reload
npm.cmd --prefix apps\web install
npm.cmd --prefix apps\web run dev
npm.cmd --prefix apps\web run build
.\.venv\Scripts\python.exe -m pytest -q apps\api\tests --basetemp .venv\tmp\pytest -p no:cacheprovider
```

The API serves on port 8000; Vite serves on port 5173 and proxies `/api`. Use the repository-local pytest temp directory to avoid Windows user-temp permission issues.

After changing code or configuration, do not restart the API or Vite server in the background. Tell the user which service needs a restart and let them restart it manually.

## Coding Style & Naming Conventions

Use four-space indentation and `snake_case` for Python functions, modules, and tests. Use two-space indentation, TypeScript types, `PascalCase` React components, and `camelCase` values in the frontend. Preserve the current layer boundaries: presentation depends on application services; application code depends on ports and domain models, not Zotero implementations. No formatter, linter, or coverage threshold is configured, so avoid introducing one incidentally.

## Testing Guidelines

Use pytest and name test files `test_*.py` and tests `test_*`. Add or update endpoint tests when changing API contracts. Verify production frontend changes with `npm.cmd --prefix apps\web run build`. There is no frontend test runner yet; do not claim browser behavior is covered by pytest.

## Commits, Pull Requests, and Configuration

The `main` branch has no commits, so it has no established commit-message convention. Use short imperative subjects with an optional scope, for example `feat(literature): add collection status endpoint`. Keep pull requests focused; describe behavior, list verification commands, link the issue when applicable, and include screenshots for UI changes.

Never commit `.env`, Zotero credentials, databases, build output, or dependency directories. Use environment variables documented in `.env.example`.
