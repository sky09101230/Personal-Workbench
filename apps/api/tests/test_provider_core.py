from app.core.providers import ProviderFailure, ProviderFailureKind, retry_call, should_retry


def test_retry_policy_is_bounded_and_only_for_retryable_failures() -> None:
    failure = ProviderFailure("demo", ProviderFailureKind.TIMEOUT, "slow", True)
    assert should_retry(failure, 0)
    assert should_retry(failure, 1)
    assert not should_retry(failure, 2)
    assert not should_retry(ProviderFailure("demo", ProviderFailureKind.AUTHENTICATION, "bad"), 0)


def test_retry_call_retries_transient_failure(monkeypatch) -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ProviderFailure("demo", ProviderFailureKind.TIMEOUT, "slow", True)
        return "ok"

    monkeypatch.setattr("app.core.providers.time.sleep", lambda _: None)
    assert retry_call(operation) == "ok"
    assert attempts == 3
