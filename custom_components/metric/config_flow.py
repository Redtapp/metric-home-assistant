"""Config flow for Metric."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow

from .api import MetricOAuth2Implementation
from .client import MetricAuthError, account_from_access_token
from .const import DOMAIN, LOGGER


class MetricFlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Sign in to a Metric account with OAuth2."""

    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return LOGGER

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Start sign-in with a fresh PKCE verifier."""
        self.flow_impl = MetricOAuth2Implementation(self.hass)
        return await self.async_step_auth()

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication when the refresh token is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to sign in again."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create or update the entry for the signed-in account."""
        try:
            account = account_from_access_token(data["token"]["access_token"])
        except MetricAuthError:
            return self.async_abort(reason="invalid_token")

        await self.async_set_unique_id(account.id)
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)

        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=account.email or "Metric", data=data)
