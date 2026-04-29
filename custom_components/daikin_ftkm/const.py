"""Constants for Daikin FTKM Local API integration."""
from homeassistant.components.climate import HVACMode

DOMAIN = "daikin_ftkm"
MANUFACTURER = "Daikin"

SCAN_INTERVAL = 30  # seconds

# API
API_PATH = "/dsiot/multireq"
ADDR_INDOOR = "adr_0100"
ADDR_OUTDOOR = "adr_0200"
ADDR_ENERGY = "adr_0100.i_power.week_power"

# ── Root entities (confirmed from device response) ────────────────────────────
# adr_0100 wraps indoor data under e_1002; adr_0200 wraps outdoor under e_1003
ROOT_INDOOR  = "e_1002"
ROOT_OUTDOOR = "e_1003"

# ── Indoor unit read fields (confirmed on FTKM50AVMV fw 2.8.0) ───────────────
#   Full path       Entity           Param   Encoding          Confirmed
FIELD_INDOOR_TEMP      = (ROOT_INDOOR, "e_A00B", "p_01")  # int(hex,16) = °C          ✓
FIELD_INDOOR_HUMIDITY  = (ROOT_INDOOR, "e_A00B", "p_02")  # int(hex,16) = %            ✓
FIELD_MODE             = (ROOT_INDOOR, "e_3003", "p_01")  # int(hex,16): 0-5           ✓
FIELD_SETPOINT         = (ROOT_INDOOR, "e_3003", "p_0C")  # int(hex,16)/2 = °C         ✓
# p_02 in e_3003 does NOT reflect on/off state (confirmed via two live snapshots).
# It stays "00" regardless of whether the compressor is running or idle.
# Writing "01"/"00" to it is kept as the best available on/off command, but
# hvac_mode reads should NOT use it to infer running state.
FIELD_POWER            = (ROOT_INDOOR, "e_3003", "p_02")  # write-only cmd: "01"=on "00"=off

# Fan speed: read from e_3001 (read-only status entity), write to e_3003.p_2F
# e_3001.p_09 = "0A00" (LE=10=auto) confirmed from device in both snapshots
FIELD_FAN_READ  = (ROOT_INDOOR, "e_3001", "p_09")  # LE uint16; "0A00"=auto ✓
FIELD_FAN_WRITE_PARAM  = "p_2F"                     # in e_3003, LE uint16, range 0–10

# ── Outdoor unit read fields ─────────────────────────────────────────────────
FIELD_OUTDOOR_TEMP     = (ROOT_OUTDOOR, "e_A00D", "p_01")  # signed LE int16 / 2 = °C  ✓
FIELD_COMPRESSOR_FREQ  = (ROOT_OUTDOOR, "e_A005", "p_09")  # LE uint16 = Hz (cached)   ✓
FIELD_COMPRESSOR_POWER = (ROOT_OUTDOOR, "e_2008", "p_01")  # LE uint16 × 0.1 = kW      ✓

# Write target for indoor settings
WRITE_ADDR        = f"{ADDR_INDOOR}.dgc_status"
WRITE_ROOT_ENTITY = ROOT_INDOOR   # e_1002 wrapper required by device
WRITE_ENTITY      = "e_3003"

# ── HVAC mode mapping ────────────────────────────────────────────────────────
# p_01 in e_3003 is a single byte (int value 0–5).
# Read:  find_pv returns "02" → decode_hex_int → 2 → _HVAC_INT_MAP lookup
# Write: encode back as single hex byte ("02" for cool)
_HVAC_INT_MAP_EXPORT: dict[int, HVACMode] = {
    0: HVACMode.FAN_ONLY,
    1: HVACMode.HEAT,
    2: HVACMode.COOL,
    3: HVACMode.AUTO,
    5: HVACMode.DRY,
}
HVAC_MODE_TO_HEX: dict[HVACMode, str] = {
    HVACMode.FAN_ONLY: "00",
    HVACMode.HEAT:     "01",
    HVACMode.COOL:     "02",
    HVACMode.AUTO:     "03",
    HVACMode.DRY:      "05",
}

# ── Fan mode mapping ─────────────────────────────────────────────────────────
# Values are LE uint16 hex strings stored in e_3003.p_2F and e_3001.p_09.
# Confirmed: "0A00" (LE=10) = auto from live device data.
FAN_MODE_HEX_MAP: dict[str, str] = {
    "0A00": "auto",
    "0B00": "quiet",
    "0300": "low",
    "0400": "medium_low",
    "0500": "medium",
    "0600": "medium_high",
    "0700": "high",
}
FAN_MODE_TO_HEX: dict[str, str] = {v: k for k, v in FAN_MODE_HEX_MAP.items()}

# ── Temperature limits ───────────────────────────────────────────────────────
MIN_TEMP = 16.0
MAX_TEMP = 32.0
TEMP_STEP = 0.5
