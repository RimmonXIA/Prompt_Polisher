from __future__ import annotations


class ProviderError(RuntimeError):
    """Base error for provider adapter failures."""


class ProviderConnectionError(ProviderError):
    """Network-level connectivity failure."""


class ProviderTimeoutError(ProviderError):
    """Provider call timed out."""


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""


class ProviderAuthError(ProviderError):
    """Provider authentication/authorization failure."""


class ProviderResponseError(ProviderError):
    """Provider returned an invalid or unsuccessful response."""
