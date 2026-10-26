"""The ZX510S-4T2XS 10G managed switch integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SwitchAuthError, SwitchClient, SwitchError
from .coordinator import ZxSwitchConfigEntry, ZxSwitchCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ZxSwitchConfigEntry) -> bool:
    """Set up the switch from a config entry."""
    client = SwitchClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    try:
        info = await client.async_get_system_info()
    except SwitchAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SwitchError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = ZxSwitchCoordinator(hass, entry, client, info)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZxSwitchConfigEntry) -> bool:
    """Unload a config entry and free the switch session."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.async_logout()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: ZxSwitchConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
