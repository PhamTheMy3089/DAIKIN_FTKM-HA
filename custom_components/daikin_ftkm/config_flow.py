"""Config flow for Daikin FTKM Local API integration."""
from __future__ import annotations

import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DaikinAPI
from .const import DOMAIN

CONF_HOST = "host"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)


async def _validate_host(hass: HomeAssistant, host: str) -> str | None:
    """Return an error key if the host is unreachable, None on success."""
    session = async_get_clientsession(hass)
    api = DaikinAPI(host.strip(), session)
    try:
        ok = await api.test_connection()
        return None if ok else "cannot_connect"
    except aiohttp.ClientError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        return "unknown"


class DaikinFTKMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the user-facing configuration flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            error = await _validate_host(self.hass, host)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"Daikin FTKM ({host})",
                    data={CONF_HOST: host},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
