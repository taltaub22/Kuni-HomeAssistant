"""HTTP client for the Aroma Republic Kuni mobile API."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .cognito import async_refresh_tokens, token_needs_refresh
from .const import (
    API_PREFIX,
    NUM_SCENT_SLOTS,
    SCENT_CATALOG_TTL_SEC,
    SHADOW_INTENSITY,
    SHADOW_LIST,
    SHADOW_POSITION,
    SHADOW_POWER,
)

_LOGGER = logging.getLogger(__name__)


def device_entry_id(device: dict[str, Any]) -> str:
    """Stable device UUID from a GET /devices/ item."""
    return str(
        device.get("id") or device.get("deviceId") or device.get("device_id") or ""
    ).strip()


def device_display_label(device: dict[str, Any]) -> str:
    """Short label for config-flow device picker."""
    did = device_entry_id(device)
    name = device.get("name") or device.get("deviceName") or device.get("label")
    if name and did:
        return f"{name} ({did[:8]}…)"
    if name:
        return str(name)
    return did or "Kuni device"


def device_entries_from_raw(raw: Any) -> list[dict[str, Any]]:
    """Normalize GET /devices/ JSON to a list of device dicts."""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("devices", "data", "items", "results"):
            inner = raw.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
        return [raw]
    return []


def _strip_bearer(token: str) -> str:
    t = token.strip()
    if t.lower().startswith("bearer "):
        return t[7:].strip()
    return t


def _coerce_bool(val: Any) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "on", "yes")
    return None


def _coerce_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


def _shadow_field_value(field: dict[str, Any] | None) -> Any:
    """Prefer device-reported shadow value, else desired (e.g. right after a command)."""
    if not isinstance(field, dict):
        return None
    if "reported" in field and field["reported"] is not None:
        return field["reported"]
    if "desired" in field and field["desired"] is not None:
        return field["desired"]
    return None


def _merge_reported_state(device: dict[str, Any]) -> dict[str, Any]:
    """Flatten common IoT shadow / reported shapes into one dict."""
    merged: dict[str, Any] = {}

    def absorb(d: dict[str, Any]) -> None:
        for k, v in d.items():
            if k in merged or not isinstance(v, (str, int, float, bool)):
                continue
            merged[k] = v

    absorb(device)

    shadow = device.get("shadow") or device.get("deviceShadow")
    if isinstance(shadow, dict):
        state = shadow.get("state")
        if isinstance(state, dict):
            rep = state.get("reported")
            if isinstance(rep, dict):
                absorb(rep)
            des = state.get("desired")
            if isinstance(des, dict):
                absorb(des)
        else:
            rep = shadow.get("reported")
            if isinstance(rep, dict):
                absorb(rep)

    reported = device.get("reported")
    if isinstance(reported, dict):
        absorb(reported)

    config = device.get("config")
    if isinstance(config, dict):
        absorb(config)

    return merged


def _state_from_device(device: dict[str, Any]) -> dict[str, Any]:
    flat = _merge_reported_state(device)
    is_on = None
    for key in ("power", "on", "active", "isOn", "is_on", "enabled"):
        if key in flat or key in device:
            raw = flat.get(key, device.get(key))
            is_on = _coerce_bool(raw)
            if is_on is not None:
                break

    intensity = _coerce_int(flat.get("intensity", device.get("intensity")))

    return {"is_on": is_on, "intensity": intensity, "shadow": flat}


def _parse_scent_list_reported(reported: Any) -> list[tuple[int, int]]:
    """Parse shadow `list` reported value: [rfid, level%, rfid, level%, ...]."""
    if reported is None:
        return []
    if isinstance(reported, str):
        try:
            arr = json.loads(reported)
        except json.JSONDecodeError:
            return []
    elif isinstance(reported, list):
        arr = reported
    else:
        return []
    pairs: list[tuple[int, int]] = []
    for i in range(0, len(arr), 2):
        if i + 1 >= len(arr):
            break
        try:
            sid = int(arr[i])
            lvl = int(arr[i + 1])
            pairs.append((sid, lvl))
        except (TypeError, ValueError):
            continue
    return pairs


class KuniApi:
    """Async client for Kuni / Aroma Republic device API."""

    def __init__(
        self,
        session: ClientSession,
        *,
        base_url: str,
        organization_id: str,
        access_token: str = "",
        id_token: str = "",
        refresh_token: str | None = None,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._organization_id = organization_id.strip()
        self._access_token = _strip_bearer(access_token)
        self._id_token = _strip_bearer(id_token)
        self._refresh_token: str | None = (
            _strip_bearer(refresh_token) if refresh_token else None
        )
        self._scent_titles: dict[str, str] = {}
        self._scent_titles_expires: float = 0.0

    def has_valid_tokens(self) -> bool:
        return bool(self._access_token and self._id_token)

    async def async_ensure_tokens(self, *, force: bool = False) -> None:
        """Refresh Cognito access/id tokens when a refresh token is configured."""
        if not self._refresh_token:
            return
        if (
            not force
            and self.has_valid_tokens()
            and not token_needs_refresh(self._access_token)
        ):
            return
        refreshed = await async_refresh_tokens(self._session, self._refresh_token)
        self._access_token = refreshed["access_token"]
        self._id_token = refreshed["id_token"]

    def _headers(self) -> dict[str, str]:
        # Match mobile app (Charles): lowercase organizationid / idtoken
        return {
            "Authorization": f"Bearer {self._access_token}",
            "organizationid": self._organization_id,
            "idtoken": self._id_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _api_url(self, path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{self._base}{p}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, str] | None = None,
        _retry_auth: bool = True,
    ) -> Any:
        url = self._api_url(path)
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                params=params,
            ) as resp:
                text = await resp.text()
                if resp.status == 401 and _retry_auth and self._refresh_token:
                    try:
                        await self.async_ensure_tokens(force=True)
                    except Exception:
                        _LOGGER.debug("Token refresh after 401 failed", exc_info=True)
                        raise ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=resp.status,
                            message=text[:200],
                        ) from None
                    return await self._request(
                        method,
                        path,
                        json_body=json_body,
                        params=params,
                        _retry_auth=False,
                    )
                if resp.status >= 400:
                    _LOGGER.debug(
                        "API error %s %s: %s", resp.status, url, text[:500]
                    )
                    raise ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message=text[:200],
                    )
                if not text.strip():
                    return None
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        except ClientError:
            _LOGGER.debug("Request failed %s %s", method, url, exc_info=True)
            raise

    async def async_validate(self) -> bool:
        """Return True if credentials work (device list loads)."""
        try:
            await self.async_ensure_tokens()
            raw = await self.async_get_devices_raw()
            return isinstance(raw, (list, dict))
        except (ClientResponseError, ClientError, OSError):
            return False

    async def async_get_devices_raw(
        self,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """GET /devices — raw JSON (list or envelope)."""
        await self.async_ensure_tokens()
        data = await self._request(
            "GET",
            f"{API_PREFIX}/devices/",
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("devices", "data", "items", "results"):
                inner = data.get(key)
                if isinstance(inner, list):
                    return inner
            return data
        return []

    @staticmethod
    def _pick_device(
        candidates: list[dict[str, Any]],
        device_id: str,
    ) -> dict[str, Any] | None:
        want = device_id.strip()
        for d in candidates:
            if device_entry_id(d) == want:
                return d
        return None

    async def async_list_devices(self) -> list[dict[str, Any]]:
        """Devices returned by GET /devices/, sorted by display label."""
        raw = await self.async_get_devices_raw()
        entries = [d for d in device_entries_from_raw(raw) if device_entry_id(d)]
        entries.sort(key=lambda d: device_display_label(d).lower())
        return entries

    async def async_get_device(self, device_id: str) -> dict[str, Any] | None:
        """Return one device object from GET /devices/ by UUID."""
        raw = await self.async_get_devices_raw()
        candidates = device_entries_from_raw(raw)
        return self._pick_device(candidates, device_id)

    async def async_get_scent_titles(self) -> dict[str, str]:
        """Map scent RFID (string) to display title from /scent/configuration/."""
        now = time.monotonic()
        if self._scent_titles and now < self._scent_titles_expires:
            return self._scent_titles

        await self.async_ensure_tokens()
        data = await self._request(
            "GET",
            f"{API_PREFIX}/scent/configuration/",
        )
        catalog: dict[str, str] = {}
        scents = data.get("scents") if isinstance(data, dict) else None
        if isinstance(scents, list):
            for item in scents:
                if not isinstance(item, dict):
                    continue
                rfid = item.get("rfid")
                title = item.get("title")
                if rfid is not None and title:
                    catalog[str(rfid)] = str(title)

        self._scent_titles = catalog
        self._scent_titles_expires = now + SCENT_CATALOG_TTL_SEC
        return catalog

    async def async_get_shadow_fields(self, device_id: str) -> list[dict[str, Any]]:
        """GET device shadow document (array of field objects)."""
        await self.async_ensure_tokens()
        did = device_id.strip()
        path = f"{API_PREFIX}/devices/{did}/shadow/"
        data = await self._request("GET", path, params={"id": did})
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    def _build_scent_slots(
        self,
        catalog: dict[str, str],
        pairs: list[tuple[int, int]],
    ) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        for i in range(NUM_SCENT_SLOTS):
            if i < len(pairs):
                sid, lvl = pairs[i]
                name = catalog.get(str(sid), f"Scent {sid}")
                slots.append(
                    {"slot": i + 1, "scent_id": sid, "level": lvl, "name": name}
                )
            else:
                slots.append(
                    {"slot": i + 1, "scent_id": None, "level": None, "name": None}
                )
        return slots

    async def async_get_status(self, device_id: str) -> dict[str, Any]:
        """Device state for the coordinator."""
        device = await self.async_get_device(device_id)
        if device is None:
            _LOGGER.warning(
                "Device id %s not found in GET devices response",
                device_id,
            )
            empty_slots = self._build_scent_slots({}, [])
            return {
                "is_on": None,
                "intensity": None,
                "shadow": {},
                "device_name": None,
                "scent_slots": empty_slots,
                "scent_position": None,
            }

        st = _state_from_device(device)
        st["device_name"] = (
            device.get("name")
            or device.get("deviceName")
            or device.get("label")
        )

        scent_slots: list[dict[str, Any]] = self._build_scent_slots({}, [])
        scent_position: int | None = None
        try:
            catalog = await self.async_get_scent_titles()
            fields = await self.async_get_shadow_fields(device_id)
            list_field = next(
                (f for f in fields if f.get("name") == SHADOW_LIST),
                None,
            )
            if list_field is not None:
                reported = list_field.get("reported")
                pairs = _parse_scent_list_reported(reported)
                scent_slots = self._build_scent_slots(catalog, pairs)
            pos_field = next(
                (f for f in fields if f.get("name") == SHADOW_POSITION),
                None,
            )
            if pos_field is not None:
                scent_position = _coerce_int(_shadow_field_value(pos_field))
                if scent_position is not None:
                    scent_position = max(
                        0, min(scent_position, NUM_SCENT_SLOTS - 1)
                    )

            power_field = next(
                (f for f in fields if f.get("name") == SHADOW_POWER),
                None,
            )
            power_raw = _shadow_field_value(power_field)
            if power_raw is not None:
                power_b = _coerce_bool(power_raw)
                if power_b is not None:
                    st["is_on"] = power_b

            intensity_field = next(
                (f for f in fields if f.get("name") == SHADOW_INTENSITY),
                None,
            )
            int_raw = _shadow_field_value(intensity_field)
            if int_raw is not None:
                int_coerced = _coerce_int(int_raw)
                if int_coerced is not None:
                    st["intensity"] = int_coerced
        except (ClientError, ClientResponseError, OSError, TypeError, ValueError) as err:
            _LOGGER.debug("Could not load shadow-derived state: %s", err)

        st["scent_slots"] = scent_slots
        st["scent_position"] = scent_position
        return st

    async def async_set_shadow_value(
        self,
        device_id: str,
        name: str,
        value: int | float | str | bool,
    ) -> None:
        """PUT shadow/update — same body shape as Postman Change Config."""
        await self.async_ensure_tokens()
        did = device_id.strip()
        path = f"{API_PREFIX}/devices/{did}/shadow/update/"
        body = {"name": name, "value": value}
        await self._request(
            "PUT",
            path,
            json_body=body,
            params={"id": did},
        )

    async def async_set_power(self, device_id: str, on: bool) -> None:
        """Turn diffuser on/off via shadow."""
        await self.async_set_shadow_value(
            device_id, SHADOW_POWER, 1 if on else 0
        )

    async def async_set_intensity(self, device_id: str, value: int) -> None:
        """Set intensity via shadow."""
        await self.async_set_shadow_value(device_id, SHADOW_INTENSITY, value)

    async def async_set_scent_position(self, device_id: str, slot_index: int) -> None:
        """Select active cartridge slot (0 .. NUM_SCENT_SLOTS-1)."""
        idx = max(0, min(int(slot_index), NUM_SCENT_SLOTS - 1))
        await self.async_set_shadow_value(device_id, SHADOW_POSITION, idx)
