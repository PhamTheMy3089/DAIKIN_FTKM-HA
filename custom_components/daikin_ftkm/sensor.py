"""Sensor entities for Daikin FTKM Local API integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    decode_hex_int,
    decode_le_uint16,
    find_energy_today,
    find_pv,
    find_runtime_today,
)
from .config_flow import CONF_HOST
from .const import (
    ADDR_INDOOR,
    ADDR_OUTDOOR,
    DOMAIN,
    FIELD_COMPRESSOR_FREQ,
    FIELD_COMPRESSOR_POWER,
    FIELD_INDOOR_HUMIDITY,
    FIELD_INDOOR_TEMP,
    FIELD_OUTDOOR_TEMP,
    MANUFACTURER,
)
from .coordinator import DaikinCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DaikinSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value-extractor callable."""

    value_fn: Callable[[dict[str, Any]], float | int | str | None]


def _make_descriptions() -> list[DaikinSensorDescription]:
    return [
        DaikinSensorDescription(
            key="indoor_temperature",
            name="Indoor Temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            value_fn=lambda d: decode_hex_int(find_pv(d, ADDR_INDOOR, *FIELD_INDOOR_TEMP)),
        ),
        DaikinSensorDescription(
            key="indoor_humidity",
            name="Indoor Humidity",
            device_class=SensorDeviceClass.HUMIDITY,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: decode_hex_int(find_pv(d, ADDR_INDOOR, *FIELD_INDOOR_HUMIDITY)),
        ),
        DaikinSensorDescription(
            key="outdoor_temperature",
            name="Outdoor Temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            # e_A00D.p_01 in adr_0200 — confirmed by local_daikin reference
            value_fn=lambda d: decode_hex_int(find_pv(d, ADDR_OUTDOOR, *FIELD_OUTDOOR_TEMP)),
        ),
        DaikinSensorDescription(
            key="compressor_frequency",
            name="Compressor Frequency",
            device_class=SensorDeviceClass.FREQUENCY,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfFrequency.HERTZ,
            # e_A005.p_09 in adr_0200 — LE uint16; e.g. "7200" → 114 Hz
            value_fn=lambda d: decode_le_uint16(find_pv(d, ADDR_OUTDOOR, *FIELD_COMPRESSOR_FREQ)),
        ),
        DaikinSensorDescription(
            key="compressor_power",
            name="Compressor Power",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.KILO_WATT,
            # e_2008.p_01 in adr_0200 — LE uint16 × 0.1 kW
            # FIX: pydaikin integration returns 0 because it does not read this field.
            # This implementation reads it directly from the outdoor unit response.
            value_fn=lambda d: _compressor_power_kw(d),
        ),
        DaikinSensorDescription(
            key="energy_today",
            name="Energy Today",
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            value_fn=lambda d: find_energy_today(d),
        ),
        DaikinSensorDescription(
            key="runtime_today",
            name="Runtime Today",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: find_runtime_today(d),
        ),
    ]


def _compressor_power_kw(data: dict[str, Any]) -> float | None:
    raw = find_pv(data, ADDR_OUTDOOR, *FIELD_COMPRESSOR_POWER)
    val = decode_le_uint16(raw)
    if val is None:
        return None
    return round(val * 0.1, 2)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DaikinCoordinator = hass.data[DOMAIN][entry.entry_id]
    host: str = entry.data[CONF_HOST]
    async_add_entities(
        DaikinSensor(coordinator, host, desc) for desc in _make_descriptions()
    )


class DaikinSensor(CoordinatorEntity[DaikinCoordinator], SensorEntity):
    """A sensor reading from the Daikin coordinator data."""

    entity_description: DaikinSensorDescription

    def __init__(
        self,
        coordinator: DaikinCoordinator,
        host: str,
        description: DaikinSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"daikin_ftkm_{host}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=f"Daikin FTKM ({host})",
            manufacturer=MANUFACTURER,
            model="FTKM50AVMV",
            configuration_url=f"http://{host}",
        )

    @property
    def native_value(self) -> float | int | str | None:
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Error computing %s: %s", self.entity_description.key, err)
            return None
