"""Mute-Switch fuer die SwitchBot Video Doorbell (mute-fuer-n-Zeit).

Zwei live gefundene Fallstricke (siehe FINDINGS.md):
1) Die Doorbell braucht ein paar Sekunden, bis ein per func/invoke
   geschriebener Wert im Shadow (shadow/getByIDs) auftaucht - der sofortige
   Refresh nach dem Schreiben liest sonst noch den alten Wert und der Switch
   springt in der UI kurz zurueck. Deshalb: optimistischer lokaler Zustand
   mit Gnadenfrist, der erst weicht, wenn der Server den erwarteten Wert
   bestaetigt oder die Frist ablaeuft.
2) Property 8433 erwartet Unix-SEKUNDEN, nicht Millisekunden wie sonst bei
   dieser API ueblich - ein Millisekunden-Wert ueberschreitet den
   32-Bit-Bereich und wird vom Geraet stillschweigend auf 2147483647 gekappt,
   wodurch der Mute nie aktiv wird (compute_mute_until() in api.py).
"""
from __future__ import annotations

import time

import voluptuous as vol
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import compute_mute_until
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

OPTIMISTIC_GRACE_SECONDS = 15


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
    # Bewusst kein _attr_translation_key: benutzerdefinierte Entity-Namen aus
    # strings.json werden bei custom_components zur Laufzeit nicht zuverlaessig
    # aufgeloest (live beobachtet - die Entity landete sonst namenlos als
    # "switch.eingang", identisch aussehend wie ein fremdes Geraet). Expliziter
    # _attr_name ist unabhaengig vom Uebersetzungssystem.
    _attr_name = "Mute"
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
        self._optimistic_mute_until: int | None = None
        self._optimistic_set_at: float = 0.0

    @property
    def is_on(self) -> bool:
        now_s = int(time.time())
        if self._optimistic_mute_until is not None:
            return self._optimistic_mute_until > now_s
        mute_until = (self.coordinator.data or {}).get("mute_until_s") or 0
        return mute_until > now_s

    @property
    def extra_state_attributes(self) -> dict:
        mute_until = (self.coordinator.data or {}).get("mute_until_s")
        return {"mute_until_s": mute_until}

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._optimistic_mute_until is not None:
            server_value = (self.coordinator.data or {}).get("mute_until_s")
            grace_elapsed = (time.monotonic() - self._optimistic_set_at) > OPTIMISTIC_GRACE_SECONDS
            if server_value == self._optimistic_mute_until or grace_elapsed:
                self._optimistic_mute_until = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs) -> None:
        await self.mute_for(DEFAULT_MUTE_MINUTES)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_mute_until(0)

    async def mute_for(self, minutes: int) -> None:
        await self._set_mute_until(compute_mute_until(minutes))

    async def _set_mute_until(self, value: int) -> None:
        self._optimistic_mute_until = value
        self._optimistic_set_at = time.monotonic()
        self.async_write_ha_state()
        await self.coordinator.async_invoke(PROP_MUTE, value)
