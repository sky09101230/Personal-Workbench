"""Shared vocabulary for external provider failures and retry policy."""

from dataclasses import dataclass
from enum import StrEnum
import time
from typing import Callable


class ProviderFailureKind(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    INVALID_RESPONSE = "invalid_response"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ProviderFailure(Exception):
    provider: str
    kind: ProviderFailureKind
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.provider}: {self.message}"


def should_retry(failure: ProviderFailure, attempt: int, max_attempts: int = 3) -> bool:
    return failure.retryable and 0 <= attempt < max_attempts - 1


def retry_call(operation: Callable[[], object], *, max_attempts: int = 3, backoff_seconds: float = 0.25) -> object:
    """Run a provider operation with bounded exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return operation()
        except ProviderFailure as failure:
            if not should_retry(failure, attempt, max_attempts):
                raise
            time.sleep(backoff_seconds * (2**attempt))
    raise RuntimeError("provider retry loop exhausted")
