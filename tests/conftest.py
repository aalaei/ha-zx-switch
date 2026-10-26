"""Fixtures for the ZX510S-4T2XS tests.

The JSON fixtures were captured from a real switch (firmware 1.1.1.34) with
serial numbers and MAC address replaced.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import parse_qs

from cryptography.hazmat.primitives.asymmetric import padding, rsa
import pytest

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.zx_switch.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "192.168.3.23"
BASE = f"http://{HOST}/cgi"
USERNAME = "admin"
PASSWORD = "secret-password"
MAC = "02:00:00:00:00:01"

# Small key keeps the tests fast; the switch uses 1024 bits.
PRIVATE_KEY = rsa.generate_private_key(public_exponent=0x10001, key_size=1024)
MODULUS = format(PRIVATE_KEY.public_key().public_numbers().n, "X")

STATIC_ENDPOINTS = [
    "home_main",
    "sys_sysinfo",
    "sys_sysTime",
    "sys_cpumem",
    "panel_info",
    "port_port",
    "diag_optical",
]


def load(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text()


def decrypt_login(body: str) -> tuple[str, str]:
    """Return (username, password) from a home_loginAuth form body."""
    fields = parse_qs(body)
    password = PRIVATE_KEY.decrypt(base64.b64decode(fields["password"][0]), padding.PKCS1v15())
    return fields["username"][0], password.decode()


class FakeSwitch:
    """Registers the switch's endpoints on an AiohttpClientMocker."""

    def __init__(self, mock: AiohttpClientMocker) -> None:
        self.mock = mock
        self.password = PASSWORD
        self.logins = 0
        self.expire_next = False
        self._pending_ok = False
        self.posts: list[tuple[str, str]] = []

    def register(self) -> None:
        self.mock.get(f"{BASE}/get.cgi?cmd=home_login", json={"data": {"modulus": MODULUS}})
        self.mock.post(f"{BASE}/set.cgi?cmd=home_loginAuth", side_effect=self._login_auth)
        self.mock.get(f"{BASE}/get.cgi?cmd=home_loginStatus", side_effect=self._login_status)
        self.mock.get(f"{BASE}/set.cgi?cmd=home_logout", json={"status": "ok"})
        self.mock.get(f"{BASE}/set.cgi?cmd=home_save", json={"status": "ok", "msgType": "save_success"})
        self.mock.post(f"{BASE}/set.cgi?cmd=port_portEdit", side_effect=self._record_post)
        self.mock.post(f"{BASE}/set.cgi?cmd=sys_reboot", side_effect=self._record_post)
        for idx in range(6):
            self.mock.get(f"{BASE}/get.cgi?cmd=port_cnt&selPort={idx}", text=load(f"port_cnt_{idx}"))
        for idx in (0, 4):
            self.mock.get(
                f"{BASE}/get.cgi?cmd=port_portEdit&port={idx}", text=load(f"port_portEdit_{idx}")
            )
        for idx in (4, 5):
            self.mock.get(
                f"{BASE}/get.cgi?cmd=diag_opticalIntf&port={idx}",
                text=load(f"diag_opticalIntf_{idx}"),
            )
        # sys_sysTime can be told to report an expired session once.
        self.mock.get(f"{BASE}/get.cgi?cmd=sys_sysTime", side_effect=self._sys_time)
        for cmd in STATIC_ENDPOINTS:
            if cmd != "sys_sysTime":
                self.mock.get(f"{BASE}/get.cgi?cmd={cmd}", text=load(cmd))

    async def _login_auth(self, method, url, data):
        username, password = decrypt_login(data)
        self.logins += 1
        self._pending_ok = username == USERNAME and password == self.password
        return AiohttpClientMockResponse(method, url, json={"status": "ok"})

    async def _login_status(self, method, url, data):
        if self._pending_ok:
            body = {"data": {"status": "ok"}}
        else:
            body = {"data": {"status": "fail", "failReason": "lang('login','errLoginUserInvalid')"}}
        return AiohttpClientMockResponse(method, url, json=body)

    async def _sys_time(self, method, url, data):
        if self.expire_next:
            self.expire_next = False
            return AiohttpClientMockResponse(method, url, json={"logout": True, "reason": "timeout"})
        return AiohttpClientMockResponse(method, url, text=load("sys_sysTime"))

    async def _record_post(self, method, url, data):
        self.posts.append((url.query.get("cmd"), data))
        return AiohttpClientMockResponse(method, url, json={"status": "ok", "msgType": "save_success"})


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def fake_switch(aioclient_mock: AiohttpClientMocker) -> FakeSwitch:
    switch = FakeSwitch(aioclient_mock)
    switch.register()
    return switch


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="ZX510S-4T2XS (Switch)",
        unique_id=MAC.lower(),
        data={CONF_HOST: HOST, CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD},
    )


def fixture_json(name: str) -> dict:
    return json.loads(load(name))
