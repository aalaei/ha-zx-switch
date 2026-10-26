"""Async client for the ZX510S-4T2XS web interface (Hydra/Realtek firmware).

The switch has no documented API. Everything here mirrors what the built-in
web UI does:

* ``GET  /cgi/get.cgi?cmd=<name>`` returns JSON.
* ``POST /cgi/set.cgi?cmd=<name>`` takes a form string ``_ds=1&k=v...&_de=1``.
* Login RSA-encrypts the password (PKCS#1 v1.5) with a modulus served by
  ``home_login`` and then polls ``home_loginStatus`` until it settles.
* Sessions are bound to the client IP address, not to cookies. A response
  of ``{"logout": true}`` means the session expired.

This module has no Home Assistant imports so it can be used on its own.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import json
import logging
import re
import time
from typing import Any
from urllib.parse import quote

import aiohttp
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_LOGGER = logging.getLogger(__name__)

RSA_EXPONENT = 0x10001
LOGIN_POLL_INTERVAL = 0.5
LOGIN_POLL_ATTEMPTS = 30

_LANG_RE = re.compile(r"^lang\('([^']*)','([^']*)'(?:,\[(.*)\])?\)$")
_TEMP_RE = re.compile(r"([A-Za-z0-9_]+)\s+(-?\d+(?:\.\d+)?)\s*C")
_FAN_RE = re.compile(r"([A-Za-z0-9_]+)\s+(\d+)\s*RPM")
_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")

# Counter names as reported by ``port_cnt`` (stripped of stray whitespace).
RX_BYTES = "ifInOctets"
TX_BYTES = "ifOutOctets"
RX_UCAST = "ifInUcastPkts"
RX_NUCAST = "ifInNUcastPkts"
TX_UCAST = "ifOutUcastPkts"
TX_NUCAST = "ifOutNUcastPkts"
RX_DISCARDS = "ifInDiscards"
TX_DISCARDS = "ifOutDiscards"
RX_ERROR_COUNTERS = (
    "dot3StatsFCSErrors",
    "dot3StatsAlignmentErrors",
    "dot3StatsSymbolErrors",
)


class SwitchError(Exception):
    """Generic error talking to the switch."""


class SwitchConnectionError(SwitchError):
    """The switch could not be reached or returned garbage."""


class SwitchAuthError(SwitchError):
    """The switch rejected the credentials."""


def parse_lang(value: Any) -> tuple[str, list[str]] | None:
    """Parse a ``lang('section','key',[args])`` placeholder.

    Returns ``(key, args)`` or ``None`` if the value is not a placeholder.
    """
    if not isinstance(value, str):
        return None
    match = _LANG_RE.match(value.strip())
    if not match:
        return None
    args = [a.strip().strip("'\"") for a in (match.group(3) or "").split(",") if a]
    return match.group(2), args


def parse_uptime(value: Any) -> int | None:
    """Turn ``lang('sys','txtSysUptimeArg',[d,h,m,s])`` into seconds."""
    parsed = parse_lang(value)
    if not parsed or len(parsed[1]) != 4:
        return None
    try:
        days, hours, minutes, seconds = (int(a) for a in parsed[1])
    except ValueError:
        return None
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def parse_temperatures(value: Any) -> dict[str, float]:
    """Parse ``"CPU 51.0C, Chassis 36.50C, PHY 36.50C"``."""
    if not isinstance(value, str):
        return {}
    return {name: float(temp) for name, temp in _TEMP_RE.findall(value)}


def parse_fans(value: Any) -> dict[str, int]:
    """Parse ``"FAN1 2293RPM"``."""
    if not isinstance(value, str):
        return {}
    return {name: int(rpm) for name, rpm in _FAN_RE.findall(value)}


def parse_float(value: Any) -> float | None:
    """Parse a DDM reading; ``lang('diag','lblNS')`` (not supported) gives None."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or parse_lang(value):
        return None
    match = _FLOAT_RE.search(value)
    return float(match.group()) if match else None


def _clean(value: Any) -> str | None:
    """Strip padding from fixed-width SFP EEPROM strings."""
    if not isinstance(value, str) or parse_lang(value):
        return None
    value = value.strip()
    return value or None


