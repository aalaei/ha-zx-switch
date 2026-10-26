"""Polling coordinator for the ZX510S-4T2XS switch."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SwitchAuthError, SwitchClient, SwitchError, SwitchState, SystemInfo
from .const import BOOT_TIME_TOLERANCE, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type ZxSwitchConfigEntry = ConfigEntry[ZxSwitchCoordinator]


@dataclass
class PortRates:
    """Throughput derived from two consecutive counter readings, in bit/s."""

    rx: float | None = None
    tx: float | None = None


@dataclass
class ZxSwitchData:
    """Coordinator payload: raw state plus derived values."""

    state: SwitchState
    boot_time: datetime | None
    rates: dict[int, PortRates] = field(default_factory=dict)


class ZxSwitchCoordinator(DataUpdateCoordinator[ZxSwitchData]):
    """Fetches switch state on an interval."""

    config_entry: ZxSwitchConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ZxSwitchConfigEntry,
        client: SwitchClient,
        info: SystemInfo,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.info = info
        self._last_counters: dict[int, tuple[float, int | None, int | None]] = {}
        self._boot_time: datetime | None = None

    async def _async_update_data(self) -> ZxSwitchData:
        try:
            state = await self.client.async_get_state()
        except SwitchAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SwitchError as err:
            raise UpdateFailed(str(err)) from err

        now = time.monotonic()
        rates: dict[int, PortRates] = {}
        for port in state.ports:
            prev = self._last_counters.get(port.index)
            rates[port.index] = PortRates(
                rx=_rate(prev[1] if prev else None, port.rx_bytes, prev[0] if prev else None, now),
                tx=_rate(prev[2] if prev else None, port.tx_bytes, prev[0] if prev else None, now),
            )
            self._last_counters[port.index] = (now, port.rx_bytes, port.tx_bytes)

        if state.uptime is not None:
            boot = dt_util.utcnow() - timedelta(seconds=state.uptime)
            if self._boot_time is None or abs(boot - self._boot_time) > BOOT_TIME_TOLERANCE:
                self._boot_time = boot.replace(microsecond=0)

        return ZxSwitchData(state=state, boot_time=self._boot_time, rates=rates)


def _rate(prev: int | None, curr: int | None, prev_time: float | None, now: float) -> float | None:
    """Bits per second between two byte counters; None after a reset or on first poll."""
    if prev is None or curr is None or prev_time is None or curr < prev:
        return None
    elapsed = now - prev_time
    if elapsed <= 0:
        return None
    return (curr - prev) * 8 / elapsed
