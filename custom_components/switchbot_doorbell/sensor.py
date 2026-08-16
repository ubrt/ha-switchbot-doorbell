"""Battery-Sensor fuer die SwitchBot Video Doorbell."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import SwitchBotDoorbellCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SwitchBotDoorbellCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([SwitchBotBatterySensor(coordinator, entry)])


class SwitchBotBatterySensor(CoordinatorEntity[SwitchBotDoorbellCoordinator], SensorEntity):
    # Kein _attr_translation_key (siehe switch.py) - der Name kommt hier ueber
    # den device_class-Standardnamen ("Battery"/"Batterie"), nicht ueber
    # strings.json.
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(self, coordinator: SwitchBotDoorbellCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.data.get(CONF_DEVICE_NAME, "SwitchBot Video Doorbell"),
            manufacturer="SwitchBot",
            model="Video Doorbell",
        )

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("battery") if self.coordinator.data else None
