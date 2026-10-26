"""Buttons for the ZX510S-4T2XS switch."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SwitchClient, SwitchError
from .const import DOMAIN
from .coordinator import ZxSwitchConfigEntry, ZxSwitchCoordinator
from .entity import ZxSwitchEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ZxButtonDescription(ButtonEntityDescription):
    """Switch action."""

    press_fn: Callable[[SwitchClient], Awaitable[None]]


BUTTONS: tuple[ZxButtonDescription, ...] = (
    ZxButtonDescription(
        key="save_config",
        translation_key="save_config",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.async_save_config(),
    ),
    ZxButtonDescription(
        key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.async_reboot(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZxSwitchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ZxButton(coordinator, d) for d in BUTTONS)


class ZxButton(ZxSwitchEntity, ButtonEntity):
    """Triggers an action on the switch."""

    entity_description: ZxButtonDescription

    def __init__(self, coordinator: ZxSwitchCoordinator, description: ZxButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(self.coordinator.client)
        except SwitchError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"error": str(err)},
            ) from err
