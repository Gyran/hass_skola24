"""A diagnostic button per child that refreshes the data on demand."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import Skola24Coordinator
from .sensor import ChildEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    coordinator: Skola24Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        UpdateButton(coordinator, guid, day.name)
        for guid, day in coordinator.data.items()
    )


class UpdateButton(ChildEntity, ButtonEntity):
    _attr_translation_key = "update_data"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: Skola24Coordinator, guid: str, name: str) -> None:
        super().__init__(coordinator, guid, name)
        self._attr_unique_id = f"{guid}_update_data"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
