"""Tests for the switch client."""

from __future__ import annotations

from urllib.parse import parse_qsl

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.zx_switch.api import (
    SwitchAuthError,
    SwitchClient,
    parse_fans,
    parse_float,
    parse_lang,
    parse_temperatures,
    parse_uptime,
)

from .conftest import HOST, PASSWORD, USERNAME, FakeSwitch


def test_parsers() -> None:
    assert parse_lang("lang('diag','lblNS')") == ("lblNS", [])
    assert parse_lang("lang('port','txtMediaGCopper',[10])") == ("txtMediaGCopper", ["10"])
    assert parse_lang("plain") is None
    assert parse_uptime("lang('sys','txtSysUptimeArg',[2,21,4,55])") == 2 * 86400 + 21 * 3600 + 4 * 60 + 55
    assert parse_temperatures("CPU 51.0C, Chassis 36.50C, PHY 36.50C ") == {
        "CPU": 51.0,
        "Chassis": 36.5,
        "PHY": 36.5,
    }
    assert parse_fans("FAN1 2293RPM") == {"FAN1": 2293}
    assert parse_float("lang('diag','lblNS')") is None
    assert parse_float("-2.35") == -2.35
    assert parse_float("35.6 C") == 35.6


def _client(hass: HomeAssistant, password: str = PASSWORD) -> SwitchClient:
    return SwitchClient(async_get_clientsession(hass), HOST, USERNAME, password)


async def test_state(hass: HomeAssistant, fake_switch: FakeSwitch) -> None:
    client = _client(hass)
    info = await client.async_get_system_info()
    assert info.model == "ZX510S-4T2XS"
    assert info.firmware_version == "1.1.1.34"
    assert info.mac == "02:00:00:00:00:01"

    state = await client.async_get_state()
    assert fake_switch.logins == 1
    assert state.temperatures == {"CPU": 51.25, "Chassis": 36.75, "PHY": 36.75}
    assert state.fans["FAN1"] > 0
    assert state.memory_usage == 66
    assert [p.name for p in state.ports] == ["TE1", "TE2", "TE3", "TE4", "TE5", "TE6"]
    assert [p.media for p in state.ports] == ["copper"] * 4 + ["fiber"] * 2
    assert [p.link for p in state.ports] == [False, False, False, True, True, True]
    assert state.ports[3].speed == 10000
    assert state.ports[0].speed == 0
    assert state.ports[3].rx_bytes > 0
    assert state.ports[0].sfp is None
    sfp = state.ports[4].sfp
    assert sfp is not None and sfp.present and not sfp.loss_of_signal
    assert sfp.temperature is None  # DAC: no DDM
    assert sfp.module["part_number"] == "SFP-H10G-CU1M"
    assert sfp.module["vendor"] == "OEM"


async def test_bad_password(hass: HomeAssistant, fake_switch: FakeSwitch) -> None:
    with pytest.raises(SwitchAuthError):
        await _client(hass, "wrong").async_login()


async def test_session_expiry_relogs(hass: HomeAssistant, fake_switch: FakeSwitch) -> None:
    client = _client(hass)
    await client.async_get_state()
    fake_switch.expire_next = True
    state = await client.async_get_state()
    assert fake_switch.logins == 2
    assert state.temperatures


async def test_set_port_enabled_preserves_settings(hass: HomeAssistant, fake_switch: FakeSwitch) -> None:
    client = _client(hass)
    await client.async_set_port_enabled(0, True)
    await client.async_set_port_enabled(4, False)

    assert [cmd for cmd, _ in fake_switch.posts] == ["port_portEdit", "port_portEdit"]
    assert parse_qsl(fake_switch.posts[0][1], keep_blank_values=True) == [
        ("_ds", "1"),
        ("portList", "TE1"),
        ("descp", ""),
        ("adminStatus", "on"),
        ("adminSpeed", "auto"),
        ("adminDuplex", "auto"),
        ("adminFlowCtrl", "disable"),
        ("_de", "1"),
    ]
    # SFP+ port: no flow control field, adminStatus omitted = disabled.
    assert parse_qsl(fake_switch.posts[1][1], keep_blank_values=True) == [
        ("_ds", "1"),
        ("portList", "TE5"),
        ("descp", ""),
        ("adminSpeed", "auto"),
        ("adminDuplex", "auto"),
        ("_de", "1"),
    ]


async def test_reboot_and_save(hass: HomeAssistant, fake_switch: FakeSwitch) -> None:
    client = _client(hass)
    await client.async_save_config()
    await client.async_reboot()
    assert fake_switch.posts == [("sys_reboot", "_ds=1&empty=1&_de=1")]
