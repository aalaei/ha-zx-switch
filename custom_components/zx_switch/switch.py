"""Port enable/disable switches for the ZX510S-4T2XS switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import PortStatus, SwitchError
from .const import DOMAIN
from .coordinator import ZxSwitchConfigEntry, ZxSwitchCoordinator
from .entity import ZxPortEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZxSwitchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ZxPortSwitch(coordinator, port) for port in coordinator.data.state.ports)


class ZxPortSwitch(ZxPortEntity, SwitchEntity):
    """Administrative state of a port.

    Changes go to the running config; press "Save configuration" to keep
    them across reboots.
    """

    _attr_translation_key = "port_enabled"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZxSwitchCoordinator, port: PortStatus) -> None:
        super().__init__(coordinator, port, "enabled")

    @property
    def is_on(self) -> bool | None:
        return self.port.admin_enabled if self.port else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.async_set_port_enabled(self.port_index, enabled)
        except SwitchError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="port_update_failed",
                translation_placeholders={"port": self._attr_translation_placeholders["port"], "error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
