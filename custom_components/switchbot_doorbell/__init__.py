"""SwitchBot Video Doorbell - Batterie, Klingel-Event, Mute-fuer-n-Zeit."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SwitchBotApiClient
from .const import CONF_APP_DEVICE_ID, CONF_SUBTOPIC, DOMAIN
from .coordinator import SwitchBotDoorbellCoordinator
from .mqtt_client import SwitchBotMqttClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = SwitchBotApiClient(session, app_device_id=entry.data[CONF_APP_DEVICE_ID])
    coordinator = SwitchBotDoorbellCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator, "client": client}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    def _on_ring() -> None:
        ring_entity = hass.data[DOMAIN][entry.entry_id].get("ring_entity")
        if ring_entity is not None:
            ring_entity.trigger_ring()

    mqtt_client = SwitchBotMqttClient(
        hass,
        client,
        lambda: coordinator.access_token,
        entry.data.get(CONF_SUBTOPIC, ""),
        _on_ring,
    )
    hass.data[DOMAIN][entry.entry_id]["mqtt_client"] = mqtt_client
    try:
        await mqtt_client.async_start()
    except Exception:  # noqa: BLE001 - MQTT ist experimentell, darf Setup nicht blockieren
        _LOGGER.exception(
            "MQTT-Klingel-Push konnte nicht gestartet werden - Batterie/Mute laufen trotzdem."
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        mqtt_client: SwitchBotMqttClient | None = data.get("mqtt_client")
        if mqtt_client is not None:
            await mqtt_client.async_stop()
    return unload_ok
