from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from uuid import uuid4
from pathlib import Path

from app.core.config import settings
from app.core.observability import request_id_var
from app.core.task_repository import SQLiteTaskRepository
from app.core.task_router import router as task_router
from app.core.events import InMemoryEventPublisher
from app.modules.literature.application.ai.service import LiteratureAIService
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.infrastructure.ai.deepseek_provider import (
    DeepSeekLiteratureAIProvider,
)
from app.modules.literature.infrastructure.ai.paper_context import PaperContextBuilder
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from app.modules.literature.application.identity import IdentityReviewService
from app.modules.literature.presentation.identity_router import router as identity_router
from app.modules.literature.infrastructure.extraction import extract_metadata
from app.modules.literature.application.upload import UploadWorkflowService
from app.modules.literature.application.review import MetadataReviewService
from app.modules.literature.application.zotero_import import ZoteroImportService
from app.modules.literature.application.materialization import PdfMaterializationService
from app.modules.literature.application.errors import LiteratureError
from app.modules.literature.domain.canonical import IdentityConflictError
from app.modules.literature.presentation.upload_router import router as upload_router
from app.modules.literature.presentation.review_router import router as review_router
from app.modules.literature.presentation.workflow_contracts import workflow_error_handler
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.presentation.library_router import router as canonical_library_router
from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider
from app.modules.literature.presentation.ai_router import router as literature_ai_router
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

    class RequestIdMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            request_id = request.headers.get("X-Request-ID") or str(uuid4())
            token = request_id_var.set(request_id)
            try:
                response = await call_next(request)
                response.headers["X-Request-ID"] = request_id
                return response
            finally:
                request_id_var.reset(token)

    app.add_middleware(RequestIdMiddleware)
    app.state.task_repository = SQLiteTaskRepository(settings.database_url)
    app.state.task_repository.mark_interrupted()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    # Composition is kept here so presentation code does not know the provider implementation.
    literature_repository = SQLiteLiteratureIdentityRepository(settings.database_url)
    literature_files = LocalLiteratureFiles(settings.literature_vault_root or str(Path(settings.database_url.removeprefix("sqlite:///")).parent / "literature-assets"))
    literature_service = LiteratureService(
        ZoteroWebProvider(settings),
        literature_repository,
        literature_files,
    )
    app.state.literature_service = literature_service
    app.state.upload_workflow_service = UploadWorkflowService(literature_repository, literature_files, extract_metadata)
    app.state.metadata_review_service = MetadataReviewService(literature_repository)
    app.state.identity_review_service = IdentityReviewService(literature_repository)
    app.state.zotero_import_service = ZoteroImportService(literature_repository, literature_service.provider)
    app.state.materialization_service = PdfMaterializationService(literature_repository, literature_files, literature_service.provider)
    app.add_exception_handler(LiteratureError, workflow_error_handler)
    app.add_exception_handler(IdentityConflictError, workflow_error_handler)
    app.state.literature_ai_service = LiteratureAIService(
        literature=literature_service,
        provider=DeepSeekLiteratureAIProvider(settings),
        context=PaperContextBuilder(literature_service, literature_repository),
        repository=literature_repository,
    )
    app.state.event_publisher = InMemoryEventPublisher()
    app.state.news_service = NewsService(
        providers=(OpenAlexPaperProvider(settings), GitHubTrendingProvider()),
        repository=SQLiteNewsRepository(settings.database_url),
        topics=DEFAULT_TOPICS,
        summarizer=DeepSeekNewsSummarizer(settings),
        slot_limited_sources=("openalex",),
        event_publisher=app.state.event_publisher,
    )
    app.state.project_activity_service = ProjectActivityService(
        repository=SQLiteProjectActivityRepository(settings.database_url),
    )
    app.state.literature_ingestion_service = LiteratureIngestionService(
        literature_repository, literature_files, app.state.news_service.export_recommendation,
    )
    app.state.project_activity_agent_token = settings.workbench_agent_token
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
    app.include_router(canonical_library_router, prefix="/api/literature", tags=["literature-library"])
    app.include_router(upload_router, prefix="/api/literature", tags=["literature-uploads"])
    app.include_router(review_router, prefix="/api/literature", tags=["literature-metadata"])
    app.include_router(identity_router, prefix="/api/literature", tags=["literature-identity"])
    app.include_router(
        literature_ai_router,
        prefix="/api/literature",
        tags=["literature-ai"],
    )
    app.include_router(news_router, prefix="/api/news", tags=["news"])
    app.include_router(
        project_activity_router,
        prefix="/api/project-activity",
        tags=["project-activity"],
    )
    app.include_router(todo_router, prefix="/api/todo", tags=["todo"])
    app.include_router(task_router, prefix="/api", tags=["tasks"])
    return app


app = create_app()
