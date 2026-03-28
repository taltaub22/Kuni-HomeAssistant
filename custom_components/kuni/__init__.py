"""The Kuni integration."""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import KuniApi, device_display_label, device_entry_id
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    KUNI_API_BASE_URL,
    KUNI_ORGANIZATION_ID,
    PLATFORMS,
    SERVICE_SET_TIMER,
    TIMER_MAX_SECONDS,
)
from .coordinator import KuniDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_SERVICES_FLAG = f"{DOMAIN}_services_done"

SET_TIMER_SCHEMA = vol.Schema(
    {
        vol.Required("duration_seconds"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=TIMER_MAX_SECONDS)
        ),
        vol.Optional("device_id"): cv.string,
    }
)


def _pick_target_ha_device_id(call: ServiceCall) -> str | None:
    if did := call.data.get("device_id"):
        return did
    target = getattr(call, "target", None)
    if target is None:
        return None
    dids = getattr(target, "device_ids", None)
    if dids:
        return next(iter(dids))
    single = getattr(target, "device_id", None)
    if isinstance(single, str) and single:
        return single
    if isinstance(target, dict):
        raw = target.get("device_id")
        if isinstance(raw, str) and raw:
            return raw
        if isinstance(raw, list) and raw:
            return raw[0]
    return None


def _hardware_uuid_from_ha_device(hass: HomeAssistant, ha_device_id: str) -> str:
    """Map Home Assistant device registry id → Kuni hardware UUID (identifier)."""
    dev_reg = dr.async_get(hass)
    dev = dev_reg.async_get(ha_device_id)
    if dev is None:
        raise ServiceValidationError(f"Unknown device: {ha_device_id}")
    for ident_domain, ident_value in dev.identifiers:
        if ident_domain == DOMAIN:
            return str(ident_value)
    raise ServiceValidationError("Selected device is not a Kuni device")


def _find_coordinator(
    hass: HomeAssistant, device_uuid: str
) -> KuniDataUpdateCoordinator | None:
    for payload in hass.data.get(DOMAIN, {}).values():
        if not isinstance(payload, dict):
            continue
        coords: dict[str, KuniDataUpdateCoordinator] | None = payload.get(
            "coordinators"
        )
        if coords and device_uuid in coords:
            return coords[device_uuid]
    return None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register Kuni services once (all config entries share the same API client pool)."""
    if hass.data.get(_SERVICES_FLAG):
        return True
    hass.data[_SERVICES_FLAG] = True

    async def async_set_timer(call: ServiceCall) -> None:
        ha_dev = _pick_target_ha_device_id(call)
        if not ha_dev:
            raise ServiceValidationError(
                "Select a Kuni device (Targets → Device or the Device field)"
            )
        device_uuid = _hardware_uuid_from_ha_device(hass, ha_dev)

        coord = _find_coordinator(hass, device_uuid)
        if coord is None:
            raise ServiceValidationError(
                "That Kuni device is not loaded; reload the integration or check login"
            )

        await coord.api.async_set_timer(device_uuid, call.data["duration_seconds"])
        await coord.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TIMER,
        async_set_timer,
        schema=SET_TIMER_SCHEMA,
    )
    return True


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
