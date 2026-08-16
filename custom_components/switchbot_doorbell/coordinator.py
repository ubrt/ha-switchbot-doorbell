"""DataUpdateCoordinator: pollt Batterie- und Mute-Status per shadow/getByIDs."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SwitchBotApiClient, SwitchBotApiError, SwitchBotAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    PROP_BATTERY,
    PROP_MUTE,
)

_LOGGER = logging.getLogger(__name__)


class SwitchBotDoorbellCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Haelt Access-Token frisch und pollt die relevanten Shadow-Properties."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: SwitchBotApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="switchbot_doorbell",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.entry = entry
        self.client = client
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        self._access_token: str = entry.data[CONF_ACCESS_TOKEN]
        self._refresh_token: str = entry.data[CONF_REFRESH_TOKEN]
        self._user_id: str = entry.data[CONF_USER_ID]

    @property
    def access_token(self) -> str:
        return self._access_token

    async def _async_refresh_token(self) -> None:
        result = await self.client.refresh(self._refresh_token, self._user_id)
        self._access_token = result["access_token"]
        self._refresh_token = result.get("refresh_token", self._refresh_token)
        new_data = {
            **self.entry.data,
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
        }
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)

    async def async_invoke(self, property_id: int, value: Any) -> None:
        """Schreibt eine Property per func/invoke, mit Auto-Refresh bei 401."""
        try:
            await self.client.invoke_func(self._access_token, self.device_id, property_id, value)
        except SwitchBotAuthError:
            await self._async_refresh_token()
            await self.client.invoke_func(self._access_token, self.device_id, property_id, value)
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            try:
                shadow = await self.client.get_shadow(
                    self._access_token, self.device_id, [PROP_BATTERY, PROP_MUTE]
                )
            except SwitchBotAuthError:
                await self._async_refresh_token()
                shadow = await self.client.get_shadow(
                    self._access_token, self.device_id, [PROP_BATTERY, PROP_MUTE]
                )
        except SwitchBotApiError as err:
            raise UpdateFailed(f"SwitchBot-API-Fehler: {err}") from err

        battery = (shadow.get(str(PROP_BATTERY)) or {}).get("value")
        mute_until = (shadow.get(str(PROP_MUTE)) or {}).get("value")
        return {
            "battery": battery,
            "mute_until_ms": mute_until,
        }
