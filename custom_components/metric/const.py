"""Constants for the Metric integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "metric"
LOGGER = logging.getLogger(__package__)

TENANT: Final = "redtapp"
BASE_URL: Final = "https://metric-app.com"
API_URL: Final = f"{BASE_URL}/openapi/v1"
OAUTH2_AUTHORIZE: Final = f"{BASE_URL}/auth/{TENANT}/authorize"
OAUTH2_TOKEN: Final = f"{BASE_URL}/auth/{TENANT}/token"
OAUTH2_REVOKE: Final = f"{BASE_URL}/auth/{TENANT}/revoke"

# Public OAuth client: no secret, PKCE is used instead.
OAUTH2_CLIENT_ID: Final = "home-assistant"

MANUFACTURER: Final = "Redtapp"

# Tank level changes slowly.
UPDATE_INTERVAL: Final = timedelta(minutes=5)
