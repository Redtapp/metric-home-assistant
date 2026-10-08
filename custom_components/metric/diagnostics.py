"""Diagnostics support for Metric."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import MetricConfigEntry

TO_REDACT = {"token", "wifi_network"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MetricConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "devices": [
            async_redact_data(asdict(device), TO_REDACT)
            for device in (coordinator.data or {}).values()
        ],
    }
