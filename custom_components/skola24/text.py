"""The day's note. Editing it writes to Skola24. Empty clears it."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import set_temporary_change_message
from .const import DOMAIN
from .coordinator import Skola24Coordinator
from .sensor import ChildEntity

_MAX_STATE = 255


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    coordinator: Skola24Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MessageText(coordinator, guid, day.name) for guid, day in coordinator.data.items()
    )


class MessageText(ChildEntity, TextEntity):
    _attr_translation_key = "message"
    _attr_icon = "mdi:message-text"
    _attr_native_min = 0
    _attr_native_max = _MAX_STATE

    def __init__(self, coordinator: Skola24Coordinator, guid: str, name: str) -> None:
        super().__init__(coordinator, guid, name)
        self._attr_unique_id = f"{guid}_message"

    @property
    def native_value(self) -> str | None:
        day = self._day()
        return None if day is None else (day.message or "")[:_MAX_STATE]

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """The full note. State is capped at 255 characters."""
        day = self._day()
        return {"message": day.message if day else None}

    async def async_set_value(self, value: str) -> None:
        """Setting the value replaces whatever note the day has."""
        try:
            await set_temporary_change_message(self.coordinator.client, self._guid, value)
        except Exception as err:
            raise HomeAssistantError(f"Skola24 did not save the message: {err}") from err
        await self.coordinator.async_request_refresh()
