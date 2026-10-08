"""Tests for Metric entities."""

from __future__ import annotations

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.metric.const import API_URL, DOMAIN
from custom_components.metric.diagnostics import async_get_config_entry_diagnostics

from .conftest import DEVICE_ID, SetupIntegration, device_payload, telemetry_payload


@pytest.mark.usefixtures("mock_api")
async def test_sensors(
    hass: HomeAssistant,
    setup_integration: SetupIntegration,
    entity_registry: er.EntityRegistry,
) -> None:
    """Each tank exposes its level, analytics and diagnostics."""
    await setup_integration()

    expected = {
        "sensor.casa_gas_level": ("42.5", "%"),
        "sensor.casa_remaining_gas": ("127.5", "L"),
        "sensor.casa_average_daily_consumption": ("3.25", "L/d"),
        "sensor.casa_estimated_run_out": ("2026-11-15T00:00:00+00:00", None),
        "sensor.casa_tank_size": ("300.0", "L"),
        "sensor.casa_last_reading": ("2026-10-08T12:00:00+00:00", None),
        "sensor.casa_battery_voltage": ("3.712", "V"),
        "sensor.casa_temperature": ("24.5", "°C"),
    }
    for entity_id, (state, unit) in expected.items():
        current = hass.states.get(entity_id)
        assert current is not None, entity_id
        assert current.state == state, entity_id
        assert current.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == unit, entity_id

    rssi = entity_registry.async_get("sensor.casa_signal_strength")
    assert rssi is not None
    assert rssi.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert rssi.unique_id == f"{DEVICE_ID}_wifi_rssi"


@pytest.mark.usefixtures("mock_api")
async def test_device_info(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Each tank is one device."""
    await setup_integration()

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), config_entry.entry_id
    )
    assert device is not None
    assert device.name == "Casa"
    assert device.manufacturer == "Redtapp"
    assert device.hw_version == "c3-v2"
    assert device.sw_version == "2.1.0"
    assert device.serial_number == DEVICE_ID


@pytest.mark.parametrize(
    ("percentage", "low", "expected"),
    [(15, 20, STATE_ON), (20, 20, STATE_ON), (21, 20, STATE_OFF), (15, None, STATE_UNKNOWN)],
)
async def test_low_gas(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    percentage: float,
    low: float | None,
    expected: str,
) -> None:
    """Low gas follows the alert threshold set in the Metric app."""
    aioclient_mock.get(
        f"{API_URL}/devices",
        json={"devices": [device_payload(percentage=percentage, alerts={"low": low})]},
    )
    aioclient_mock.get(f"{API_URL}/devices/{DEVICE_ID}/telemetry/latest", json=telemetry_payload())

    await setup_integration()

    assert hass.states.get("binary_sensor.casa_low_gas").state == expected


@pytest.mark.parametrize(
    ("battery", "expected"), [(3712, "3.712"), (3.7, "3.7"), (None, STATE_UNKNOWN)]
)
async def test_battery_voltage_units(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    battery: float | None,
    expected: str,
) -> None:
    """v2 firmware reports millivolts and legacy firmware volts; both show volts."""
    aioclient_mock.get(f"{API_URL}/devices", json={"devices": [device_payload()]})
    aioclient_mock.get(
        f"{API_URL}/devices/{DEVICE_ID}/telemetry/latest",
        json=telemetry_payload(battery=battery),
    )

    await setup_integration()

    assert hass.states.get("sensor.casa_battery_voltage").state == expected


async def test_missing_analytics(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Devices without enough history have unknown analytics."""
    aioclient_mock.get(
        f"{API_URL}/devices",
        json={
            "devices": [
                device_payload(
                    timeDataUpdated=None,
                    analytics={"averageConsumePerDay": None, "dateRunOutGas": None},
                )
            ]
        },
    )
    aioclient_mock.get(f"{API_URL}/devices/{DEVICE_ID}/telemetry/latest", json=telemetry_payload())

    await setup_integration()

    for entity_id in (
        "sensor.casa_average_daily_consumption",
        "sensor.casa_estimated_run_out",
        "sensor.casa_last_reading",
    ):
        assert hass.states.get(entity_id).state == STATE_UNKNOWN, entity_id


@pytest.mark.usefixtures("mock_api")
async def test_diagnostics_redact_secrets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    setup_integration: SetupIntegration,
) -> None:
    """Diagnostics never include tokens or the Wi-Fi network name."""
    await setup_integration()
    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["entry_data"]["token"] == "**REDACTED**"
    assert diagnostics["devices"][0]["wifi_network"] == "**REDACTED**"
    assert diagnostics["devices"][0]["percentage"] == 42.5