@dataclass
class SystemInfo:
    """Static information about the switch."""

    model: str
    hostname: str
    serial: str
    mac: str
    ip_address: str
    firmware_version: str
    firmware_date: str
    loader_version: str
    object_id: str
    location: str
    contact: str


@dataclass
class SfpStatus:
    """Transceiver state of an SFP+ cage."""

    present: bool
    loss_of_signal: bool
    temperature: float | None = None
    voltage: float | None = None
    bias_current: float | None = None
    tx_power: float | None = None
    rx_power: float | None = None
    module: dict[str, str | None] = field(default_factory=dict)


@dataclass
class PortStatus:
    """State of one physical port."""

    index: int
    name: str
    media: str
    link: bool
    speed: int | None
    full_duplex: bool | None
    admin_enabled: bool
    description: str
    counters: dict[str, int] = field(default_factory=dict)
    sfp: SfpStatus | None = None

    @property
    def rx_bytes(self) -> int | None:
        return self.counters.get(RX_BYTES)

    @property
    def tx_bytes(self) -> int | None:
        return self.counters.get(TX_BYTES)

    @property
    def rx_packets(self) -> int | None:
        return _sum(self.counters, (RX_UCAST, RX_NUCAST))

    @property
    def tx_packets(self) -> int | None:
        return _sum(self.counters, (TX_UCAST, TX_NUCAST))

    @property
    def rx_errors(self) -> int | None:
        return _sum(self.counters, RX_ERROR_COUNTERS)


def _sum(counters: dict[str, int], names: tuple[str, ...]) -> int | None:
    values = [counters[n] for n in names if n in counters]
    return sum(values) if values else None


@dataclass
class SwitchState:
    """Everything fetched in one poll."""

    uptime: int | None
    temperatures: dict[str, float]
    fans: dict[str, int]
    cpu_usage: int | None
    memory_usage: int | None
    ports: list[PortStatus]


