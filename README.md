# ZX510S-4T2XS 10G Managed Switch for Home Assistant

A HACS custom integration for the **ZX510S-4T2XS** managed switch (4× 10GBASE-T + 2× SFP+). It talks to the switch's built-in web interface, so SNMP does not need to be enabled.

Tested on firmware **1.1.1.34** (Mar 29 2025). Other switches running the same "Hydra" web UI (Realtek-based, `System OID 1.3.6.1.4.1.27282`) will probably work too.

## Features

**Switch-wide**
- CPU, chassis and PHY temperature
- Fan speed (RPM)
- CPU and memory usage
- Last boot time
- Number of ports with link

**Per port (TE1–TE6)**
- Link state (with media, duplex and description as attributes)
- Negotiated link speed
- Download/upload throughput, worked out from the byte counters on each poll
- Total bytes received/sent (works with the Energy-style statistics graphs)
- Receive errors (FCS + alignment + symbol)
- Packets and discards (disabled by default)
- **Enable/disable switch** (port admin state)

**SFP+ ports (TE5, TE6)**
- Module inserted, loss of signal
- Module part number, with vendor, serial, type, connector and bit rate as attributes
- DDM readings: temperature, voltage, bias current, TX and RX power. These start disabled when the module doesn't report DDM (DAC cables and many cheap modules don't).

**Buttons**
- Save configuration (running → startup)
- Restart

## Installation

### HACS (one click)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aalaei&repository=ZX510S-4T2XS-ha&category=integration)

Click the button, then **Download**, and restart Home Assistant.

### HACS (by hand)
1. In HACS, open the ⋮ menu → **Custom repositories**.
2. Add `https://github.com/aalaei/ZX510S-4T2XS-ha` with category **Integration**.
3. Install **ZX510S 10G Managed Switch** and restart Home Assistant.

### Manual
Copy `custom_components/zx_switch` into `<config>/custom_components/` and restart Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=zx_switch)

Or go to **Settings → Devices & services → Add integration → ZX510S 10G Managed Switch**, then enter the switch's IP address and its web UI username/password.

The polling interval (default 30 s) can be changed under the integration's **Configure** button. Each poll makes about 13 small HTTP requests.

## Notes and caveats

- **Port switches change the running config only.** Press **Save configuration** to keep changes after a reboot.
- **Don't disable the port Home Assistant uses to reach the switch.** If you do, you'll need another path to the switch, or a power cycle (as long as the change hasn't been saved).
- The switch tracks logins **by client IP address**, not by cookie, and limits the number of concurrent sessions. The integration keeps one session open and logs in again automatically when it expires. If you open the web UI from the Home Assistant host itself, it shares that session.
- The switch's own clock may be wrong (no NTP by default). The *Last boot* sensor is based on Home Assistant's clock and the switch's uptime, so it's unaffected.
- Counters are 64-bit and keep running until a reboot or a manual clear. After a reset, throughput shows *unknown* for one poll.

## How it works

The web UI is a single-page app that calls `cgi/get.cgi?cmd=…` (JSON) and `cgi/set.cgi?cmd=…` (form-encoded `_ds=1&…&_de=1`). On login, the password is RSA-encrypted (PKCS#1 v1.5) with a public key the switch serves. `custom_components/zx_switch/api.py` has no Home Assistant dependency and can be used on its own.

Endpoints used: `home_login`, `home_loginAuth`, `home_loginStatus`, `home_logout`, `home_main`, `sys_sysinfo`, `sys_sysTime`, `sys_cpumem`, `panel_info`, `port_port`, `port_cnt`, `port_portEdit`, `diag_optical`, `diag_opticalIntf`, `home_save`, `sys_reboot`.

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```

Tests run offline against JSON responses captured from a real switch (`tests/fixtures`, with serials and MAC replaced).
