from __future__ import annotations

import time
from typing import Any

import anyio
import httpx

from ._base_client import BaseClient
from ._constants import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT
from ._errors import ApprovalExpiredError, ApprovalTimeoutError
from ._types import (
    ApprovalStatusResponse,
    EvaluateParams,
    EvaluateResponse,
    RecordOutcomeParams,
    WaitForApprovalOptions,
)


class SidClaw(BaseClient):
    """Synchronous SidClaw client."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            agent_id=agent_id,
            max_retries=max_retries,
            timeout=timeout,
        )
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=self._build_headers(),
            timeout=self.timeout,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> SidClaw:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> httpx.Response:
        last_response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._http.request(method, path, json=json)
                if response.is_success:
                    return response
                last_response = response
                if not self._should_retry(response.status_code, attempt):
                    self._handle_error_response(response)
                last_error = Exception(f"HTTP {response.status_code}")
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
                if attempt >= self.max_retries:
                    raise
            except Exception:
                raise

            delay = self._get_retry_delay(attempt, last_response)
            time.sleep(delay)

        if last_response is not None:
            self._handle_error_response(last_response)
        raise last_error or Exception("Request failed after retries")

    def evaluate(self, params: EvaluateParams) -> EvaluateResponse:
        """Evaluate an action against the policy engine."""
        body: dict[str, Any] = {"agent_id": self.agent_id, **params}
        response = self._request("POST", "/api/v1/evaluate", json=body)
        return EvaluateResponse.model_validate(response.json())

    def wait_for_approval(
        self,
        approval_request_id: str,
        options: WaitForApprovalOptions | None = None,
    ) -> ApprovalStatusResponse:
        """Poll for approval status until decided or timeout."""
        opts = options or {}
        timeout = opts.get("timeout", 300)
        poll_interval = opts.get("poll_interval", 2)
        start = time.monotonic()

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                raise ApprovalTimeoutError(approval_request_id, "unknown", timeout)

            response = self._request("GET", f"/api/v1/approvals/{approval_request_id}/status")
            status = ApprovalStatusResponse.model_validate(response.json())

            if status.status in ("approved", "denied"):
                return status
            if status.status == "expired":
                raise ApprovalExpiredError(approval_request_id, "unknown")

            time.sleep(poll_interval)

    def record_outcome(self, trace_id: str, params: RecordOutcomeParams) -> None:
        """Record the outcome of an action after execution."""
        self._request("POST", f"/api/v1/traces/{trace_id}/outcome", json=dict(params))


class AsyncSidClaw(BaseClient):
    """Asynchronous SidClaw client."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            agent_id=agent_id,
            max_retries=max_retries,
            timeout=timeout,
        )
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._build_headers(),
            timeout=self.timeout,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncSidClaw:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> httpx.Response:
        last_response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._http.request(method, path, json=json)
                if response.is_success:
                    return response
                last_response = response
                if not self._should_retry(response.status_code, attempt):
                    self._handle_error_response(response)
                last_error = Exception(f"HTTP {response.status_code}")
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
                if attempt >= self.max_retries:
                    raise
            except Exception:
                raise

            delay = self._get_retry_delay(attempt, last_response)
            await anyio.sleep(delay)

        if last_response is not None:
            self._handle_error_response(last_response)
        raise last_error or Exception("Request failed after retries")

    async def evaluate(self, params: EvaluateParams) -> EvaluateResponse:
        """Evaluate an action against the policy engine."""
        body: dict[str, Any] = {"agent_id": self.agent_id, **params}
        response = await self._request("POST", "/api/v1/evaluate", json=body)
        return EvaluateResponse.model_validate(response.json())

    async def wait_for_approval(
        self,
        approval_request_id: str,
        options: WaitForApprovalOptions | None = None,
    ) -> ApprovalStatusResponse:
        """Poll for approval status until decided or timeout."""
        opts = options or {}
        timeout = opts.get("timeout", 300)
        poll_interval = opts.get("poll_interval", 2)
        start = time.monotonic()

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                raise ApprovalTimeoutError(approval_request_id, "unknown", timeout)

            response = await self._request("GET", f"/api/v1/approvals/{approval_request_id}/status")
            status = ApprovalStatusResponse.model_validate(response.json())

            if status.status in ("approved", "denied"):
                return status
            if status.status == "expired":
                raise ApprovalExpiredError(approval_request_id, "unknown")

            await anyio.sleep(poll_interval)

    async def record_outcome(self, trace_id: str, params: RecordOutcomeParams) -> None:
        """Record the outcome of an action after execution."""
        await self._request("POST", f"/api/v1/traces/{trace_id}/outcome", json=dict(params))
