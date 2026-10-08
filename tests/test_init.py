"""Tests for Metric setup, polling and token handling."""

from __future__ import annotations

from http import HTTPStatus
import time

from aiohttp import ClientError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.metric import async_remove_config_entry_device
from custom_components.metric.const import (
    API_URL,
    DOMAIN,
    OAUTH2_REVOKE,
    OAUTH2_TOKEN,
    UPDATE_INTERVAL,
)

from .conftest import (
    DEVICE_ID,
    USER_ID,
    SetupIntegration,
    device_payload,
    make_access_token,
    telemetry_payload,
)


@pytest.mark.usefixtures("mock_api")
async def test_setup_and_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: SetupIntegration
) -> None:
    """The entry loads and unloads."""
    await setup_integration()
    assert config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_remove_entry_revokes_refresh_token(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """Removing the entry revokes its refresh token with the public client."""
    mock_api.post(OAUTH2_REVOKE)
    await setup_integration()

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    revoke_calls = [call for call in mock_api.mock_calls if str(call[1]) == OAUTH2_REVOKE]
    assert len(revoke_calls) == 1
    assert revoke_calls[0][2] == {
        "token": f"{USER_ID}:refresh",
        "token_type_hint": "refresh_token",
        "client_id": "home-assistant",
    }


@pytest.mark.parametrize("revoke_status", [HTTPStatus.INTERNAL_SERVER_ERROR, None])
async def test_remove_entry_survives_failed_revoke(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
    revoke_status: HTTPStatus | None,
) -> None:
    """A failed or unreachable revoke still removes the entry."""
    if revoke_status is None:
        mock_api.post(OAUTH2_REVOKE, exc=ClientError())
    else:
        mock_api.post(OAUTH2_REVOKE, status=revoke_status)
    await setup_integration()

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(config_entry.entry_id) is None


async def test_requests_use_bearer_token(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """API requests carry the stored access token."""
    await setup_integration()

    for _method, _url, _data, headers in mock_api.mock_calls:
        assert headers["Authorization"] == f"Bearer {config_entry.data['token']['access_token']}"


async def test_unauthorized_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """A rejected token puts the entry into reauth."""
    aioclient_mock.get(f"{API_URL}/devices", status=HTTPStatus.UNAUTHORIZED)

    await setup_integration()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


@pytest.mark.parametrize("status", [HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.TOO_MANY_REQUESTS])
async def test_server_error_retries_setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
    status: HTTPStatus,
) -> None:
    """Server errors and rate limiting retry setup later."""
    aioclient_mock.get(f"{API_URL}/devices", status=status)

    await setup_integration()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize("token_expires_at", [time.time() - 60])
async def test_expired_token_is_refreshed(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """An expired access token is refreshed with the public client before polling."""
    new_token = make_access_token()
    mock_api.post(
        OAUTH2_TOKEN,
        json={
            "access_token": new_token,
            "refresh_token": f"{USER_ID}:rotated",
            "token_type": "Bearer",
            "expires_in": 86400,
        },
    )

    await setup_integration()

    assert config_entry.state is ConfigEntryState.LOADED
    refresh_request = mock_api.mock_calls[0][2]
    assert refresh_request["grant_type"] == "refresh_token"
    assert refresh_request["client_id"] == "home-assistant"
    assert config_entry.data["token"]["refresh_token"] == f"{USER_ID}:rotated"


@pytest.mark.parametrize("token_expires_at", [time.time() - 60])
async def test_rejected_refresh_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """A revoked refresh token puts the entry into reauth."""
    aioclient_mock.post(OAUTH2_TOKEN, status=HTTPStatus.BAD_REQUEST)

    await setup_integration()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_device_without_telemetry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """A device that never reported telemetry still loads."""
    aioclient_mock.get(f"{API_URL}/devices", json={"devices": [device_payload()]})
    aioclient_mock.get(
        f"{API_URL}/devices/{DEVICE_ID}/telemetry/latest", status=HTTPStatus.NOT_FOUND
    )

    await setup_integration()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.casa_battery_voltage").state == "unknown"
    assert hass.states.get("sensor.casa_gas_level").state == "42.5"


async def test_new_and_removed_devices(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
    device_registry: dr.DeviceRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Devices added to the account appear; removed ones become unavailable and removable."""
    aioclient_mock.get(f"{API_URL}/devices", json={"devices": [device_payload()]})
    aioclient_mock.get(f"{API_URL}/devices/{DEVICE_ID}/telemetry/latest", json=telemetry_payload())
    await setup_integration()
    assert hass.states.get("sensor.cabana_gas_level") is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{API_URL}/devices",
        json={"devices": [device_payload("112233445566", name="Cabaña", percentage=80)]},
    )
    aioclient_mock.get(f"{API_URL}/devices/112233445566/telemetry/latest", json=telemetry_payload())
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get("sensor.cabana_gas_level").state == "80.0"
    assert hass.states.get("sensor.casa_gas_level").state == "unavailable"

    old_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), config_entry.entry_id
    )
    new_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, "112233445566"), config_entry.entry_id
    )
    assert old_device is not None and new_device is not None

    assert await async_remove_device(hass, old_device.id, config_entry.entry_id)
    assert not await async_remove_device(hass, new_device.id, config_entry.entry_id)


async def async_remove_device(hass: HomeAssistant, device_id: str, entry_id: str) -> bool:
    """Ask the integration whether a device can be removed."""
    entry = hass.config_entries.async_get_entry(entry_id)
    device = dr.async_get(hass).async_get(device_id)
    assert entry is not None and device is not None
    return await async_remove_config_entry_device(hass, entry, device)
