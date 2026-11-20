"""Poll today's exception for every child."""

from datetime import timedelta
import logging
from pathlib import Path

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.ssl import get_default_context

from .api import ChildDay, get_timetable, lessons_on, today_overview
from .auth import AuthError, Credentials
from .client import Skola24Client
from .const import DOMAIN
from .dates import today_stockholm

_LOGGER = logging.getLogger(__name__)


def build_client(
    hass: HomeAssistant, credentials: Credentials, session_file: Path | None
) -> Skola24Client:
    """A client with cookie file I/O in the executor.

    The httpx client is ours, not HA's, because it holds this account's cookies
    and is closed on unload. HA warns when its own clients are closed. HA's
    cached SSL context keeps creation off the disk.
    """
    http = httpx.AsyncClient(
        verify=get_default_context(),
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
        today = today_stockholm()
        for day in days:
            # The schedule is a bonus. A failure here must not hide the rest.
            try:
                week = await get_timetable(self.client, child=day.name, date=today)
                day.lessons = lessons_on(week.lessons, today)
            except Exception as err:
                _LOGGER.debug("No timetable for %s: %s", day.name, err)
        return {day.guid: day for day in days}
