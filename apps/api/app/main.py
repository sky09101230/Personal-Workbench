from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository
from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider
from app.modules.literature.presentation.router import router as literature_router
from app.modules.news.application.service import NewsService
from app.modules.news.infrastructure.cache.sqlite import SQLiteNewsRepository
from app.modules.news.infrastructure.providers.demo.provider import DEFAULT_TOPICS
from app.modules.news.infrastructure.providers.github.trending.provider import GitHubTrendingProvider
from app.modules.news.infrastructure.providers.openalex.provider import OpenAlexPaperProvider
from app.modules.news.infrastructure.summarizers.deepseek import DeepSeekNewsSummarizer
from app.modules.news.presentation.router import router as news_router
from app.modules.project_activity.application.errors import ProjectActivityError
from app.modules.project_activity.application.service import ProjectActivityService
from app.modules.project_activity.infrastructure.sqlite import SQLiteProjectActivityRepository
from app.modules.project_activity.presentation.router import (
    project_activity_error_handler,
    router as project_activity_router,
)
from app.modules.todo.application.errors import TodoError
from app.modules.todo.application.service import TodoService
from app.modules.todo.infrastructure.planners.deepseek import DeepSeekTodoPlanner
from app.modules.todo.infrastructure.sqlite import SQLiteTodoRepository
from app.modules.todo.presentation.router import router as todo_router, todo_error_handler


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Workbench API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    # Composition is kept here so presentation code does not know the provider implementation.
    app.state.literature_service = LiteratureService(
        ZoteroWebProvider(settings),
        SQLiteLiteratureRepository(settings.database_url),
    )
    app.state.news_service = NewsService(
        providers=(OpenAlexPaperProvider(settings), GitHubTrendingProvider()),
        repository=SQLiteNewsRepository(settings.database_url),
        topics=DEFAULT_TOPICS,
        summarizer=DeepSeekNewsSummarizer(settings),
        slot_limited_sources=("openalex",),
    )
    app.state.project_activity_service = ProjectActivityService(
        repository=SQLiteProjectActivityRepository(settings.database_url),
    )
    app.state.todo_service = TodoService(
        repository=SQLiteTodoRepository(settings.database_url),
        planner=DeepSeekTodoPlanner(settings),
    )
    app.add_exception_handler(ProjectActivityError, project_activity_error_handler)
    app.add_exception_handler(TodoError, todo_error_handler)

    @app.get("/api/health", tags=["core"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "workbench-api"}

    app.include_router(literature_router, prefix="/api/literature", tags=["literature"])
    app.include_router(news_router, prefix="/api/news", tags=["news"])
    app.include_router(
        project_activity_router,
        prefix="/api/project-activity",
        tags=["project-activity"],
    )
    app.include_router(todo_router, prefix="/api/todo", tags=["todo"])
    return app


app = create_app()
