"""Sensors for Metric gas tanks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import Device
from .coordinator import MetricConfigEntry
from .entity import MetricEntity, async_add_device_entities

# Coordinator handles all updates.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MetricSensorEntityDescription(SensorEntityDescription):
    """Describes a Metric sensor."""

    value_fn: Callable[[Device], float | int | datetime | None]


SENSORS: tuple[MetricSensorEntityDescription, ...] = (
    MetricSensorEntityDescription(
        key="level",
        translation_key="level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda device: device.percentage,
    ),
    MetricSensorEntityDescription(
        key="remaining_gas",
        translation_key="remaining_gas",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda device: device.remaining_gas,
    ),
    MetricSensorEntityDescription(
        key="average_consumption",
        translation_key="average_consumption",
        native_unit_of_measurement="L/d",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda device: device.average_consumption_per_day,
    ),
    MetricSensorEntityDescription(
        key="run_out_date",
        translation_key="run_out_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda device: device.date_run_out,
    ),
    MetricSensorEntityDescription(
        key="tank_size",
        translation_key="tank_size",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.tank_size,
    ),
    MetricSensorEntityDescription(
        key="last_reading",
        translation_key="last_reading",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.time_data_updated,
    ),
    MetricSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda device: device.telemetry.battery_voltage if device.telemetry else None,
    ),
    MetricSensorEntityDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda device: device.telemetry.temperature if device.telemetry else None,
    ),
    MetricSensorEntityDescription(
        key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.wifi_rssi,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MetricConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Metric sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda device_id: (
            MetricSensorEntity(coordinator, device_id, description) for description in SENSORS
        ),
    )


class MetricSensorEntity(MetricEntity, SensorEntity):
    """A Metric sensor."""

    entity_description: MetricSensorEntityDescription

    @property
    def native_value(self) -> float | int | datetime | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.device)
