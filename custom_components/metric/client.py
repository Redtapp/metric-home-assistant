"""Client for the Metric public integrations API.

This module has no Home Assistant imports so it can be extracted into a
standalone PyPI package if the integration is ever submitted to core.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
import json
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout

REQUEST_TIMEOUT = ClientTimeout(total=30)

# v2 firmware reports battery in millivolts, legacy firmware in volts.
MILLIVOLT_THRESHOLD = 100


class MetricError(Exception):
    """Base error for the Metric API."""


class MetricAuthError(MetricError):
    """The access token was rejected."""


class MetricConnectionError(MetricError):
    """The API could not be reached or returned a server error."""


class MetricNotFoundError(MetricError):
    """The requested resource does not exist."""


@dataclass(frozen=True, slots=True)
class Account:
    """The Metric account an access token belongs to."""

    id: str
    email: str | None


@dataclass(frozen=True, slots=True)
class Telemetry:
    """Latest raw sample reported by a device."""

    percentage: float
    battery_voltage: float | None
    temperature: float | None
    time: datetime


@dataclass(frozen=True, slots=True)
class Device:
    """A gas tank sensor."""

    id: str
    name: str
    percentage: float
    tank_size: float
    hardware_version: str
    software_version: str
    wifi_network: str | None
    wifi_rssi: int | None
    time_data_updated: datetime | None
    average_consumption_per_day: float | None
    date_run_out: datetime | None
    low_alert_threshold: float | None
    telemetry: Telemetry | None

    @property
    def remaining_gas(self) -> float:
        """Gas left in the tank, in liters."""
        return round(self.tank_size * self.percentage / 100, 1)

    @property
    def is_low(self) -> bool | None:
        """Whether the level is at or below the user's low-gas alert."""
        if self.low_alert_threshold is None:
            return None
        return self.percentage <= self.low_alert_threshold


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _battery_voltage(value: Any) -> float | None:
    battery = _parse_float(value)
    if battery is None:
        return None
    if battery > MILLIVOLT_THRESHOLD:
        battery /= 1000
    return round(battery, 3)


def parse_telemetry(data: dict[str, Any]) -> Telemetry:
    """Parse a `/telemetry/latest` response."""
    return Telemetry(
        percentage=float(data["percentage"]),
        battery_voltage=_battery_voltage(data.get("battery")),
        temperature=_parse_float(data.get("temp")),
        time=datetime.fromisoformat(data["timeCreated"]),
    )


def parse_device(data: dict[str, Any], telemetry: Telemetry | None) -> Device:
    """Parse a device from the `/devices` response."""
    analytics = data.get("analytics") or {}
    alerts = data.get("alerts") or {}
    rssi = _parse_float(data.get("wifiRssi"))
    return Device(
        id=data["id"],
        name=data["name"],
        percentage=float(data["percentage"]),
        tank_size=float(data["tankSize"]),
        hardware_version=data["hardwareVersion"],
        software_version=data["softwareVersion"],
        wifi_network=data.get("wifiNetwork"),
        wifi_rssi=int(rssi) if rssi is not None else None,
        time_data_updated=_parse_datetime(data.get("timeDataUpdated")),
        average_consumption_per_day=_parse_float(analytics.get("averageConsumePerDay")),
        date_run_out=_parse_datetime(analytics.get("dateRunOutGas")),
        low_alert_threshold=_parse_float(alerts.get("low")),
        telemetry=telemetry,
    )


def account_from_access_token(access_token: str) -> Account:
    """Read the account from the access token's claims.

    The token is not verified here; the API verifies it on every request.
    """
    try:
        payload = access_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        user_id = claims["sub"]
    except (IndexError, KeyError, TypeError, ValueError) as err:
        raise MetricAuthError("Access token is not a valid JWT") from err

    identities = (claims.get("properties") or {}).get("identities") or []
    email = next(
        (
            identity.get("value")
            for identity in identities
            if isinstance(identity, dict) and identity.get("type") == "email"
        ),
        None,
    )
    return Account(id=str(user_id), email=email)


class AbstractAuth(ABC):
    """Makes authenticated requests to the Metric API."""

    def __init__(self, session: ClientSession, host: str) -> None:
        """Initialize the auth."""
        self._session = session
        self._host = host.rstrip("/")

    @abstractmethod
    async def async_get_access_token(self) -> str:
        """Return a valid access token."""

    async def get(self, path: str) -> Any:
        """Make a GET request and return the decoded JSON body."""
        access_token = await self.async_get_access_token()
        try:
            async with self._session.get(
                f"{self._host}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == HTTPStatus.UNAUTHORIZED:
                    raise MetricAuthError("Access token was rejected")
                if response.status == HTTPStatus.NOT_FOUND:
                    raise MetricNotFoundError(path)
                if response.status >= HTTPStatus.BAD_REQUEST:
                    raise MetricConnectionError(
                        f"Metric API returned HTTP {response.status} for {path}"
                    )
                return await response.json()
        except (ClientError, TimeoutError) as err:
            raise MetricConnectionError(f"Error requesting {path}: {err}") from err


class MetricClient:
    """Reads devices and telemetry from the Metric API."""

    def __init__(self, auth: AbstractAuth) -> None:
        """Initialize the client."""
        self._auth = auth

    async def async_get_latest_telemetry(self, device_id: str) -> Telemetry | None:
        """Return the latest telemetry sample, or None if there is none yet."""
        try:
            data = await self._auth.get(f"/devices/{quote(device_id, safe='')}/telemetry/latest")
        except MetricNotFoundError:
            return None
        return parse_telemetry(data)

    async def async_get_devices(self) -> dict[str, Device]:
        """Return all devices owned by the account, keyed by device ID."""
        data = await self._auth.get("/devices")
        raw_devices: list[dict[str, Any]] = data["devices"]
        telemetry = await asyncio.gather(
            *(self.async_get_latest_telemetry(device["id"]) for device in raw_devices)
        )
        return {
            device["id"]: parse_device(device, sample)
            for device, sample in zip(raw_devices, telemetry, strict=True)
        }
