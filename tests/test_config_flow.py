"""Tests for the config flow."""

from __future__ import annotations

import aiohttp

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.zx_switch.const import CONF_SCAN_INTERVAL, DOMAIN

from .conftest import HOST, MAC, PASSWORD, USERNAME, FakeSwitch

USER_INPUT = {CONF_HOST: HOST, CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD}


async def test_user_flow(hass: HomeAssistant, fake_switch: FakeSwitch) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "ZX510S-4T2XS (Switch)"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == MAC.lower()


async def test_user_flow_invalid_auth(hass: HomeAssistant, fake_switch: FakeSwitch) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"http://{HOST}/cgi/get.cgi?cmd=home_login", exc=aiohttp.ClientError)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_already_configured(
    hass: HomeAssistant, fake_switch: FakeSwitch, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, fake_switch: FakeSwitch, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    fake_switch.password = "new-password"
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "new-password"

    # The successful reauth reloads the entry; unload it so its poll timer stops.
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_options(hass: HomeAssistant, fake_switch: FakeSwitch, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 15}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_SCAN_INTERVAL: 15}
