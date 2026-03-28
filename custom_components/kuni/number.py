"""Kuni intensity number entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KuniDataUpdateCoordinator

ENTITY_DESCRIPTION = NumberEntityDescription(
    key="intensity",
    translation_key="intensity",
    native_min_value=1,
    native_max_value=6,
    native_step=1,
    mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add intensity entity for each discovered device."""
    coordinators: dict[str, KuniDataUpdateCoordinator] = hass.data[DOMAIN][
        entry.entry_id
    ]["coordinators"]
    async_add_entities(
        [KuniIntensityNumber(c, ENTITY_DESCRIPTION) for c in coordinators.values()]
    )


class KuniIntensityNumber(
    CoordinatorEntity[KuniDataUpdateCoordinator], NumberEntity
):
    """Intensity from device shadow, written via shadow/update."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KuniDataUpdateCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_"
            f"{coordinator.device_id}_{description.key}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_id)},
            name=self.coordinator.device_name,
            manufacturer="Kuni",
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get("intensity")
        if raw is None:
            return None
        try:
            v = int(round(float(raw)))
        except (TypeError, ValueError):
            return None
        lo = int(self.entity_description.native_min_value)
        hi = int(self.entity_description.native_max_value)
        return float(max(lo, min(v, hi)))

    async def async_set_native_value(self, value: float) -> None:
        lo = int(self.entity_description.native_min_value)
        hi = int(self.entity_description.native_max_value)
        sent = max(lo, min(int(round(value)), hi))
        await self.coordinator.api.async_set_intensity(
            self.coordinator.device_id, sent
        )
        await self.coordinator.async_request_refresh()
