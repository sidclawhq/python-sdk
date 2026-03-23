from __future__ import annotations

import random

import httpx

from ._constants import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, SDK_VERSION
from ._errors import APIError, AuthenticationError, PlanLimitError, RateLimitError


class BaseClient:
    """Shared HTTP logic for sync and async clients."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.max_retries = max_retries
        self.timeout = timeout

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"sidclaw-python/{SDK_VERSION}",
        }

    def _should_retry(self, status_code: int, attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False
        return status_code >= 500 or status_code == 429

    def _get_retry_delay(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
        delay = (2**attempt) * 0.5
        jitter = random.uniform(0.5, 1.5)  # noqa: S311
        return delay * jitter

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Parse error response and raise appropriate exception."""
        request_id = response.headers.get("x-request-id")

        try:
            body = response.json()
        except Exception:
            body = {"error": "unknown", "message": f"HTTP {response.status_code}", "status": response.status_code}

        status = response.status_code
        code = body.get("error", "unknown")
        message = body.get("message", f"HTTP {status}")
        details = body.get("details", {})

        if status == 401:
            raise AuthenticationError(message, request_id=request_id)
        elif status == 429:
            retry_after = float(response.headers.get("Retry-After", "60"))
            raise RateLimitError(message, retry_after=retry_after, request_id=request_id)
        elif status == 402:
            raise PlanLimitError(
                details.get("limit", "unknown"),
                details.get("current", 0),
                details.get("max", 0),
                request_id=request_id,
            )
        else:
            raise APIError(message, status_code=status, code=code, request_id=request_id)
