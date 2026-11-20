"""Skola24 parent account. A device per child. The message entity writes the day's note.

Home Assistant imports stay inside the setup functions so the client modules
can be imported by the stdio server and the tests.
"""

from __future__ import annotations

from .const import DOMAIN

PLATFORMS = ["sensor", "button", "text"]


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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.aclose()
    return unloaded
