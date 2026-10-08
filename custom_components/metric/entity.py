"""Base entity for Metric."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import Device
from .const import DOMAIN, MANUFACTURER
from .coordinator import MetricConfigEntry, MetricCoordinator


class MetricEntity(CoordinatorEntity[MetricCoordinator]):
    """An entity belonging to one Metric tank sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MetricCoordinator,
        device_id: str,
        description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{description.key}"
        device = self.device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            model="Gas tank sensor",
            hw_version=device.hardware_version,
            sw_version=device.software_version,
            name=device.name,
            serial_number=device_id,
        )

    @property
    def device(self) -> Device:
        """Return the latest data for this entity's device."""
        return self.coordinator.data[self.device_id]

    @property
    def available(self) -> bool:
        """Return if the device is still in the account."""
        return super().available and self.device_id in self.coordinator.data


def async_add_device_entities(
    entry: MetricConfigEntry,
    async_add_entities: Callable[[Iterable[Entity]], None],
    create_entities: Callable[[str], Iterable[Entity]],
) -> None:
    """Add entities for current devices and for devices added to the account later."""
    coordinator = entry.runtime_data.coordinator
    known_devices: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        new_devices = set(coordinator.data) - known_devices
        if not new_devices:
            return
        known_devices.update(new_devices)
        async_add_entities(
            entity for device_id in new_devices for entity in create_entities(device_id)
        )

    _add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))
