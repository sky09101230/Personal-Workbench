from app.core.events import DomainEvent, InMemoryEventPublisher


def test_in_memory_events_route_by_name() -> None:
    publisher = InMemoryEventPublisher()
    received = []
    publisher.subscribe("todo.created", received.append)
    publisher.publish(DomainEvent.create("todo.created", "task-1", {"title": "Read"}))
    publisher.publish(DomainEvent.create("news.saved", "item-1"))
    assert received[0].aggregate_id == "task-1"
    assert received[0].payload["title"] == "Read"
