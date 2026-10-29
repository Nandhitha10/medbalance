"""HTTP client factories with timeout and retry configuration."""

import httpx


def create_http_client(
    timeout: float = 10.0,
    max_retries: int = 3,
    **kwargs,
) -> httpx.AsyncClient:
    """Create an asynchronous httpx client with standard retries and timeouts."""
    transport = httpx.AsyncHTTPTransport(retries=max_retries)
    client_timeout = httpx.Timeout(timeout)
    return httpx.AsyncClient(transport=transport, timeout=client_timeout, **kwargs)


def create_sync_http_client(
    timeout: float = 10.0,
    max_retries: int = 3,
    **kwargs,
) -> httpx.Client:
    """Create a synchronous httpx client with standard retries and timeouts."""
    transport = httpx.HTTPTransport(retries=max_retries)
    client_timeout = httpx.Timeout(timeout)
    return httpx.Client(transport=transport, timeout=client_timeout, **kwargs)
