"""Minimal async client for the reverse-engineered SwitchBot cloud API.

Nur die fuer diese Integration benoetigten Endpunkte. Details/Herkunft jedes
Endpunkts stehen in FINDINGS.md im mitm-Repo.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from typing import Any

import aiohttp

from .const import ACCOUNT_HOST, CLIENT_ID, CLIENT_SECRET, GRANT_TYPE, WONDER_HOST

_LOGGER = logging.getLogger(__name__)


class SwitchBotApiError(Exception):
    """Generic API error, message enthaelt die Server-Antwort falls vorhanden."""

    def __init__(self, message: str, result_code: int | None = None) -> None:
        super().__init__(message)
        self.result_code = result_code


class SwitchBotAuthError(SwitchBotApiError):
    """Access-Token abgelaufen/ungueltig, Refresh nötig (oder erneuter Login)."""


def _new_request_id() -> str:
    return str(uuid.uuid4())


def decode_user_id_from_jwt(access_token: str) -> str | None:
    """Liest den userID-Claim direkt aus dem (bereits vertrauenswuerdigen) JWT.

    Keine Signaturpruefung - wir haben das Token ja selbst gerade vom Server
    bekommen, es geht nur darum, das enthaltene Feld ohne Zusatz-Request zu lesen.
    """
    try:
        payload_b64 = access_token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return payload.get("userID")
    except Exception:  # noqa: BLE001 - reine Best-effort-Hilfsfunktion
        return None


class SwitchBotApiClient:
    """Kapselt Login/Refresh/Shadow/Invoke gegen die SwitchBot-Cloud."""

    def __init__(self, session: aiohttp.ClientSession, app_device_id: str | None = None) -> None:
        self._session = session
        # PhoneUtils.d() - App-Install-UUID. Wird pro Config-Entry einmal erzeugt
        # und dauerhaft wiederverwendet (siehe config_flow.py).
        self.app_device_id = app_device_id or str(uuid.uuid4())

    async def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "content-type": "application/json",
            "user-agent": "okhttp/4.12.0",
            "appversion": "10.0.1",
            "versionflag": "10.0.1",
            **headers,
        }
        async with self._session.post(url, headers=headers, json=body) as resp:
            text = await resp.text()
            try:
                data = json.loads(text) if text else {}
            except json.JSONDecodeError:
                raise SwitchBotApiError(f"Ungueltige JSON-Antwort ({resp.status}): {text[:200]}")

            # Gson-Doppelnamen normalisieren (siehe FINDINGS.md Abschnitt 1):
            # body/data und statusCode/resultCode sind gleichbedeutend.
            body_val = data.get("body", data.get("data"))
            result_code = data.get("statusCode", data.get("resultCode"))

            if resp.status >= 400 or (result_code is not None and result_code not in (100, 0)):
                message = data.get("message", "")
                if result_code in (2001, 2005, 2006, 2050, 190):
                    raise SwitchBotAuthError(
                        f"Auth-Fehler (Code {result_code}): {message}", result_code
                    )
                raise SwitchBotApiError(f"API-Fehler (Code {result_code}): {message}", result_code)

            return body_val if body_val is not None else {}

    async def login(self, email: str, password: str) -> dict[str, Any]:
        body = {
            "username": email,
            "password": password,
            "verifyCode": "",
            "clientId": CLIENT_ID,
            "grantType": GRANT_TYPE,
            "deviceInfo": {
                "deviceId": self.app_device_id,
                "deviceName": "",
                "model": "",
                "appVersion": "",
            },
            "dialCode": "",
        }
        headers = {
            "hideLog": "true",
            "uuid": self.app_device_id,
            "requestid": _new_request_id(),
        }
        return await self._post(f"{ACCOUNT_HOST}/account/api/v2/user/login", headers, body)

    async def refresh(self, refresh_token: str, user_id: str) -> dict[str, Any]:
        body = {
            "refreshToken": refresh_token,
            "clientSecret": CLIENT_SECRET,
            "deviceId": self.app_device_id,
            "clientId": CLIENT_ID,
            "userId": user_id,
        }
        headers = {
            "switchbottk": "none",
            "uuid": self.app_device_id,
            "requestid": _new_request_id(),
        }
        return await self._post(f"{ACCOUNT_HOST}/account/api/v1/user/token/refresh", headers, body)

    async def list_groups(self, access_token: str) -> dict[str, Any]:
        headers = {
            "authorization": access_token,
            "uuid": self.app_device_id,
            "requestid": _new_request_id(),
        }
        return await self._post(f"{WONDER_HOST}/groupshare/api/v2/group", headers, {})

    async def list_devices(self, access_token: str, group_id: str) -> dict[str, Any]:
        headers = {
            "authorization": access_token,
            "uuid": self.app_device_id,
            "requestid": _new_request_id(),
        }
        return await self._post(
            f"{WONDER_HOST}/homepage/v1/device/getall", headers, {"groupID": group_id}
        )

    async def get_shadow(
        self, access_token: str, device_id: str, property_ids: list[int]
    ) -> dict[str, Any]:
        headers = {"authorization": access_token}
        return await self._post(
            f"{WONDER_HOST}/device/device/v1/shadow/getByIDs",
            headers,
            {"deviceID": device_id, "propertyIDs": property_ids},
        )

    async def invoke_func(
        self,
        access_token: str,
        device_id: str,
        property_id: int,
        value: Any,
        function_id: int = 1,
    ) -> dict[str, Any]:
        headers = {
            "functionID": str(function_id),
            "authorization": access_token,
        }
        body = {
            "functionID": function_id,
            "requestID": _new_request_id(),
            "optSrc": "app",
            "params": {"0": {str(property_id): value}},
            "deviceID": device_id,
            "notify": {"type": "mqtt", "url": ""},
            "timeout": 20000,
        }
        return await self._post(f"{WONDER_HOST}/command/cmd/api/v1/func/invoke", headers, body)

    async def get_mqtt_cert(self, access_token: str, self_signed: bool = False) -> str:
        """Liefert den base64-PKCS12-Zertifikatsblob (Passwort: '12345678')."""
        headers = {"authorization": access_token}
        result = await self._post(
            f"{WONDER_HOST}/wonder/user/policyCer",
            headers,
            {"MQTTSelfSigned": self_signed},
        )
        if isinstance(result, str):
            return result
        raise SwitchBotApiError(f"Unerwartetes policyCer-Antwortformat: {result!r}")


def compute_mute_until_ms(minutes: int) -> int:
    """Unix-Millisekunden-Zeitstempel, bis zu dem gemutet werden soll."""
    return int(time.time() * 1000) + minutes * 60 * 1000
