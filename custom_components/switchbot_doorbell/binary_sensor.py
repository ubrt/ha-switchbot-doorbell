"""Klingel-Binary-Sensor - wird per MQTT-Push gesetzt (nicht gepollt).

Schaltet bei einem erkannten Klingel-Event kurz auf 'on' und danach automatisch
wieder auf 'off' (Impuls-Verhalten, wie bei anderen Klingel-Integrationen ueblich).
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN

RING_RESET_SECONDS = 5


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entity = SwitchBotRingBinarySensor(entry)
    hass.data[DOMAIN][entry.entry_id]["ring_entity"] = entity
    async_add_entities([entity])


class SwitchBotRingBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "ring"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_ring"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.data.get(CONF_DEVICE_NAME, "SwitchBot Video Doorbell"),
            manufacturer="SwitchBot",
            model="Video Doorbell",
        )
        self._unsub_reset = None

    @callback
    def trigger_ring(self) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()
        if self._unsub_reset is not None:
            self._unsub_reset()

        @callback
        def _reset(_now) -> None:
            self._attr_is_on = False
            self._unsub_reset = None
            self.async_write_ha_state()

        self._unsub_reset = async_call_later(self.hass, RING_RESET_SECONDS, _reset)
