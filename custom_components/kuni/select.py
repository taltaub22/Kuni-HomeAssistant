"""Kuni active scent selector (shadow `position` → cartridge slot)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUM_SCENT_SLOTS
from .coordinator import KuniDataUpdateCoordinator


def _slot_options(slots: list) -> list[str]:
    """Stable, unique labels for the three physical slots."""
    opts: list[str] = []
    for idx in range(NUM_SCENT_SLOTS):
        row = slots[idx] if idx < len(slots) else {}
        name = row.get("name")
        label = str(name) if name else "Empty"
        opts.append(f"{label} · slot {idx + 1}")
    return opts


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add current-scent select per device."""
    coordinators: dict[str, KuniDataUpdateCoordinator] = hass.data[DOMAIN][
        entry.entry_id
    ]["coordinators"]
    async_add_entities(
        [KuniCurrentScentSelect(c) for c in coordinators.values()]
    )


class KuniCurrentScentSelect(
    CoordinatorEntity[KuniDataUpdateCoordinator], SelectEntity
):
    """Choose which loaded cartridge is active (API shadow field `position`)."""

    _attr_has_entity_name = True
    _attr_translation_key = "current_scent"

    def __init__(self, coordinator: KuniDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_"
            f"{coordinator.device_id}_current_scent"
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_id)},
            name=self.coordinator.device_name,
            manufacturer="Kuni",
        )

    @property
    def options(self) -> list[str]:
        slots = (self.coordinator.data or {}).get("scent_slots") or []
        return _slot_options(slots)

    @property
    def current_option(self) -> str | None:
        data = self.coordinator.data
        if not data:
            return None
        pos = data.get("scent_position")
        opts = self.options
        if pos is None or not opts:
            return None
        if 0 <= int(pos) < len(opts):
            return opts[int(pos)]
        return None

    async def async_select_option(self, option: str) -> None:
        opts = self.options
        if option not in opts:
            return
        idx = opts.index(option)
        await self.coordinator.api.async_set_scent_position(
            self.coordinator.device_id, idx
        )
        await self.coordinator.async_request_refresh()
