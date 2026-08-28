class LiteratureError(Exception):
    """Expected errors at the Literature module boundary."""


class ProviderNotConfiguredError(LiteratureError):
    pass


class ProviderAuthenticationError(LiteratureError):
    pass


class ProviderUnavailableError(LiteratureError):
    pass


class InvalidCollectionIdentifierError(LiteratureError):
    pass


class LiteratureResourceNotFoundError(LiteratureError):
    pass


class PdfUnavailableError(LiteratureError):
    pass


class LiteratureAIError(LiteratureError):
    """Expected failures at the Literature AI boundary."""


class LiteratureAINotConfiguredError(LiteratureAIError):
    pass


class LiteratureAIProviderError(LiteratureAIError):
    pass


class LiteratureAIRateLimitError(LiteratureAIProviderError):
    pass


class LiteratureAIInvalidResponseError(LiteratureAIProviderError):
    pass


class LiteratureAIContextError(LiteratureAIError):
    pass


class LiteratureAINoTextError(LiteratureAIContextError):
    pass


class LiteratureAIResourceNotFoundError(LiteratureAIError):
    pass
