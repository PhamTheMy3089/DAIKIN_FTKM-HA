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

# ── Indoor unit read fields (confirmed on FTKM50AVMV fw 2.8.0) ───────────────
#   Entity   Param   Encoding          Confirmed
FIELD_INDOOR_TEMP      = ("e_A00B", "p_01")  # int(hex, 16) = °C            ✓
FIELD_INDOOR_HUMIDITY  = ("e_A00B", "p_02")  # int(hex, 16) = %             ✓
FIELD_POWER            = ("e_3003", "p_02")  # "00"=off  "01"=on            ✓
FIELD_MODE             = ("e_3003", "p_01")  # LE uint16: 0200=cool         ✓
FIELD_SETPOINT         = ("e_3003", "p_0C")  # int(hex,16)/2 = °C           ✓
# Fan speed varies by mode; p_09 is confirmed for cool
FIELD_FAN_COOL         = ("e_3003", "p_09")  # LE uint16                    (assumed)
FIELD_FAN_HEAT         = ("e_3003", "p_0A")  # LE uint16                    (assumed)
FIELD_FAN_AUTO         = ("e_3003", "p_26")  # LE uint16                    (assumed)
FIELD_FAN_DRY          = ("e_3003", "p_28")  # LE uint16                    (assumed)
# Target humidity — field TBD; only present in DRY / AUTO mode
# TODO: Capture adr_0100 response while in DRY mode to confirm this field
FIELD_TARGET_HUMIDITY  = ("e_3003", "p_14")  # placeholder — needs verify

# ── Outdoor unit read fields ─────────────────────────────────────────────────
FIELD_OUTDOOR_TEMP     = ("e_A00D", "p_01")  # int(hex,16) = °C             (from local_daikin ref)
FIELD_COMPRESSOR_FREQ  = ("e_A005", "p_09")  # LE uint16 = Hz               ✓
FIELD_COMPRESSOR_POWER = ("e_2008", "p_01")  # LE uint16 × 0.1 = kW        ✓ (was 0 in pydaikin)

# Write target for indoor settings
WRITE_ADDR   = f"{ADDR_INDOOR}.dgc_status"
WRITE_ENTITY = "e_3003"
# NOTE: If direct writes to e_3003 fail on your device, try wrapping in a
# parent entity e.g. "e_1002". Uncomment WRITE_PARENT below:
# WRITE_PARENT = "e_1002"

# ── HVAC mode mapping ────────────────────────────────────────────────────────
# Values are little-endian uint16 hex strings as seen in the API response.
# int.from_bytes(bytes.fromhex("0200"), "little") == 2 == cool
HVAC_MODE_HEX_MAP: dict[str, HVACMode] = {
    "0000": HVACMode.FAN_ONLY,
    "0100": HVACMode.HEAT,
    "0200": HVACMode.COOL,
    "0300": HVACMode.AUTO,
    "0500": HVACMode.DRY,
}
# Reverse lookup: HVACMode → hex string for write
HVAC_MODE_TO_HEX: dict[HVACMode, str] = {v: k for k, v in HVAC_MODE_HEX_MAP.items()}

# ── Fan mode mapping ─────────────────────────────────────────────────────────
# Values are LE uint16 hex strings; names follow HA convention.
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

# Fan param name per HVAC mode (for write)
FAN_PARAM_BY_MODE: dict[HVACMode, str] = {
    HVACMode.COOL:     "p_09",
    HVACMode.HEAT:     "p_0A",
    HVACMode.AUTO:     "p_26",
    HVACMode.DRY:      "p_28",
    HVACMode.FAN_ONLY: "p_09",  # assumed same as cool
}

# ── Temperature limits ───────────────────────────────────────────────────────
MIN_TEMP = 16.0
MAX_TEMP = 32.0
TEMP_STEP = 0.5
