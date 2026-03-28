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

from .const import (
    DOMAIN,
    INTENSITY_DEVICE_MAX,
    INTENSITY_DEVICE_MIN,
    entity_suggested_object_id,
)
from .coordinator import KuniDataUpdateCoordinator

# Device sends/receives 0..INTENSITY_DEVICE_MAX; Home Assistant shows 1..(max+1).
_INTENSITY_HA_MIN = INTENSITY_DEVICE_MIN + 1
_INTENSITY_HA_MAX = INTENSITY_DEVICE_MAX + 1

ENTITY_DESCRIPTION = NumberEntityDescription(
    key="intensity",
    translation_key="intensity",
    native_min_value=_INTENSITY_HA_MIN,
    native_max_value=_INTENSITY_HA_MAX,
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
            f"{DOMAIN}_{coordinator.config_entry.entry_id}_"
            f"{coordinator.device_id}_{description.key}"
        )

    @property
    def suggested_object_id(self) -> str:
        return entity_suggested_object_id(
            self.coordinator.device_id, self.entity_description.key
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_id)},
            name=self.coordinator.device_name,
            manufacturer="Kuni",
        )

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get("intensity")
        if raw is None:
            return None
        try:
            device_v = int(round(float(raw)))
        except (TypeError, ValueError):
            return None
        device_v = max(
            INTENSITY_DEVICE_MIN, min(device_v, INTENSITY_DEVICE_MAX)
        )
        return device_v + 1

    async def async_set_native_value(self, value: float) -> None:
        ha_v = max(
            _INTENSITY_HA_MIN,
            min(int(round(value)), _INTENSITY_HA_MAX),
        )
        device_v = ha_v - 1
        await self.coordinator.api.async_set_intensity(
            self.coordinator.device_id, device_v
        )
        await self.coordinator.async_request_refresh()
