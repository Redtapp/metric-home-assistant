"""The Metric integration."""

from __future__ import annotations

from aiohttp import ClientError, ClientTimeout
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow, config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType

from .api import AsyncConfigEntryAuth, MetricOAuth2Implementation
from .client import MetricClient
from .const import DOMAIN, LOGGER, OAUTH2_CLIENT_ID, OAUTH2_REVOKE
from .coordinator import MetricConfigEntry, MetricCoordinator, MetricRuntimeData

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Metric OAuth implementation used to refresh tokens."""
    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN, MetricOAuth2Implementation(hass)
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MetricConfigEntry) -> bool:
    """Set up Metric from a config entry."""
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    oauth_session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    client = MetricClient(AsyncConfigEntryAuth(async_get_clientsession(hass), oauth_session))

    coordinator = MetricCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = MetricRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MetricConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: MetricConfigEntry) -> None:
    """Revoke the refresh token so a removed entry can't keep reading the account."""
    refresh_token = entry.data.get("token", {}).get("refresh_token")
    if not refresh_token:
        return

    try:
        async with async_get_clientsession(hass).post(
            OAUTH2_REVOKE,
            data={
                "token": refresh_token,
                "token_type_hint": "refresh_token",
                "client_id": OAUTH2_CLIENT_ID,
            },
            timeout=ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                LOGGER.warning("Metric did not revoke the token (HTTP %s)", response.status)
    except (ClientError, TimeoutError) as err:
        LOGGER.warning("Could not revoke the Metric token: %s", err)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: MetricConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Allow removing a device that is no longer in the account."""
    devices = entry.runtime_data.coordinator.data
    return not any(
        identifier[0] == DOMAIN and identifier[1] in devices
        for identifier in device_entry.identifiers
    )
