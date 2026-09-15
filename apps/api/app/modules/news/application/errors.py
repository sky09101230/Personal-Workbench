class NewsError(Exception):
    code = "news_error"


class NewsSourceError(NewsError):
    code = "news_source_unavailable"


class NewsProviderFailure(NewsSourceError):
    def __init__(self, message: str, *, code: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class NewsProviderTimeout(NewsProviderFailure):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="news_source_unavailable", retryable=True)


class NewsProviderRateLimited(NewsProviderFailure):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="news_source_unavailable", retryable=True)


class InvalidFeedItemError(NewsError):
    code = "invalid_feed_item"


class PaperResearchIdentityConflictError(NewsError):
    code = "paper_research_identity_conflict"
