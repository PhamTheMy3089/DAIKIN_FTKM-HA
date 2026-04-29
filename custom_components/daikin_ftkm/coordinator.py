"""DataUpdateCoordinator for Daikin FTKM."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import aiohttp

from .api import DaikinAPI
from .const import ADDR_INDOOR, ADDR_OUTDOOR, ADDR_ENERGY, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class DaikinCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls all three Daikin endpoints and merges responses into one dict."""

    def __init__(self, hass: HomeAssistant, api: DaikinAPI) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.read(
                f"{ADDR_INDOOR}.dgc_status",
                f"{ADDR_OUTDOOR}.dgc_status",
                ADDR_ENERGY,
            )
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Cannot reach Daikin device: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

        # Validate at least one response came back OK
        responses = data.get("responses", [])
        if not responses:
            raise UpdateFailed("Empty response from device")
        if not any(r.get("rsc") == 2000 for r in responses):
            raise UpdateFailed(f"Device returned no successful response: {responses}")

        return data
