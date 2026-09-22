import os
from pathlib import Path
import tempfile

import pytest

# Import-time app composition and un-overridden health/status tests must never
# initialize or upgrade the developer's configured database or contact providers.
_temporary_root = Path(__file__).resolve().parents[3] / '.venv' / 'tmp'
_temporary_root.mkdir(parents=True, exist_ok=True)
_application = tempfile.TemporaryDirectory(prefix='pytest-app-', dir=_temporary_root, ignore_cleanup_errors=True)
os.environ['DATABASE_URL'] = f'sqlite:///{Path(_application.name) / "workbench.db"}'
os.environ['LITERATURE_VAULT_ROOT'] = str(Path(_application.name) / 'vault')
os.environ['ZOTERO_DATA_DIR'] = ''
for _key in ('ZOTERO_USER_ID', 'ZOTERO_API_KEY', 'OPENALEX_API_KEY', 'DEEPSEEK_API_KEY', 'WORKBENCH_AGENT_TOKEN'):
    os.environ[_key] = ''

from app.main import app


def pytest_sessionfinish(session, exitstatus):
    _application.cleanup()


@pytest.fixture
def override_service():
    """Replace services on app.state for one test and restore them afterwards."""
    replaced: list[tuple[str, object]] = []

    def _override(name: str, service):
        replaced.append((name, getattr(app.state, name)))
        setattr(app.state, name, service)
        return service

    yield _override

    for name, original in reversed(replaced):
        setattr(app.state, name, original)
