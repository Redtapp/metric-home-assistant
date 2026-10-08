"""Fixtures for Metric tests."""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
import json
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.metric.const import API_URL, DOMAIN

USER_ID = "01JUSER0000000000000000000"
EMAIL = "user@example.com"
DEVICE_ID = "AABBCCDDEEFF"


def make_access_token(user_id: str = USER_ID, email: str | None = EMAIL) -> str:
    """Build an unsigned access token for tests."""

    def encode(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    identities = [{"type": "email", "value": email}] if email else []
    claims = {
        "type": "user",
        "sub": user_id,
        "properties": {"id": user_id, "tenantID": "redtapp", "identities": identities},
    }
    return f"{encode({'alg': 'none'})}.{encode(claims)}.signature"


def device_payload(device_id: str = DEVICE_ID, **overrides: Any) -> dict[str, Any]:
    """Return a device as served by `/openapi/v1/devices`."""
    return {
        "id": device_id,
        "name": "Casa",
        "percentage": 42.5,
        "tankSize": 300,
        "hardwareVersion": "c3-v2",
        "softwareVersion": "2.1.0",
        "wifiNetwork": "HomeWifi",
        "wifiRssi": -61,
        "timeCreated": "2026-01-01T00:00:00.000Z",
        "timeDataUpdated": "2026-10-08T12:00:00.000Z",
        "analytics": {
            "averageConsumePerDay": 3.25,
            "dateRunOutGas": "2026-11-15T00:00:00.000Z",
        },
        "alerts": {"low": 20},
    } | overrides


def telemetry_payload(**overrides: Any) -> dict[str, Any]:
    """Return a sample as served by `/telemetry/latest`."""
    return {
        "percentage": 42.5,
        "battery": 3712,
        "temp": 24.5,
        "source": "v2",
        "timeCreated": "2026-10-08T12:00:00.000Z",
    } | overrides


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the integration from custom_components."""


@pytest.fixture
def token_expires_at() -> float:
    """Expiry of the stored access token."""
    return time.time() + 3600


@pytest.fixture
def config_entry(token_expires_at: float) -> MockConfigEntry:
    """A config entry for a signed-in account."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=USER_ID,
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": make_access_token(),
                "refresh_token": f"{USER_ID}:refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
                "expires_at": token_expires_at,
            },
        },
    )


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Serve one device with telemetry."""
    aioclient_mock.get(f"{API_URL}/devices", json={"devices": [device_payload()]})
    aioclient_mock.get(f"{API_URL}/devices/{DEVICE_ID}/telemetry/latest", json=telemetry_payload())
    return aioclient_mock


type SetupIntegration = Callable[[], Awaitable[None]]


@pytest.fixture
def setup_integration(hass: HomeAssistant, config_entry: MockConfigEntry) -> SetupIntegration:
    """Add the config entry and set up the integration."""

    async def _setup() -> None:
        config_entry.add_to_hass(hass)
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

    return _setup
