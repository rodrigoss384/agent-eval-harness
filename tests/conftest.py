"""A suíte normal nunca pode gastar créditos por acidente."""

import httpx
import pytest


@pytest.fixture(autouse=True)
def deny_external_http(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return

    async def deny_async(*args, **kwargs):
        raise AssertionError(
            "HTTP externo proibido nos testes; use MockTransport ou ASGITransport."
        )

    def deny_sync(*args, **kwargs):
        raise AssertionError("HTTP externo proibido nos testes; use um transporte falso.")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny_sync)
