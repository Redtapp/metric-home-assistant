"""Data update coordinator for Metric."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import Device, MetricAuthError, MetricClient, MetricError
from .const import DOMAIN, LOGGER, UPDATE_INTERVAL


@dataclass
class MetricRuntimeData:
    """Runtime data stored on the config entry."""

    client: MetricClient
    coordinator: MetricCoordinator


type MetricConfigEntry = ConfigEntry[MetricRuntimeData]


class MetricCoordinator(DataUpdateCoordinator[dict[str, Device]]):
    """Polls all devices of a Metric account."""

    config_entry: MetricConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: MetricConfigEntry, client: MetricClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Device]:
        try:
            return await self.client.async_get_devices()
        except MetricAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except MetricError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
