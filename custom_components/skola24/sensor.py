"""One device per child. Sensors: ordinary times, exception times, current lesson."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import ChildDay, ClockSpan, current_lesson
from .const import DOMAIN
from .coordinator import Skola24Coordinator


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    coordinator: Skola24Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for guid, day in coordinator.data.items():
        entities.append(TimesSensor(coordinator, guid, day.name, "ordinary_times"))
        entities.append(TimesSensor(coordinator, guid, day.name, "exception_times"))
        entities.append(LessonSensor(coordinator, guid, day.name))
        entities.append(NextLessonSensor(coordinator, guid, day.name))
    async_add_entities(entities)


class ChildEntity(CoordinatorEntity[Skola24Coordinator]):
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


class _ChildSensor(ChildEntity, SensorEntity):
    pass


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


class LessonSensor(_ChildSensor):
    """What the week's timetable says is on right now. Empty between lessons."""

    _attr_translation_key = "current_lesson"
    _attr_icon = "mdi:school"

    def __init__(self, coordinator: Skola24Coordinator, guid: str, name: str) -> None:
        super().__init__(coordinator, guid, name)
        self._attr_unique_id = f"{guid}_current_lesson"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._tick, second=0)
        )

    @callback
    def _tick(self, _now) -> None:
        self.async_write_ha_state()

    def _now(self):
        day = self._day()
        if day is None:
            return None, None
        hhmm = dt_util.now(dt_util.get_time_zone("Europe/Stockholm")).strftime("%H:%M")
        return current_lesson(day.lessons, hhmm)

    @property
    def native_value(self) -> str | None:
        if self._day() is None:
            return None
        lesson, _ = self._now()
        return lesson.title if lesson else ""

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        lesson, upcoming = self._now()
        day = self._day()
        return {
            "timetable": [
                {
                    "start": item.start,
                    "end": item.end,
                    "title": item.title,
                    "details": ", ".join(item.details),
                }
                for item in (day.lessons if day else [])
            ],
            "details": ", ".join(lesson.details) if lesson else None,
            "start": lesson.start if lesson else None,
            "end": lesson.end if lesson else None,
            "next": upcoming.title if upcoming else None,
            "next_start": upcoming.start if upcoming else None,
        }


class NextLessonSensor(LessonSensor):
    """The next lesson today that starts after now. Empty when the day is done."""

    _attr_translation_key = "next_lesson"
    _attr_icon = "mdi:school-outline"

    def __init__(self, coordinator: Skola24Coordinator, guid: str, name: str) -> None:
        super().__init__(coordinator, guid, name)
        self._attr_unique_id = f"{guid}_next_lesson"

    @property
    def native_value(self) -> str | None:
        if self._day() is None:
            return None
        _, upcoming = self._now()
        return upcoming.title if upcoming else ""

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        _, upcoming = self._now()
        return {
            "details": ", ".join(upcoming.details) if upcoming else None,
            "start": upcoming.start if upcoming else None,
            "end": upcoming.end if upcoming else None,
        }


def _format_spans(spans: list[ClockSpan]) -> str:
    if not spans:
        return ""
    return ", ".join(f"{span.start}-{span.end}" for span in spans)
