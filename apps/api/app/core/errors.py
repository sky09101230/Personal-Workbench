"""Shared error envelope primitives for the API hardening work."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorEnvelope:
    code: str
    message: str
    retryable: bool = False

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}
