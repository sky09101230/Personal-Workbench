class LiteratureError(Exception):
    """Expected errors at the Literature module boundary."""


class MigrationRequiredError(LiteratureError):
    pass


class WorkflowConflictError(LiteratureError):
    pass


class WorkflowNotFoundError(LiteratureError):
    pass


class ProviderNotConfiguredError(LiteratureError):
    pass


class ProviderAuthenticationError(LiteratureError):
    pass


class ProviderUnavailableError(LiteratureError):
    pass


class ProviderTimeoutError(ProviderUnavailableError):
    retryable = True


class InvalidCollectionIdentifierError(LiteratureError):
    pass


class LiteratureResourceNotFoundError(LiteratureError):
    pass


class PdfUnavailableError(LiteratureError):
    pass


class LocalAssetError(PdfUnavailableError):
    def __init__(self, state: str) -> None:
        super().__init__(f"Local asset {state}")
        self.state = state


class LiteratureAIError(LiteratureError):
    """Expected failures at the Literature AI boundary."""


class LiteratureAINotConfiguredError(LiteratureAIError):
    pass


class LiteratureAIProviderError(LiteratureAIError):
    retryable = False


class LiteratureAIRateLimitError(LiteratureAIProviderError):
    retryable = True


class LiteratureAITimeoutError(LiteratureAIProviderError):
    retryable = True


class LiteratureAIInvalidResponseError(LiteratureAIProviderError):
    pass


class LiteratureAIContextError(LiteratureAIError):
    pass


class LiteratureAINoTextError(LiteratureAIContextError):
    pass


class LiteratureAIResourceNotFoundError(LiteratureAIError):
    pass
