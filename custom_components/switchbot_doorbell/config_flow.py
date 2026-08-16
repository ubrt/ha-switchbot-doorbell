"""Config flow: Login + automatische Geraete-Erkennung."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SwitchBotApiClient, SwitchBotApiError, decode_user_id_from_jwt
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_APP_DEVICE_ID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_GROUP_ID,
    CONF_PUBTOPIC,
    CONF_REFRESH_TOKEN,
    CONF_SUBTOPIC,
    CONF_USER_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _is_camera_device(device: dict[str, Any]) -> bool:
    detail = device.get("device_detail") or {}
    return bool(detail.get("streamARN")) or detail.get("device_type") == "W1050001"


class SwitchBotDoorbellConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Login -> Gruppe waehlen (falls mehrere) -> Doorbell waehlen (falls mehrere)."""

    VERSION = 1

    def __init__(self) -> None:
        self._app_device_id = str(uuid.uuid4())
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._user_id: str | None = None
        self._groups: list[dict[str, Any]] = []
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = SwitchBotApiClient(session, app_device_id=self._app_device_id)
            try:
                login_result = await client.login(
                    user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
                access_token = login_result.get("access_token")
                refresh_token = login_result.get("refresh_token")
                if not access_token:
                    errors["base"] = "invalid_auth"
                else:
                    self._access_token = access_token
                    self._refresh_token = refresh_token
                    self._user_id = decode_user_id_from_jwt(access_token)

                    groups_result = await client.list_groups(access_token)
                    self._groups = list(groups_result or [])
                    if not self._groups:
                        errors["base"] = "no_groups"
                    elif len(self._groups) == 1:
                        return await self._proceed_with_group(
                            client, self._groups[0]["groupID"]
                        )
                    else:
                        return await self.async_step_group()
            except SwitchBotApiError as err:
                _LOGGER.warning("Login fehlgeschlagen: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_group(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = SwitchBotApiClient(session, app_device_id=self._app_device_id)
            return await self._proceed_with_group(client, user_input[CONF_GROUP_ID])

        options = {g["groupID"]: g.get("groupName", g["groupID"]) for g in self._groups}
        schema = vol.Schema({vol.Required(CONF_GROUP_ID): vol.In(options)})
        return self.async_show_form(step_id="group", data_schema=schema)

    async def _proceed_with_group(
        self, client: SwitchBotApiClient, group_id: str
    ) -> config_entries.ConfigFlowResult:
        assert self._access_token is not None
        devices_result = await client.list_devices(self._access_token, group_id)
        all_devices = list((devices_result or {}).get("devices", []))
        self._devices = [d for d in all_devices if _is_camera_device(d)]
        self._group_id = group_id  # type: ignore[attr-defined]

        if not self._devices:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_SCHEMA,
                errors={"base": "no_doorbell_found"},
            )
        if len(self._devices) == 1:
            return await self._finish(self._devices[0])
        return await self.async_step_device()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            chosen = next(
                d for d in self._devices if d["device_mac"] == user_input[CONF_DEVICE_ID]
            )
            return await self._finish(chosen)

        options = {d["device_mac"]: d.get("device_name", d["device_mac"]) for d in self._devices}
        schema = vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(options)})
        return self.async_show_form(step_id="device", data_schema=schema)

    async def _finish(self, device: dict[str, Any]) -> config_entries.ConfigFlowResult:
        detail = device.get("device_detail") or {}
        device_id = device["device_mac"]

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=device.get("device_name", "SwitchBot Video Doorbell"),
            data={
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_REFRESH_TOKEN: self._refresh_token,
                CONF_USER_ID: self._user_id,
                CONF_APP_DEVICE_ID: self._app_device_id,
                CONF_GROUP_ID: getattr(self, "_group_id", ""),
                CONF_DEVICE_ID: device_id,
                CONF_DEVICE_NAME: device.get("device_name", device_id),
                CONF_SUBTOPIC: detail.get("subtopic", ""),
                CONF_PUBTOPIC: detail.get("pubtopic", ""),
            },
        )
