"""Home Assistant glue for the Metric API client."""

from __future__ import annotations

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .client import AbstractAuth
from .const import API_URL, DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_CLIENT_ID, OAUTH2_TOKEN


class MetricOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce):
    """Metric as a public OAuth client.

    The PKCE verifier is generated per instance, so config flows create their
    own instance rather than reusing the registered one.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the implementation."""
        super().__init__(
            hass,
            DOMAIN,
            OAUTH2_CLIENT_ID,
            authorize_url=OAUTH2_AUTHORIZE,
            token_url=OAUTH2_TOKEN,
        )

    @property
    def name(self) -> str:
        """Name shown if the user has to pick an implementation."""
        return "Metric"

    @property
    def redirect_uri(self) -> str:
        """Always redirect through my.home-assistant.io.

        This is the redirect URI registered for the Metric client. Home
        Assistant would otherwise use `<instance>/auth/external/callback` when
        the `my` integration isn't loaded. The callback view is registered by
        the OAuth helper itself, so this works whether or not `my` is loaded.
        """
        return config_entry_oauth2_flow.MY_AUTH_CALLBACK_PATH


class AsyncConfigEntryAuth(AbstractAuth):
    """Provides Metric authentication tied to an OAuth2 config entry."""

    def __init__(
        self,
        session: ClientSession,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialize the auth."""
        super().__init__(session, API_URL)
        self._oauth_session = oauth_session

    async def async_get_access_token(self) -> str:
        """Return a valid access token, refreshing it if needed."""
        await self._oauth_session.async_ensure_token_valid()
        return str(self._oauth_session.token["access_token"])
