import pytest
import respx

from sidclaw import AsyncSidClaw, SidClaw


@pytest.fixture
def client():
    return SidClaw(api_key="test-key", base_url="https://test.api", agent_id="test-agent", max_retries=0)


@pytest.fixture
def async_client():
    return AsyncSidClaw(api_key="test-key", base_url="https://test.api", agent_id="test-agent", max_retries=0)


@pytest.fixture
def retry_client():
    return SidClaw(api_key="test-key", base_url="https://test.api", agent_id="test-agent", max_retries=2)


@pytest.fixture
def mock_api():
    with respx.mock(base_url="https://test.api") as respx_mock:
        yield respx_mock
