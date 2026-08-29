class NewsError(Exception):
    code = "news_error"


class NewsSourceError(NewsError):
    code = "news_source_unavailable"


class InvalidFeedItemError(NewsError):
    code = "invalid_feed_item"


class PaperResearchIdentityConflictError(NewsError):
    code = "paper_research_identity_conflict"
