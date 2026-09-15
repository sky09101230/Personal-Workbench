"""Small, dependency-free observability hooks shared by API modules."""

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("workbench")


def current_request_id() -> str | None:
    return request_id_var.get()
