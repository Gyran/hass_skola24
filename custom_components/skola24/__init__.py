"""Skola24 parent account. A device per child, a service that writes today's note.

Home Assistant imports stay inside the setup functions so the client modules
can be imported by the stdio server and the tests.
"""

from __future__ import annotations

from .const import DOMAIN

_SERVICE = "set_temporary_change_message"


async def async_setup_entry(hass, entry) -> bool:
    from pathlib import Path

    from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

    from .auth import Credentials
    from .const import DEFAULT_HOST
    from .coordinator import Skola24Coordinator, build_client

    host = entry.data.get(CONF_HOST, DEFAULT_HOST)
    session = Path(hass.config.path(f".storage/skola24_{entry.entry_id}_cookies.json"))
    client = build_client(
        hass,
        Credentials(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            host=host,
        ),
        session,
    )
    coordinator = Skola24Coordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.aclose()
        raise
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    _register_service(hass)
    return True


async def async_unload_entry(hass, entry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.aclose()
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, _SERVICE)
    return unloaded


def _register_service(hass) -> None:
    import voluptuous as vol
    from homeassistant.core import SupportsResponse
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    from homeassistant.helpers import config_validation as cv

    from .api import get_temporary_change, set_temporary_change_message
    from .dates import service_date

    if hass.services.has_service(DOMAIN, _SERVICE):
        return

    schema = vol.Schema(
        {
            vol.Required("message"): cv.string,
            vol.Optional("date"): cv.string,
            vol.Optional("overwrite", default=False): cv.boolean,
            vol.Optional("device_id"): vol.Any(str, [str]),
            vol.Optional("entity_id"): vol.Any(str, [str]),
            vol.Optional("area_id"): vol.Any(str, [str]),
        }
    )

    async def _handle(call):
        device_ids = _device_ids(hass, call, er)
        if len(device_ids) != 1:
            raise ServiceValidationError("Target one Skola24 child device")
        device = dr.async_get(hass).async_get(device_ids[0])
        if device is None:
            raise ServiceValidationError("Unknown device")
        guid = next((item[1] for item in device.identifiers if item[0] == DOMAIN), None)
        if guid is None or not device.config_entries:
            raise ServiceValidationError("Device is not a Skola24 child")
        entry_id = next(iter(device.config_entries))
        coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
        if coordinator is None:
            raise ServiceValidationError("Skola24 is not loaded")
        if guid not in coordinator.data:
            raise ServiceValidationError("Child is not in the latest update")
        message = str(call.data["message"]).strip()
        if not message:
            raise ServiceValidationError("Empty message rejected")
        try:
            date = service_date(call.data.get("date"))
        except ValueError as err:
            raise ServiceValidationError("date must be YYYY-MM-DD") from err
        overwrite = bool(call.data.get("overwrite", False))
        if not overwrite:
            current = await get_temporary_change(coordinator.client, guid, date)
            if current.message:
                return {
                    "child": current.child,
                    "date": current.date,
                    "message": current.message,
                    "skipped": True,
                    "confirmation": "Befintlig lapp lämnades kvar.",
                }
        saved = await set_temporary_change_message(
            coordinator.client, guid, message, date
        )
        await coordinator.async_request_refresh()
        return {
            "child": saved.child,
            "date": saved.date,
            "message": saved.message,
            "skipped": False,
            "confirmation": saved.confirmation,
        }

    hass.services.async_register(
        DOMAIN,
        _SERVICE,
        _handle,
        schema=schema,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _device_ids(hass, call, entity_registry) -> list[str]:
    raw = call.data.get("device_id")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list) and raw:
        return [str(item) for item in raw]
    entity_ids = call.data.get("entity_id")
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    if not entity_ids:
        return []
    registry = entity_registry.async_get(hass)
    found: list[str] = []
    for entity_id in entity_ids:
        entity = registry.async_get(entity_id)
        if entity and entity.device_id:
            found.append(entity.device_id)
    return found
