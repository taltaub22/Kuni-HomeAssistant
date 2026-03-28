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


class KuniConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kuni."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cognito login; one entry loads every device returned by the API."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            username = build_cognito_username(KUNI_ORGANIZATION_ID, email)
            try:
                tokens = await self.hass.async_add_executor_job(
                    sync_srp_authenticate,
                    username,
                    user_input[CONF_PASSWORD],
                )
            except KuniAuthError as err:
                if err.args and err.args[0] == "invalid_credentials":
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except RuntimeError:
                errors["base"] = "missing_dependency"
            except Exception:
                _LOGGER.exception("Unexpected error during Cognito login")
                errors["base"] = "cannot_connect"
            else:
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
                except ClientResponseError:
                    errors["base"] = "cannot_connect"
                except ClientError:
                    errors["base"] = "cannot_connect"
                except OSError:
                    errors["base"] = "cannot_connect"
                else:
                    if not devices:
                        errors["base"] = "no_devices"
                    else:
                        await self.async_set_unique_id(
                            f"kuni_{KUNI_ORGANIZATION_ID}"
                        )
                        self._abort_if_unique_id_configured()
                        rt = tokens.get("refresh_token") or ""
                        return self.async_create_entry(
                            title="Kuni",
                            data={
                                CONF_REFRESH_TOKEN: rt,
                                CONF_ACCESS_TOKEN: tokens["access_token"],
                                CONF_ID_TOKEN: tokens["id_token"],
                            },
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
