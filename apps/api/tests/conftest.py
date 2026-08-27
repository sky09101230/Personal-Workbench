import pytest

from app.main import app


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
