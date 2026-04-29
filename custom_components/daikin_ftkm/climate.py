"""Climate entity for Daikin FTKM Local API integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import FAN_AUTO
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    decode_hex_int,
    decode_le_uint16,
    encode_hex_byte,
    find_pv,
)
from .config_flow import CONF_HOST
from .const import (
    ADDR_INDOOR,
    DOMAIN,
    FAN_MODE_HEX_MAP,
    FAN_MODE_TO_HEX,
    FIELD_FAN_READ,
    FIELD_FAN_WRITE_PARAM,
    FIELD_INDOOR_HUMIDITY,
    FIELD_INDOOR_TEMP,
    FIELD_MODE,
    FIELD_POWER,
    FIELD_SETPOINT,
    HVAC_MODE_TO_HEX,
    MANUFACTURER,
    MAX_TEMP,
    MIN_TEMP,
    TEMP_STEP,
    WRITE_ADDR,
    WRITE_ENTITY,
    WRITE_ROOT_ENTITY,
)
from .coordinator import DaikinCoordinator

_LOGGER = logging.getLogger(__name__)

# Map raw int mode value → HVACMode (e_3003.p_01 is a single hex byte)
_HVAC_INT_MAP: dict[int, HVACMode] = {
    0: HVACMode.FAN_ONLY,
    1: HVACMode.HEAT,
    2: HVACMode.COOL,
    3: HVACMode.AUTO,
    5: HVACMode.DRY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DaikinCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DaikinClimate(coordinator, entry.data[CONF_HOST])])


class DaikinClimate(CoordinatorEntity[DaikinCoordinator], ClimateEntity):
    """Daikin FTKM climate entity — controls power, mode, setpoint and fan speed."""

    _attr_has_entity_name = True
    _attr_name = None  # uses device name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.AUTO,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = list(FAN_MODE_TO_HEX.keys())
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: DaikinCoordinator, host: str) -> None:
        super().__init__(coordinator)
        self._host = host
        self._attr_unique_id = f"daikin_ftkm_{host}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=f"Daikin FTKM ({host})",
            manufacturer=MANUFACTURER,
            model="FTKM50AVMV",
            configuration_url=f"http://{host}",
        )

    # ── State properties ──────────────────────────────────────────────────────

    @property
    def current_temperature(self) -> float | None:
        raw = find_pv(self.coordinator.data, ADDR_INDOOR, *FIELD_INDOOR_TEMP)
        val = decode_hex_int(raw)
        return float(val) if val is not None else None

    @property
    def current_humidity(self) -> int | None:
        raw = find_pv(self.coordinator.data, ADDR_INDOOR, *FIELD_INDOOR_HUMIDITY)
        return decode_hex_int(raw)

    @property
    def hvac_mode(self) -> HVACMode:
        # e_3003.p_02 was confirmed to stay "00" in both running and idle states,
        # so it cannot be used as a reliable power-state indicator.
        # Instead, treat the entity as ON whenever a valid mode can be read.
        # Writing "00" to p_02 still serves as the off command.
        mode_raw = find_pv(self.coordinator.data, ADDR_INDOOR, *FIELD_MODE)
        if mode_raw is None:
            return HVACMode.OFF
        mode_int = decode_hex_int(mode_raw)
        return _HVAC_INT_MAP.get(mode_int, HVACMode.OFF)  # type: ignore[arg-type]

    @property
    def target_temperature(self) -> float | None:
        raw = find_pv(self.coordinator.data, ADDR_INDOOR, *FIELD_SETPOINT)
        val = decode_hex_int(raw)
        # Setpoint stored as (°C × 2); e.g. "38" = 0x38 = 56 → 28.0°C
        return val / 2 if val is not None else None

    @property
    def fan_mode(self) -> str:
        # Read from e_3001.p_09 (read-only status entity).
        # Confirmed: "0A00" (LE=10) = auto from live device data.
        raw = find_pv(self.coordinator.data, ADDR_INDOOR, *FIELD_FAN_READ)
        if raw:
            return FAN_MODE_HEX_MAP.get(raw.upper(), FAN_AUTO)
        return FAN_AUTO

    # ── Write operations ──────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        api = self.coordinator.api
        if hvac_mode == HVACMode.OFF:
            await api.write(WRITE_ADDR, WRITE_ROOT_ENTITY, WRITE_ENTITY, FIELD_POWER[2], "00")
        else:
            mode_hex = HVAC_MODE_TO_HEX.get(hvac_mode)
            if mode_hex is None:
                _LOGGER.error("Unknown HVAC mode: %s", hvac_mode)
                return
            await api.write(WRITE_ADDR, WRITE_ROOT_ENTITY, WRITE_ENTITY, FIELD_POWER[2], "01")
            await api.write(WRITE_ADDR, WRITE_ROOT_ENTITY, WRITE_ENTITY, FIELD_MODE[2], mode_hex)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.coordinator.api.write(
            WRITE_ADDR, WRITE_ROOT_ENTITY, WRITE_ENTITY, FIELD_POWER[2], "01"
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        await self.coordinator.api.write(
            WRITE_ADDR, WRITE_ROOT_ENTITY, WRITE_ENTITY, FIELD_POWER[2], "00"
        )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        # Encode: °C × 2 → int → 2-char hex byte. E.g. 28.0 → 56 → "38"
        encoded = encode_hex_byte(int(round(temp * 2)))
        await self.coordinator.api.write(
            WRITE_ADDR, WRITE_ROOT_ENTITY, WRITE_ENTITY, FIELD_SETPOINT[2], encoded
        )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        hex_val = FAN_MODE_TO_HEX.get(fan_mode)
        if hex_val is None:
            _LOGGER.error("Unknown fan mode: %s", fan_mode)
            return
        # Write to e_3003.p_2F — single param for all HVAC modes (confirmed from device data)
        await self.coordinator.api.write(
            WRITE_ADDR, WRITE_ROOT_ENTITY, WRITE_ENTITY, FIELD_FAN_WRITE_PARAM, hex_val
        )
        await self.coordinator.async_request_refresh()
