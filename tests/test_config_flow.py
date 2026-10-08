"""Tests for the Metric config flow."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.metric.const import (
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_CLIENT_ID,
    OAUTH2_TOKEN,
)

from .conftest import EMAIL, USER_ID, SetupIntegration, make_access_token

REDIRECT_URI = config_entry_oauth2_flow.MY_AUTH_CALLBACK_PATH

pytestmark = pytest.mark.usefixtures("current_request_with_host")


@pytest.fixture(autouse=True)
async def setup_component(hass: HomeAssistant) -> None:
    """Register the OAuth implementation."""
    assert await async_setup_component(hass, DOMAIN, {})


async def _authorize(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    result: dict[str, Any],
    access_token: str,
) -> dict[str, Any]:
    """Complete the external OAuth step and return the next flow result."""
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    query = parse_qs(urlparse(result["url"]).query)
    state = config_entry_oauth2_flow._encode_jwt(
        hass, {"flow_id": result["flow_id"], "redirect_uri": REDIRECT_URI}
    )

    client = await hass_client_no_auth()
    response = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert response.status == 200

    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "access_token": access_token,
            "refresh_token": f"{USER_ID}:refresh",
            "token_type": "Bearer",
            "expires_in": 86400,
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    token_request = next(
        data for method, url, data, _ in aioclient_mock.mock_calls if str(url) == OAUTH2_TOKEN
    )
    assert token_request["client_id"] == OAUTH2_CLIENT_ID
    assert "client_secret" not in token_request or not token_request["client_secret"]
    assert len(token_request["code_verifier"]) == 128
    assert query["code_challenge_method"] == ["S256"]
    return result


async def test_full_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Signing in creates an entry keyed by the Metric user ID.

    The `my` integration isn't loaded here, which is when Home Assistant would
    otherwise fall back to the instance's own callback URL.
    """
    assert "my" not in hass.config.components
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["url"].startswith(f"{OAUTH2_AUTHORIZE}?")
    query = parse_qs(urlparse(result["url"]).query)
    assert query["client_id"] == [OAUTH2_CLIENT_ID]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [REDIRECT_URI]

    result = await _authorize(
        hass, hass_client_no_auth, aioclient_mock, result, make_access_token()
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == EMAIL
    assert result["result"].unique_id == USER_ID
    assert result["data"]["auth_implementation"] == DOMAIN
    assert result["data"]["token"]["refresh_token"] == f"{USER_ID}:refresh"


async def test_each_flow_uses_a_new_code_verifier(hass: HomeAssistant) -> None:
    """Two sign-ins never share a PKCE challenge."""
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    second = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    def challenge(result: dict[str, Any]) -> str:
        return parse_qs(urlparse(result["url"]).query)["code_challenge"][0]

    assert challenge(first) != challenge(second)


async def test_title_falls_back_without_email(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Accounts that signed up by phone get a generic title."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await _authorize(
        hass, hass_client_no_auth, aioclient_mock, result, make_access_token(email=None)
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Metric"


async def test_already_configured(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """The same account can't be added twice."""
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await _authorize(
        hass, hass_client_no_auth, aioclient_mock, result, make_access_token()
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_invalid_token(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A token that isn't a JWT aborts the flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await _authorize(hass, hass_client_no_auth, aioclient_mock, result, "not-a-jwt")

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_token"


@pytest.mark.usefixtures("mock_api")
async def test_reauth(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """Reauth replaces the stored token."""
    await setup_integration()

    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    new_token = make_access_token()
    result = await _authorize(hass, hass_client_no_auth, aioclient_mock, result, new_token)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["token"]["access_token"] == new_token
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_api")
async def test_reauth_wrong_account(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """Reauth with a different account is rejected."""
    await setup_integration()
    original_token = config_entry.data["token"]["access_token"]

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await _authorize(
        hass,
        hass_client_no_auth,
        aioclient_mock,
        result,
        make_access_token(user_id="01JOTHER000000000000000000"),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert config_entry.data["token"]["access_token"] == original_token
