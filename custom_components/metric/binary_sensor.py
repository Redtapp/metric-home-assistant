"""Binary sensors for Metric gas tanks."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MetricConfigEntry
from .entity import MetricEntity, async_add_device_entities

# Coordinator handles all updates.
PARALLEL_UPDATES = 0

LOW_GAS = BinarySensorEntityDescription(
    key="low_gas",
    translation_key="low_gas",
    device_class=BinarySensorDeviceClass.PROBLEM,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MetricConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Metric binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda device_id: (MetricLowGasEntity(coordinator, device_id, LOW_GAS),),
    )


class MetricLowGasEntity(MetricEntity, BinarySensorEntity):
    """On when the level is at or below the low-gas alert set in the Metric app."""

    @property
    def is_on(self) -> bool | None:
        """Return if the tank is low."""
        return self.device.is_low
