"""Diagnostics for the ZX510S-4T2XS switch."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import ZxSwitchConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "serial", "mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ZxSwitchConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "system": async_redact_data(asdict(coordinator.info), TO_REDACT),
        "state": async_redact_data(asdict(coordinator.data.state), TO_REDACT),
    }
