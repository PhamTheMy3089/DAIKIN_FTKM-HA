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
    decode_mode,
    encode_hex_byte,
    encode_le_uint16,
    find_pv,
)
from .config_flow import CONF_HOST
from .const import (
    ADDR_INDOOR,
    DOMAIN,
    FAN_MODE_HEX_MAP,
    FAN_MODE_TO_HEX,
    FAN_PARAM_BY_MODE,
    FIELD_FAN_COOL,
    FIELD_FAN_HEAT,
    FIELD_INDOOR_HUMIDITY,
    FIELD_INDOOR_TEMP,
    FIELD_MODE,
    FIELD_POWER,
    FIELD_SETPOINT,
    FIELD_TARGET_HUMIDITY,
    HVAC_MODE_HEX_MAP,
    HVAC_MODE_TO_HEX,
    MANUFACTURER,
    MAX_TEMP,
    MIN_TEMP,
    TEMP_STEP,
    WRITE_ADDR,
    WRITE_ENTITY,
)
from .coordinator import DaikinCoordinator

_LOGGER = logging.getLogger(__name__)

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
        power_raw = find_pv(self.coordinator.data, ADDR_INDOOR, *FIELD_POWER)
        # Power field: "00" = off, "01" = on (1-byte hex)
        if power_raw in ("00", "0000", None):
            return HVACMode.OFF

        mode_raw = find_pv(self.coordinator.data, ADDR_INDOOR, *FIELD_MODE)
        mode_int = decode_mode(mode_raw)
        return _HVAC_INT_MAP.get(mode_int, HVACMode.OFF)  # type: ignore[arg-type]

    @property
    def target_temperature(self) -> float | None:
        raw = find_pv(self.coordinator.data, ADDR_INDOOR, *FIELD_SETPOINT)
        val = decode_hex_int(raw)
        # Setpoint stored as (°C × 2); e.g. "38" = 0x38 = 56 → 28.0°C
        return val / 2 if val is not None else None

    @property
    def fan_mode(self) -> str:
        # Fan param depends on current mode; fall back to cool's p_09
        mode = self.hvac_mode
        fan_param = FAN_PARAM_BY_MODE.get(mode, FIELD_FAN_COOL[1])
        raw = find_pv(self.coordinator.data, ADDR_INDOOR, WRITE_ENTITY, fan_param)
        if raw:
            return FAN_MODE_HEX_MAP.get(raw.upper(), FAN_AUTO)
        return FAN_AUTO

    # ── Write operations ──────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        api = self.coordinator.api
        if hvac_mode == HVACMode.OFF:
            await api.write(WRITE_ADDR, WRITE_ENTITY, FIELD_POWER[1], "00")
        else:
            mode_hex = HVAC_MODE_TO_HEX.get(hvac_mode)
            if mode_hex is None:
                _LOGGER.error("Unknown HVAC mode: %s", hvac_mode)
                return
            # Power on first, then set mode
            await api.write(WRITE_ADDR, WRITE_ENTITY, FIELD_POWER[1], "01")
            await api.write(WRITE_ADDR, WRITE_ENTITY, FIELD_MODE[1], mode_hex)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.coordinator.api.write(WRITE_ADDR, WRITE_ENTITY, FIELD_POWER[1], "01")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        await self.coordinator.api.write(WRITE_ADDR, WRITE_ENTITY, FIELD_POWER[1], "00")
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        # Encode: °C × 2 → int → 2-char hex byte. E.g. 28.0 → 56 → "38"
        encoded = encode_hex_byte(int(round(temp * 2)))
        await self.coordinator.api.write(WRITE_ADDR, WRITE_ENTITY, FIELD_SETPOINT[1], encoded)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        hex_val = FAN_MODE_TO_HEX.get(fan_mode)
        if hex_val is None:
            _LOGGER.error("Unknown fan mode: %s", fan_mode)
            return
        current_mode = self.hvac_mode
        fan_param = FAN_PARAM_BY_MODE.get(current_mode, FIELD_FAN_COOL[1])
        await self.coordinator.api.write(WRITE_ADDR, WRITE_ENTITY, fan_param, hex_val)
        await self.coordinator.async_request_refresh()
