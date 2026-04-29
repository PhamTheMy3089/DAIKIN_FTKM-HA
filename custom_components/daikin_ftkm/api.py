"""Daikin local API client (firmware 2.8.0 — /dsiot/multireq endpoint)."""
from __future__ import annotations

import logging
import struct
from typing import Any

import aiohttp

from .const import API_PATH

_LOGGER = logging.getLogger(__name__)

# Write success codes (2000 = OK, 2004 = Created/Updated)
_WRITE_OK_RSC = {2000, 2004}


class DaikinAPIError(Exception):
    """Raised when the device returns an unexpected response."""


class DaikinAPI:
    """Thin async wrapper around the Daikin /dsiot/multireq endpoint."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        self._host = host
        self._url = f"http://{host}{API_PATH}"
        self._session = session

    # ── Read ─────────────────────────────────────────────────────────────────

    async def read(self, *addresses: str) -> dict[str, Any]:
        """POST a multi-read request; returns the raw response dict."""
        payload = {
            "requests": [
                {"op": 2, "to": f"/dsiot/edge/{addr}"}
                for addr in addresses
            ]
        }
        _LOGGER.debug("READ %s %s", self._url, addresses)
        async with self._session.post(
            self._url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            _LOGGER.debug("READ response: %s", data)
            return data

    # ── Write ─────────────────────────────────────────────────────────────────

    async def write(
        self,
        address: str,
        root_entity: str,
        entity: str,
        param: str,
        value: str,
    ) -> bool:
        """PUT a single-parameter write; returns True on success."""
        addr_node = address.split(".")[0]
        payload = {
            "requests": [
                {
                    "op": 3,
                    "to": f"/dsiot/edge/{address}",
                    "pc": {
                        "pn": addr_node,
                        "pch": [
                            {
                                "pn": root_entity,
                                "pch": [
                                    {
                                        "pn": entity,
                                        "pch": [{"pn": param, "pv": value}],
                                    }
                                ],
                            }
                        ],
                    },
                }
            ]
        }
        _LOGGER.debug("WRITE %s %s.%s.%s=%s", address, root_entity, entity, param, value)
        async with self._session.put(
            self._url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            _LOGGER.debug("WRITE response: %s", data)
            rsc = data.get("responses", [{}])[0].get("rsc")
            if rsc not in _WRITE_OK_RSC:
                _LOGGER.warning("Write returned unexpected rsc=%s for %s.%s", rsc, entity, param)
                return False
            return True

    async def test_connection(self) -> bool:
        """Return True if the device is reachable and responds correctly."""
        try:
            data = await self.read("adr_0100.dgc_status")
            rsc = data.get("responses", [{}])[0].get("rsc")
            return rsc == 2000
        except Exception:  # noqa: BLE001
            return False


# ── Value helpers ─────────────────────────────────────────────────────────────

def decode_hex_int(hex_str: str | None) -> int | None:
    """Decode a plain hex string to int (e.g. '19' → 25)."""
    if hex_str is None:
        return None
    try:
        return int(hex_str, 16)
    except (ValueError, TypeError):
        return None


def decode_le_uint16(hex_str: str | None) -> int | None:
    """Decode a 4-char LE hex string to int (e.g. '0200' → 2, '7200' → 114)."""
    if hex_str is None:
        return None
    try:
        raw = bytes.fromhex(hex_str)
        return struct.unpack("<H", raw)[0]
    except (ValueError, struct.error, TypeError):
        return None


def decode_le_int16(hex_str: str | None) -> int | None:
    """Decode a 4-char LE signed int16 (e.g. '3D00' → 61, 'CEFF' → -50)."""
    if hex_str is None:
        return None
    try:
        raw = bytes.fromhex(hex_str)
        return struct.unpack("<h", raw)[0]
    except (ValueError, struct.error, TypeError):
        return None


def decode_mode(hex_str: str | None) -> int | None:
    """Decode mode value — tries LE uint16 for 4-char strings, plain int otherwise."""
    if hex_str is None:
        return None
    if len(hex_str) == 4:
        return decode_le_uint16(hex_str)
    return decode_hex_int(hex_str)


def encode_hex_byte(value: int) -> str:
    """Encode int to 2-char uppercase hex (e.g. 56 → '38')."""
    return format(value & 0xFF, "02X")


def encode_le_uint16(value: int) -> str:
    """Encode int to 4-char LE hex string (e.g. 2 → '0200')."""
    return struct.pack("<H", value).hex().upper()


def find_pv(data: dict[str, Any], address: str, *path: str) -> str | None:
    """
    Locate a parameter value in an API response.

    Searches responses[] for one whose 'fr' or 'to' contains *address*,
    then walks the pch tree by the given *path* keys, returning 'pv'.
    """
    responses = data.get("responses", [])
    for resp in responses:
        # CoAP responses use 'fr' (from) field; fall back to 'to'
        endpoint = resp.get("fr") or resp.get("to") or ""
        if address not in endpoint:
            continue
        node: dict[str, Any] = resp.get("pc", {})
        for key in path:
            pch: list[dict] = node.get("pch", [])
            node = next((x for x in pch if x.get("pn") == key), None)  # type: ignore[assignment]
            if node is None:
                return None
        return node.get("pv") if isinstance(node, dict) else None
    return None


def find_energy_today(data: dict[str, Any]) -> float | None:
    """Extract today's energy (Wh) from a week_power response."""
    responses = data.get("responses", [])
    for resp in responses:
        endpoint = resp.get("fr") or resp.get("to") or ""
        if "week_power" not in endpoint:
            continue
        pc = resp.get("pc", {})
        datas = pc.get("datas")
        if isinstance(datas, list) and datas:
            try:
                return float(datas[-1])
            except (ValueError, TypeError):
                pass
    return None


def find_runtime_today(data: dict[str, Any]) -> int | None:
    """Extract today's runtime (minutes) from a week_power response."""
    responses = data.get("responses", [])
    for resp in responses:
        endpoint = resp.get("fr") or resp.get("to") or ""
        if "week_power" not in endpoint:
            continue
        pc = resp.get("pc", {})
        val = pc.get("today_runtime")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None