class SwitchClient:
    """Talks to the switch over its web UI endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        timeout: float = 15,
    ) -> None:
        host = host.strip().removeprefix("http://").removeprefix("https://")
        self._base = f"http://{host.rstrip('/')}"
        self._session = session
        self._username = username
        self._password = password
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()
        self._logged_in = False
        self._port_names: list[str] | None = None

    @property
    def base_url(self) -> str:
        return self._base

    # ------------------------------------------------------------------ HTTP

    async def _http(self, method: str, path: str, body: str | None = None) -> dict[str, Any]:
        sep = "&" if "?" in path else "?"
        url = f"{self._base}/{path}{sep}dummy={int(time.time() * 1000)}"
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if body else None
        try:
            async with self._session.request(
                method, url, data=body, headers=headers, timeout=self._timeout
            ) as resp:
                resp.raise_for_status()
                text = await resp.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SwitchConnectionError(f"Error talking to {self._base}: {err}") from err
        if not text.strip():
            return {}
        try:
            result = json.loads(text)
        except ValueError as err:
            raise SwitchConnectionError(f"Invalid JSON from {path}: {text[:100]!r}") from err
        return result if isinstance(result, dict) else {}

    async def _login(self) -> None:
        info = await self._http("GET", "cgi/get.cgi?cmd=home_login")
        modulus = info.get("data", {}).get("modulus")
        if not modulus:
            raise SwitchConnectionError("Switch did not return an RSA modulus")

        key = rsa.RSAPublicNumbers(RSA_EXPONENT, int(modulus, 16)).public_key()
        encrypted = base64.b64encode(
            key.encrypt(self._password.encode(), padding.PKCS1v15())
        ).decode()
        body = (
            f"_ds=1&username={quote(self._username, safe='')}"
            f"&password={quote(encrypted, safe='')}&_de=1"
        )
        await self._http("POST", "cgi/set.cgi?cmd=home_loginAuth", body)

        for _ in range(LOGIN_POLL_ATTEMPTS):
            status = (await self._http("GET", "cgi/get.cgi?cmd=home_loginStatus")).get("data", {})
            if status.get("status") == "ok":
                self._logged_in = True
                _LOGGER.debug("Logged in to %s", self._base)
                return
            if status.get("status") == "fail":
                reason = parse_lang(status.get("failReason"))
                key_name = reason[0] if reason else str(status.get("failReason"))
                if key_name == "errLoginUserInvalid":
                    raise SwitchAuthError("Invalid username or password")
                if key_name == "errLoginSessionNum":
                    raise SwitchConnectionError("Too many users are logged in to the switch")
                raise SwitchError(f"Login failed: {key_name}")
            await asyncio.sleep(LOGIN_POLL_INTERVAL)
        raise SwitchConnectionError("Timed out waiting for login to complete")

    async def _call(self, method: str, path: str, body: str | None = None) -> dict[str, Any]:
        async with self._lock:
            if not self._logged_in:
                await self._login()
            result = await self._http(method, path, body)
            if result.get("logout"):
                _LOGGER.debug("Session expired (%s), logging in again", result.get("reason"))
                self._logged_in = False
                await self._login()
                result = await self._http(method, path, body)
                if result.get("logout"):
                    raise SwitchAuthError(f"Switch rejected session: {result.get('reason')}")
            return result

    async def _get(self, cmd: str, query: str = "") -> dict[str, Any]:
        return (await self._call("GET", f"cgi/get.cgi?cmd={cmd}{query}")).get("data") or {}

    async def _set(self, cmd: str, fields: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        form = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in fields or [])
        body = f"_ds=1&{form or 'empty=1'}&_de=1"
        result = await self._call("POST", f"cgi/set.cgi?cmd={cmd}", body)
        if result.get("status") not in (None, "ok"):
            raise SwitchError(f"{cmd} failed: {result.get('msg') or result.get('errMsgs') or result}")
        return result

    # ----------------------------------------------------------------- reads

    async def async_login(self) -> None:
        """Log in, raising SwitchAuthError on bad credentials."""
        async with self._lock:
            self._logged_in = False
            await self._login()

    async def async_logout(self) -> None:
        """End the session so it doesn't count against the switch's limit."""
        async with self._lock:
            if not self._logged_in:
                return
            self._logged_in = False
            try:
                await self._http("GET", "cgi/set.cgi?cmd=home_logout")
            except SwitchError:
                pass

    async def async_get_system_info(self) -> SystemInfo:
        data = await self._get("sys_sysinfo")
        main = await self._get("home_main")
        self._port_names = self._physical_ports(main)
        return SystemInfo(
            model=main.get("model") or data.get("model") or "ZX510S-4T2XS",
            hostname=data.get("hostname", ""),
            serial=data.get("syssn", ""),
            mac=data.get("sysMac", ""),
            ip_address=data.get("currIpv4", ""),
            firmware_version=data.get("fwVer", ""),
            firmware_date=data.get("fwDate", ""),
            loader_version=data.get("loaderVer", ""),
            object_id=data.get("sysObjID", ""),
            location=data.get("location", ""),
            contact=data.get("contact", ""),
        )

    @staticmethod
    def _physical_ports(main: dict[str, Any]) -> list[str]:
        ports = [p.get("port", "") for p in main.get("ports", [])]
        lags = len(main.get("lags", []))
        return ports[: len(ports) - lags] if lags else ports

    async def async_get_state(self) -> SwitchState:
        """Fetch all live data."""
        if self._port_names is None:
            self._port_names = self._physical_ports(await self._get("home_main"))

        sys_time = await self._get("sys_sysTime")
        cpumem = await self._get("sys_cpumem")
        panel = (await self._get("panel_info")).get("ports", [])
        config = (await self._get("port_port")).get("ports", [])
        optical = {
            int(p["port"]): p
            for p in (await self._get("diag_optical")).get("ports", [])
            if isinstance(p.get("port"), int)
        }

        ports: list[PortStatus] = []
        for idx, name in enumerate(self._port_names):
            live = panel[idx] if idx < len(panel) else {}
            cfg = config[idx] if idx < len(config) else {}
            port_type = parse_lang(cfg.get("type"))
            is_fiber = idx in optical or (
                port_type is not None and "Fiber" in port_type[0]
            )
            link = bool(live.get("linkup"))
            speed: int | None = None
            if link:
                try:
                    speed = int(live.get("speed"))
                except (TypeError, ValueError):
                    speed = None
            port = PortStatus(
                index=idx,
                name=name,
                media="fiber" if is_fiber else "copper",
                link=link,
                speed=speed if link else 0,
                full_duplex=live.get("dupFull") if link else None,
                admin_enabled=bool(cfg.get("adminStatus", True)),
                description=cfg.get("descp") or "",
                counters=await self._get_counters(idx),
            )
            if idx in optical:
                port.sfp = await self._get_sfp(idx, optical[idx])
            ports.append(port)

        return SwitchState(
            uptime=parse_uptime(sys_time.get("sysUpTime")),
            temperatures=parse_temperatures(sys_time.get("sysCurrTemp")),
            fans=parse_fans(sys_time.get("sysCurrFAN")),
            cpu_usage=cpumem.get("cpu"),
            memory_usage=cpumem.get("mem"),
            ports=ports,
        )

    async def _get_counters(self, idx: int) -> dict[str, int]:
        data = await self._get("port_cnt", f"&selPort={idx}")
        counters: dict[str, int] = {}
        for group in data.get("cnts", []):
            for counter in group.get("cnts", []):
                if isinstance(counter.get("val"), int):
                    counters[str(counter.get("name", "")).strip()] = counter["val"]
        return counters

    async def _get_sfp(self, idx: int, summary: dict[str, Any]) -> SfpStatus:
        insert = parse_lang(summary.get("oe"))
        los = parse_lang(summary.get("los"))
        sfp = SfpStatus(
            present=insert is not None and insert[0] == "lblInsert",
            loss_of_signal=los is None or los[0] != "lblNormal",
            temperature=parse_float(summary.get("temp")),
            voltage=parse_float(summary.get("volt")),
            bias_current=parse_float(summary.get("bias")),
            tx_power=parse_float(summary.get("txPwr")),
            rx_power=parse_float(summary.get("rxPwr")),
        )
        if sfp.present:
            detail = await self._get("diag_opticalIntf", f"&port={idx}")
            sfp.module = {
                "type": _clean(detail.get("trxType")),
                "connector": _clean(detail.get("connectorType")),
                "compliance": _clean(detail.get("ethComplianceCode")),
                "media": _clean(detail.get("transMedia")),
                "wavelength": _clean(detail.get("wavelength")),
                "bitrate": _clean(detail.get("bitrate")),
                "vendor": _clean(detail.get("vendor_name")),
                "vendor_oui": _clean(detail.get("vendor_oui")),
                "part_number": _clean(detail.get("vendor_pn")),
                "revision": _clean(detail.get("vendor_rev")),
                "serial": _clean(detail.get("vendor_sn")),
                "date_code": _clean(detail.get("datecode")),
            }
        return sfp

    # ---------------------------------------------------------------- writes

    async def async_set_port_enabled(self, idx: int, enabled: bool) -> None:
        """Enable or disable a port, keeping its other settings.

        Rebuilds the same form the web UI's port edit dialog submits.
        """
        if self._port_names is None:
            self._port_names = self._physical_ports(await self._get("home_main"))
        cfg = await self._get("port_portEdit", f"&port={idx}&_src={idx}")
        if not cfg:
            raise SwitchError(f"Could not read settings for port {idx}")

        fields = [
            ("portList", self._port_names[idx]),
            ("descp", cfg.get("descp") or ""),
        ]
        if enabled:
            fields.append(("adminStatus", "on"))
        fields += [
            ("adminSpeed", str(cfg.get("adminSpeed", "auto"))),
            ("adminDuplex", str(cfg.get("adminDuplex", "auto"))),
        ]
        if cfg.get("FPort"):
            fields.append(("adminFlowCtrl", str(cfg.get("adminFlowCtrl", "disable"))))
        if cfg.get("TenGi") and not cfg.get("TenGiCopper") and cfg.get("TenGiModeSet"):
            fields.append(("2500M" if cfg.get("TenGiMode2500") else "1000M", "on"))
        await self._set("port_portEdit", fields)

    async def async_save_config(self) -> None:
        """Copy the running config to the startup config."""
        result = await self._call("GET", "cgi/set.cgi?cmd=home_save")
        if result.get("status") not in (None, "ok"):
            raise SwitchError(f"Saving config failed: {result.get('msg') or result}")

    async def async_reboot(self) -> None:
        """Reboot the switch. The connection usually drops mid-request."""
        try:
            await self._set("sys_reboot")
        except SwitchConnectionError:
            pass
        self._logged_in = False
