from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository
from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider
from app.modules.literature.presentation.router import router as literature_router


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Workbench API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Composition is kept here so presentation code does not know the provider implementation.
    app.state.literature_service = LiteratureService(
        ZoteroWebProvider(settings),
        SQLiteLiteratureRepository(settings.database_url),
    )

    @app.get("/api/health", tags=["core"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "workbench-api"}

    app.include_router(literature_router, prefix="/api/literature", tags=["literature"])
    return app


app = create_app()
