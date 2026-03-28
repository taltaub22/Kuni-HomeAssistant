"""Data update coordinator for Kuni."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KuniApi

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


class KuniDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Pulls one device's state periodically (one coordinator per physical device)."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: KuniApi,
        entry: ConfigEntry,
        *,
        device_id: str,
        default_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"kuni_{device_id[:8]}",
            update_interval=SCAN_INTERVAL,
        )
        self.api = api
        self.config_entry = entry
        self.device_id = device_id
        self._default_name = default_name

    @property
    def device_name(self) -> str:
        if self.data and self.data.get("device_name"):
            return str(self.data["device_name"])
        return self._default_name

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_status(self.device_id)
        except Exception as err:
            raise UpdateFailed(f"Error talking to Kuni device: {err}") from err
