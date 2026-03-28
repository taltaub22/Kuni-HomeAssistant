"""Kuni scent slot sensors (current cartridge / level per slot from device shadow)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUM_SCENT_SLOTS, entity_suggested_object_id
from .coordinator import KuniDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add scent slot sensors for each discovered device."""
    coordinators: dict[str, KuniDataUpdateCoordinator] = hass.data[DOMAIN][
        entry.entry_id
    ]["coordinators"]
    entities: list[KuniScentSlotSensor] = []
    for coordinator in coordinators.values():
        for idx in range(NUM_SCENT_SLOTS):
            key = f"scent_slot_{idx + 1}"
            entities.append(
                KuniScentSlotSensor(
                    coordinator,
                    SensorEntityDescription(
                        key=key,
                        native_unit_of_measurement=PERCENTAGE,
                        suggested_display_precision=0,
                    ),
                    slot_index=idx,
                )
            )
    async_add_entities(entities)


class KuniScentSlotSensor(
    CoordinatorEntity[KuniDataUpdateCoordinator], SensorEntity
):
    """Cartridge fill level % for one slot; scent name in attributes."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KuniDataUpdateCoordinator,
        description: SensorEntityDescription,
        *,
        slot_index: int,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._slot_index = slot_index
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
    def name(self) -> str:
        """Include slot index and catalog scent title (updates when cartridges change)."""
        slots = (self.coordinator.data or {}).get("scent_slots") or []
        num = self._slot_index + 1
        if self._slot_index >= len(slots):
            return f"Slot {num}"
        row = slots[self._slot_index]
        scent = row.get("name")
        if scent:
            return f"Slot {num} · {scent}"
        return f"Slot {num} · Empty"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_id)},
            name=self.coordinator.device_name,
            manufacturer="Kuni",
        )

    @property
    def native_value(self) -> StateType:
        if not self.coordinator.data:
            return None
        slots: list = self.coordinator.data.get("scent_slots") or []
        if self._slot_index >= len(slots):
            return None
        level = slots[self._slot_index].get("level")
        if level is None:
            return None
        try:
            return float(level)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        if not self.coordinator.data:
            return {"scent_id": None, "scent_name": None}
        slots: list = self.coordinator.data.get("scent_slots") or []
        if self._slot_index >= len(slots):
            return {"scent_id": None, "scent_name": None}
        row = slots[self._slot_index]
        name = row.get("name")
        return {
            "scent_id": row.get("scent_id"),
            "scent_name": str(name) if name else None,
        }
