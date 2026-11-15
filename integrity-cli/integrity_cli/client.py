"""
Thin HTTP clients wrapping calls to integrity-oracle and bcc_middleware.

Kept deliberately dumb: no retries, no circuit breaking, no caching. This is
a developer CLI, not a production agent runtime -- if a call fails we want
the real error surfaced in the terminal immediately, not papered over by
retry logic.
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import get_auth_token, get_config_value


class ApiError(Exception):
    """Raised for both HTTP-level errors (4xx/5xx) and transport failures
    (connection refused, timeout, DNS), so CLI commands can catch one
    exception type regardless of what went wrong underneath.

    `status` is the HTTP status, or None for a transport failure (see ApiUnreachable).
    `unverified` is True when the service could not give an answer -- unreachable or 5xx --
    which the v3 exit-code table reports as 3, never as a definite "no" (1)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status

    @property
    def unverified(self) -> bool:
        return self.status is None or self.status >= 500


class ApiUnreachable(ApiError):
    """Transport failure: connection refused, timeout, DNS. No HTTP status."""


class IntegrityClient:
    """Talks to integrity-oracle. Base URL comes from ORACLE_URL (env var
    overrides the config file -- see config.get_config_value), defaulting to
    the docker-compose port in INTERFACE_CONTRACT.md section 2."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or get_config_value("ORACLE_URL")).rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = httpx.request(
                method, url, headers=self._headers(), timeout=self.timeout, **kwargs
            )
        except httpx.HTTPError as e:
            raise ApiUnreachable(f"Connection error calling {url}: {e}") from e
        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.is_error:
            detail = response.text
            try:
                body = response.json()
                if isinstance(body, dict) and "detail" in body:
                    detail = body["detail"]
            except ValueError:
                pass
            raise ApiError(f"{response.status_code} {response.reason_phrase}: {detail}", status=response.status_code)
        if not response.content:
            return {}
        return response.json()

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json_data: dict[str, Any] | None = None) -> Any:
        return self._request("POST", endpoint, json=json_data)


class BccClient(IntegrityClient):
    """Talks to bcc_middleware. Base URL comes from BCC_MIDDLEWARE_URL."""

    def __init__(self, timeout: float = 10.0):
        super().__init__(base_url=get_config_value("BCC_MIDDLEWARE_URL"), timeout=timeout)
