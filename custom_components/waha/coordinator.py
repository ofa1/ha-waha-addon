"""Session-status polling for WAHA."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WahaAuthError, WahaClient, WahaError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# A WhatsApp session drops rarely but silently, and the whole point of the
# sensor is to notice. 30s is cheap against a service on the same host.
UPDATE_INTERVAL = timedelta(seconds=30)

type WahaConfigEntry = ConfigEntry[WahaCoordinator]


class WahaCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls /api/sessions and exposes the sessions keyed by name."""

    config_entry: WahaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: WahaConfigEntry,
        client: WahaClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch the current session list."""
        try:
            sessions = await self.client.async_list_sessions()
        except WahaAuthError as err:
            # Surfaces as a reauth prompt rather than a permanently failing
            # entity — the add-on regenerates its key when told to.
            raise ConfigEntryAuthFailed(str(err)) from err
        except WahaError as err:
            raise UpdateFailed(str(err)) from err

        return {
            session["name"]: session
            for session in sessions
            if isinstance(session.get("name"), str)
        }
