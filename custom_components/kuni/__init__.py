"""The Kuni integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KuniApi, device_display_label, device_entry_id
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    KUNI_API_BASE_URL,
    KUNI_ORGANIZATION_ID,
    PLATFORMS,
)
from .coordinator import KuniDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kuni: one coordinator per device returned by GET /devices/."""
    data = entry.data

    required = (CONF_ACCESS_TOKEN, CONF_ID_TOKEN)
    if not all(k in data for k in required):
        _LOGGER.error("Kuni config entry is missing required keys")
        return False

    session = async_get_clientsession(hass)
    refresh = data.get(CONF_REFRESH_TOKEN) or None
    api = KuniApi(
        session,
        base_url=KUNI_API_BASE_URL,
        organization_id=KUNI_ORGANIZATION_ID,
        access_token=data[CONF_ACCESS_TOKEN],
        id_token=data[CONF_ID_TOKEN],
        refresh_token=refresh.strip() if refresh else None,
    )

    try:
        await api.async_ensure_tokens()
    except Exception:
        _LOGGER.exception("Could not obtain API tokens")
        return False

    if not api.has_valid_tokens():
        _LOGGER.error("Kuni integration has no valid access tokens")
        return False

    try:
        device_rows = await api.async_list_devices()
    except Exception:
        _LOGGER.exception("Could not list Kuni devices")
        return False

    if not device_rows:
        _LOGGER.error("No Kuni devices returned for this account")
        return False

    coordinators: dict[str, KuniDataUpdateCoordinator] = {}
    for row in device_rows:
        did = device_entry_id(row)
        if not did:
            continue
        coordinators[did] = KuniDataUpdateCoordinator(
            hass,
            api,
            entry,
            device_id=did,
            default_name=device_display_label(row),
        )

    if not coordinators:
        _LOGGER.error("No valid device ids in Kuni device list")
        return False

    refresh_tasks = [
        c.async_config_entry_first_refresh() for c in coordinators.values()
    ]
    results = await asyncio.gather(*refresh_tasks, return_exceptions=True)
    for coord, res in zip(coordinators.values(), results, strict=True):
        if isinstance(res, Exception):
            _LOGGER.warning(
                "Kuni device %s initial refresh failed: %s",
                coord.device_id,
                res,
            )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinators": coordinators}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Kuni config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
