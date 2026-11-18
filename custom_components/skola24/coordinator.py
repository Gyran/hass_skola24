"""Poll today's exception for every child."""

from datetime import timedelta
import logging
from pathlib import Path

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.httpx_client import create_async_httpx_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ChildDay, today_overview
from .auth import AuthError, Credentials
from .client import Skola24Client
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def build_client(
    hass: HomeAssistant, credentials: Credentials, session_file: Path | None
) -> Skola24Client:
    """A client on HA's httpx setup with cookie file I/O in the executor."""
    http = create_async_httpx_client(
        hass,
        auto_cleanup=False,
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
    )
    return Skola24Client(
        credentials,
        session_file,
        http=http,
        run_io=hass.async_add_executor_job,
    )


class Skola24Coordinator(DataUpdateCoordinator[dict[str, ChildDay]]):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: Skola24Client
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=30),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, ChildDay]:
        try:
            days = await today_overview(self.client)
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(str(err)) from err
        return {day.guid: day for day in days}
