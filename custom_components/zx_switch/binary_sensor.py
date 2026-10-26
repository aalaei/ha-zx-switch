"""Binary sensors for the ZX510S-4T2XS switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import PortStatus
from .coordinator import ZxSwitchConfigEntry, ZxSwitchCoordinator
from .entity import ZxPortEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZxSwitchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for port in coordinator.data.state.ports:
        entities.append(ZxPortLinkSensor(coordinator, port))
        if port.sfp is not None:
            entities += [ZxSfpPresentSensor(coordinator, port), ZxSfpLosSensor(coordinator, port)]
    async_add_entities(entities)


class ZxPortLinkSensor(ZxPortEntity, BinarySensorEntity):
    """Whether the port has link."""

    _attr_translation_key = "link"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ZxSwitchCoordinator, port: PortStatus) -> None:
        super().__init__(coordinator, port, "link")

    @property
    def is_on(self) -> bool | None:
        return self.port.link if self.port else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        port = self.port
        if port is None:
            return None
        attrs: dict[str, Any] = {"media": port.media}
        if port.description:
            attrs["description"] = port.description
        if port.link and port.full_duplex is not None:
            attrs["duplex"] = "full" if port.full_duplex else "half"
        return attrs


class ZxSfpPresentSensor(ZxPortEntity, BinarySensorEntity):
    """Whether a transceiver is inserted in the cage."""

    _attr_translation_key = "sfp_present"
    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZxSwitchCoordinator, port: PortStatus) -> None:
        super().__init__(coordinator, port, "sfp_present")

    @property
    def is_on(self) -> bool | None:
        sfp = self.port.sfp if self.port else None
        return sfp.present if sfp else None


class ZxSfpLosSensor(ZxPortEntity, BinarySensorEntity):
    """Loss of signal reported by the transceiver."""

    _attr_translation_key = "sfp_los"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZxSwitchCoordinator, port: PortStatus) -> None:
        super().__init__(coordinator, port, "sfp_los")

    @property
    def is_on(self) -> bool | None:
        sfp = self.port.sfp if self.port else None
        return sfp.loss_of_signal if sfp and sfp.present else None
