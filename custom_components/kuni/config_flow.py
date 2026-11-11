"""Config flow for Kuni."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from aiohttp import ClientError, ClientResponseError

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KuniApi
from .cognito import KuniAuthError, build_cognito_username, sync_srp_authenticate
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_ID_TOKEN,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    KUNI_API_BASE_URL,
    KUNI_ORGANIZATION_ID,
)

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: dict[str, Any] | None) -> vol.Schema:
    defs = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_EMAIL,
                default=defs.get(CONF_EMAIL, ""),
            ): selector.TextSelector(),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.PASSWORD,
                    autocomplete="current-password",
                ),
            ),
        }
    )


def _entry_data(tokens: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_REFRESH_TOKEN: tokens.get("refresh_token") or "",
        CONF_ACCESS_TOKEN: tokens["access_token"],
        CONF_ID_TOKEN: tokens["id_token"],
    }


class KuniConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kuni."""

    VERSION = 1

    async def _async_authenticate(
        self, email: str, password: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Cognito login + device check. Returns (tokens, error_key)."""
        username = build_cognito_username(KUNI_ORGANIZATION_ID, email)
        try:
            tokens = await self.hass.async_add_executor_job(
                sync_srp_authenticate,
                username,
                password,
            )
        except KuniAuthError as err:
            if err.args and err.args[0] == "invalid_credentials":
                return None, "invalid_auth"
            return None, "cannot_connect"
        except RuntimeError:
            return None, "missing_dependency"
        except Exception:
            _LOGGER.exception("Unexpected error during Cognito login")
            return None, "cannot_connect"

        session = async_get_clientsession(self.hass)
        api = KuniApi(
            session,
            base_url=KUNI_API_BASE_URL,
            organization_id=KUNI_ORGANIZATION_ID,
            access_token=tokens["access_token"],
            id_token=tokens["id_token"],
            refresh_token=tokens.get("refresh_token") or None,
        )
        try:
            devices = await api.async_list_devices()
        except (ClientResponseError, ClientError, OSError):
            return None, "cannot_connect"
        if not devices:
            return None, "no_devices"
        return tokens, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cognito login; one entry loads every device returned by the API."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            tokens, error = await self._async_authenticate(
                email, user_input[CONF_PASSWORD]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(f"kuni_{KUNI_ORGANIZATION_ID}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Kuni",
                    data=_entry_data(tokens),
                )

        schema = _user_schema(user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Triggered when tokens expire; re-prompt for credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-authenticate and update the existing entry's tokens."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if user_input is not None and entry is not None:
            email = user_input[CONF_EMAIL].strip()
            tokens, error = await self._async_authenticate(
                email, user_input[CONF_PASSWORD]
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data=_entry_data(tokens)
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_user_schema(user_input),
            errors=errors,
        )
