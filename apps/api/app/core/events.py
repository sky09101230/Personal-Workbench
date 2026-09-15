from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol


@dataclass(frozen=True)
class DomainEvent:
    name: str
    aggregate_id: str
    occurred_at: datetime
    payload: dict[str, object]

    @classmethod
    def create(cls, name: str, aggregate_id: str, payload: dict[str, object] | None = None):
        return cls(name, aggregate_id, datetime.now(timezone.utc), payload or {})


class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> None: ...


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[DomainEvent], None]]] = {}

    def subscribe(self, name: str, handler: Callable[[DomainEvent], None]) -> None:
        self._handlers.setdefault(name, []).append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(event.name, []):
            handler(event)
