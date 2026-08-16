"""Mute-Switch fuer die SwitchBot Video Doorbell (mute-fuer-n-Zeit)."""
from __future__ import annotations

import time

import voluptuous as vol
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import compute_mute_until_ms
from .const import (
    ATTR_MINUTES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    DEFAULT_MUTE_MINUTES,
    DOMAIN,
    PROP_MUTE,
    SERVICE_MUTE_FOR,
)
from .coordinator import SwitchBotDoorbellCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SwitchBotDoorbellCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([SwitchBotMuteSwitch(coordinator, entry)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_MUTE_FOR,
        {vol.Required(ATTR_MINUTES): vol.All(vol.Coerce(int), vol.Range(min=1))},
        "mute_for",
    )


class SwitchBotMuteSwitch(CoordinatorEntity[SwitchBotDoorbellCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "mute"
    _attr_icon = "mdi:bell-off"

    def __init__(self, coordinator: SwitchBotDoorbellCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_mute"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.data.get(CONF_DEVICE_NAME, "SwitchBot Video Doorbell"),
            manufacturer="SwitchBot",
            model="Video Doorbell",
        )

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        mute_until = self.coordinator.data.get("mute_until_ms") or 0
        return mute_until > int(time.time() * 1000)

    @property
    def extra_state_attributes(self) -> dict:
        mute_until = (self.coordinator.data or {}).get("mute_until_ms")
        return {"mute_until_ms": mute_until}

    async def async_turn_on(self, **kwargs) -> None:
        await self.mute_for(DEFAULT_MUTE_MINUTES)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_invoke(PROP_MUTE, 0)

    async def mute_for(self, minutes: int) -> None:
        await self.coordinator.async_invoke(PROP_MUTE, compute_mute_until_ms(minutes))
