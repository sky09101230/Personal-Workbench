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
