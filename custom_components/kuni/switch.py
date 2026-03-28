"""Kuni power switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, entity_suggested_object_id
from .coordinator import KuniDataUpdateCoordinator

ENTITY_DESCRIPTION = SwitchEntityDescription(
    key="power",
    name="Power",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add power switch for each discovered device."""
    coordinators: dict[str, KuniDataUpdateCoordinator] = hass.data[DOMAIN][
        entry.entry_id
    ]["coordinators"]
    async_add_entities(
        [KuniPowerSwitch(c, ENTITY_DESCRIPTION) for c in coordinators.values()]
    )


class KuniPowerSwitch(CoordinatorEntity[KuniDataUpdateCoordinator], SwitchEntity):
    """Switch that turns the Kuni device on or off."""

    _attr_has_entity_name = True
    _attr_translation_key = "power"

    def __init__(
        self,
        coordinator: KuniDataUpdateCoordinator,
        description: SwitchEntityDescription,
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
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get("is_on")
        if raw is None:
            return None
        return bool(raw)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.api.async_set_power(self.coordinator.device_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.async_set_power(self.coordinator.device_id, False)
        await self.coordinator.async_request_refresh()
