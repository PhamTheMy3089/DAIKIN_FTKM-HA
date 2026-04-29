# Daikin FTKM — Home Assistant Local API Integration

Custom Home Assistant integration for **Daikin FTKM50AVMV** (and similar FTKM/RKM models with firmware 2.8.0) using the device's built-in local HTTP API — **no cloud, no SSL, no pydaikin**.

---

## Why this integration?

The official HA Daikin integration (via pydaikin) fails on firmware 2.8.0 with:
```
Cannot connect to host 192.168.100.204:2000 ssl:default [Connect call failed]
```
pydaikin tries port 2000 over SSL, which does not exist on this firmware.

This integration communicates directly with the `/dsiot/multireq` endpoint on port 80, which is the native local API for BRP084Cxx WiFi modules on fw 2.8.0.

---

## Hardware

| Component | Model |
|-----------|-------|
| Indoor unit | FTKM50AVMV |
| Outdoor unit | RKM50AVMV |
| WiFi module | BRP084Cxx (built-in) |
| Firmware | 2.8.0 |

---

## Installation (HACS manual)

1. Copy the `custom_components/daikin_ftkm/` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Integrations → Add Integration → Daikin FTKM (Local API)**.
4. Enter the IP address of your unit (set a DHCP reservation so it never changes).

---

## Entities created

| Entity | Type | Notes |
|--------|------|-------|
| `climate.daikin_ftkm_*` | Climate | Power, mode, setpoint, fan speed |
| `sensor.*_indoor_temperature` | Sensor | °C |
| `sensor.*_indoor_humidity` | Sensor | % (read-only) |
| `sensor.*_outdoor_temperature` | Sensor | °C |
| `sensor.*_compressor_frequency` | Sensor | Hz — **fixed** vs pydaikin |
| `sensor.*_compressor_power` | Sensor | kW — **fixed** (was always 0) |
| `sensor.*_energy_today` | Sensor | Wh |
| `sensor.*_runtime_today` | Sensor | minutes |

---

## Local API reference

### Endpoint
```
POST  http://<ip>/dsiot/multireq   → read  (op: 2)
PUT   http://<ip>/dsiot/multireq   → write (op: 3)
```
No authentication. Anyone on the same LAN can call it.

### Read request
```json
{
  "requests": [
    { "op": 2, "to": "/dsiot/edge/adr_0100.dgc_status" },
    { "op": 2, "to": "/dsiot/edge/adr_0200.dgc_status" }
  ]
}
```
`rsc: 2000` = OK. `rsc: 2004` = write OK.

### Field mapping (FTKM50AVMV fw 2.8.0)

**adr_0100 — Indoor unit**

| Field path | Encoding | Value |
|-----------|----------|-------|
| `e_A00B.p_01` | `int(hex, 16)` = °C | Indoor temperature |
| `e_A00B.p_02` | `int(hex, 16)` = % | Indoor humidity |
| `e_3003.p_01` | LE uint16: `0000`=fan, `0100`=heat, `0200`=cool, `0300`=auto, `0500`=dry | HVAC mode |
| `e_3003.p_02` | `00`=off, `01`=on | Power |
| `e_3003.p_0C` | `int(hex, 16) / 2` = °C | Target temperature |
| `e_3003.p_09` | LE uint16 (see fan table below) | Fan speed (cool mode) |

**Fan speed values**

| Hex | Mode |
|-----|------|
| `0A00` | Auto |
| `0B00` | Quiet |
| `0300` | Low |
| `0400` | Medium-Low |
| `0500` | Medium |
| `0600` | Medium-High |
| `0700` | High |

**adr_0200 — Outdoor unit**

| Field path | Encoding | Value |
|-----------|----------|-------|
| `e_A00D.p_01` | `int(hex, 16)` = °C | Outdoor temperature |
| `e_A005.p_09` | LE uint16 = Hz | Compressor frequency |
| `e_2008.p_01` | LE uint16 × 0.1 = kW | Compressor power (**was 0 in pydaikin**) |

---

## Known issues / TODOs

### Compressor power fix
pydaikin did not read `e_2008.p_01` from `adr_0200`. This integration reads it directly. Verify the value when the unit is running — it may be in W rather than kW (field `e_2008.p_01` × 0.1; e.g. raw `6200` → 98 → 9.8 kW or 980 W).

### Humidity control
Target humidity write field is **not yet confirmed**. Steps to discover it:
1. Switch the unit to **DRY mode** via the remote.
2. Call the read API and compare `adr_0100` response to the cool-mode response.
3. The new field that appears with a value matching your target humidity (%) is the write target.
4. Update `FIELD_TARGET_HUMIDITY` in `const.py` with the confirmed `(entity, param)` tuple.

### Setpoint fields for Heat / Auto modes
Only the cool-mode setpoint (`e_3003.p_0C`) is confirmed. Heat and Auto modes may use different params (`p_0D`, `p_1D`). Update `FIELD_SETPOINT` or add mode-specific fields in `const.py` after testing.

### Write format
If setting temperature/mode has no effect, the device may require a parent entity wrapper in the write payload (similar to how the FTKM20 uses `e_1002 → e_3001`). Enable `WRITE_PARENT` in `const.py` and adjust `api.py:write()` accordingly.

---

## Firmware warning

**Do NOT update firmware** via the Daikin Air Select app — newer versions may close the local API. Set a DHCP reservation for the unit's MAC address so its IP is stable.

---

## References

- [Apoc182/local_daikin](https://github.com/Apoc182/local_daikin) — Similar integration for FTKM20YVMA fw 2.8.0
- [HA core issue #99251](https://github.com/home-assistant/core/issues/99251) — API reverse-engineering thread
- [Chris971991/homeassistant-daikin-optimized](https://github.com/Chris971991/homeassistant-daikin-optimized) — pydaikin fork with SSL port fix
