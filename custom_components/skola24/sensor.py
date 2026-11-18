"""One device per child. Three sensors: note, ordinary times, exception times."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ChildDay, ClockSpan
from .const import DOMAIN
from .coordinator import Skola24Coordinator

_MAX_STATE = 255


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    coordinator: Skola24Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for guid, day in coordinator.data.items():
        entities.append(MessageSensor(coordinator, guid, day.name))
        entities.append(TimesSensor(coordinator, guid, day.name, "ordinary_times"))
        entities.append(TimesSensor(coordinator, guid, day.name, "exception_times"))
    async_add_entities(entities)


class _ChildSensor(CoordinatorEntity[Skola24Coordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Skola24Coordinator, guid: str, name: str) -> None:
        super().__init__(coordinator)
        self._guid = guid
        self._child_name = name

    @property
    def available(self) -> bool:
        return self._guid in self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        day = self.coordinator.data.get(self._guid)
        return DeviceInfo(
            identifiers={(DOMAIN, self._guid)},
            name=self._child_name,
            manufacturer="Skola24",
            model=day.school if day else None,
            configuration_url="https://web.skola24.se/",
        )

    def _day(self) -> ChildDay | None:
        return self.coordinator.data.get(self._guid)


class MessageSensor(_ChildSensor):
    _attr_translation_key = "message"
    _attr_icon = "mdi:message-text"

    def __init__(self, coordinator: Skola24Coordinator, guid: str, name: str) -> None:
        super().__init__(coordinator, guid, name)
        self._attr_unique_id = f"{guid}_message"

    @property
    def native_value(self) -> str | None:
        day = self._day()
        if day is None or day.message is None:
            return None
        if len(day.message) <= _MAX_STATE:
            return day.message
        return day.message[: _MAX_STATE - 1] + "…"

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """The full note. State is capped at 255 characters."""
        day = self._day()
        return {"message": day.message if day else None}


class TimesSensor(_ChildSensor):
    def __init__(
        self,
        coordinator: Skola24Coordinator,
        guid: str,
        name: str,
        kind: str,
    ) -> None:
        super().__init__(coordinator, guid, name)
        self._kind = kind
        self._attr_unique_id = f"{guid}_{kind}"
        self._attr_translation_key = kind
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> str | None:
        day = self._day()
        if day is None:
            return None
        spans = day.ordinary_times if self._kind == "ordinary_times" else day.exception_times
        return _format_spans(spans)


def _format_spans(spans: list[ClockSpan]) -> str | None:
    if not spans:
        return None
    return ", ".join(f"{span.start}-{span.end}" for span in spans)
