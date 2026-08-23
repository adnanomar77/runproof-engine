"""Optional boundary adapters for automatic RunProof observation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request

from .core import RunContext


class Adapter(Protocol):
    """Contract implemented by an automatic boundary adapter."""

    name: str

    def install(self, context: RunContext) -> Any:
        """Install hooks and return a zero-argument uninstall callback."""


@dataclass(frozen=True)
class AdapterInfo:
    name: str
    version: str
    capabilities: tuple[str, ...]


_SECRET_QUERY_MARKERS = (
    "token",
    "key",
    "secret",
    "password",
    "credential",
    "authorization",
)


def _safe_url(value: str) -> str:
    """Keep URL structure while redacting likely secret query values."""
    try:
        parts = urlsplit(value)
        query = []
        for key, item in parse_qsl(parts.query, keep_blank_values=True):
            safe_item = "[REDACTED]" if any(marker in key.lower() for marker in _SECRET_QUERY_MARKERS) else item
            query.append((key, safe_item))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    except ValueError:
        return value[:500]


def _request_details(value: Any, data: Any) -> tuple[str, str, str | None]:
    if isinstance(value, Request):
        url = value.full_url
        method = value.method or ("POST" if value.data is not None else "GET")
        body = value.data
    else:
        url = str(value)
        method = "POST" if data is not None else "GET"
        body = data
    body_bytes = body if isinstance(body, bytes) else str(body).encode("utf-8") if body is not None else None
    digest = hashlib.sha256(body_bytes).hexdigest() if body_bytes else None
    return method.upper(), _safe_url(url), digest


class UrllibAdapter:
    """Observe calls through ``urllib.request.urlopen`` without consuming responses."""

    name = "urllib"
    info = AdapterInfo(
        name="urllib",
        version="1",
        capabilities=("http-request-metadata", "response-status", "secret-query-redaction"),
    )

    def install(self, context: RunContext) -> Any:
        import urllib.request as urllib_request

        original = urllib_request.urlopen
        adapter = self

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            request_value = args[0] if args else kwargs.get("url")
            data = args[1] if len(args) > 1 else kwargs.get("data")
            method, url, body_sha256 = _request_details(request_value, data)
            try:
                response = original(*args, **kwargs)
            except Exception as error:
                context._event(
                    "http_request_failed",
                    {
                        "adapter": adapter.name,
                        "method": method,
                        "url": url,
                        "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
                        "message": str(error),
                    },
                )
                raise
            status_code = getattr(response, "status", None) or getattr(response, "code", None)
            context._event(
                "http_request_observed",
                {
                    "adapter": adapter.name,
                    "method": method,
                    "url": url,
                    "body_sha256": body_sha256,
                    "status_code": status_code,
                },
            )
            context.boundary(
                "network_response",
                target=url,
                reason="automatic urllib adapter does not consume or archive the response body",
                replay="requires_live_service",
            )
            return response

        urllib_request.urlopen = wrapped
        context._event("adapter_installed", {"name": self.name, "version": self.info.version})

        def uninstall() -> None:
            if urllib_request.urlopen is wrapped:
                urllib_request.urlopen = original
            context._event("adapter_uninstalled", {"name": self.name})

        return uninstall


def default_adapters() -> tuple[Adapter, ...]:
    """Return safe standard-library adapters enabled by automatic capture."""
    return (UrllibAdapter(),)


__all__ = ["Adapter", "AdapterInfo", "UrllibAdapter", "default_adapters"]
