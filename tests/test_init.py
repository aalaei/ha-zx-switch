"""Tests for setup and the entities it creates."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FakeSwitch


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, fake_switch: FakeSwitch, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.switch_cpu_temperature").state == "51.25"
    assert hass.states.get("sensor.switch_fan1_speed").state.isdigit()
    assert hass.states.get("sensor.switch_ports_up").state == "3"
    assert hass.states.get("binary_sensor.switch_te4_link").state == STATE_ON
    assert hass.states.get("binary_sensor.switch_te1_link").state == STATE_OFF
    assert hass.states.get("sensor.switch_te4_link_speed").state == "10000"
    assert hass.states.get("switch.switch_te1_enabled").state == STATE_ON
    assert hass.states.get("sensor.switch_te5_sfp_module").state == "SFP-H10G-CU1M"
    assert hass.states.get("binary_sensor.switch_te5_sfp_inserted").state == STATE_ON
    assert hass.states.get("binary_sensor.switch_te5_sfp_loss_of_signal").state == STATE_OFF
    assert hass.states.get("button.switch_restart") is not None

    # A DAC has no DDM, so its readings start disabled.
    registry = er.async_get(hass)
    assert registry.async_get("sensor.switch_te5_sfp_temperature").disabled_by is er.RegistryEntryDisabler.INTEGRATION
    # No rate until two samples exist.
    assert hass.states.get("sensor.switch_te4_download_rate").state == "unknown"

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_port_switch(hass: HomeAssistant, fake_switch: FakeSwitch, config_entry: MockConfigEntry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: "switch.switch_te5_enabled"}, blocking=True
    )
    assert fake_switch.posts[-1][0] == "port_portEdit"
    assert "portList=TE5" in fake_switch.posts[-1][1]
    assert "adminStatus" not in fake_switch.posts[-1][1]


async def test_reboot_button(hass: HomeAssistant, fake_switch: FakeSwitch, config_entry: MockConfigEntry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.switch_restart"}, blocking=True
    )
    assert fake_switch.posts[-1][0] == "sys_reboot"


async def test_bad_credentials_start_reauth(
    hass: HomeAssistant, fake_switch: FakeSwitch, config_entry: MockConfigEntry
) -> None:
    fake_switch.password = "changed"
    await _setup_expect_fail(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def _setup_expect_fail(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
