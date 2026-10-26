"""Base entities for the ZX510S-4T2XS switch."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PortStatus
from .const import DOMAIN, MANUFACTURER
from .coordinator import ZxSwitchCoordinator


class ZxSwitchEntity(CoordinatorEntity[ZxSwitchCoordinator]):
    """An entity attached to the switch device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZxSwitchCoordinator, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.info
        mac = format_mac(info.mac)
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer=MANUFACTURER,
            model=info.model,
            name=info.hostname or info.model,
            serial_number=info.serial or None,
            sw_version=info.firmware_version or None,
            hw_version=f"Loader {info.loader_version}" if info.loader_version else None,
            configuration_url=coordinator.client.base_url,
        )


class ZxPortEntity(ZxSwitchEntity):
    """An entity describing one physical port."""

    def __init__(self, coordinator: ZxSwitchCoordinator, port: PortStatus, key: str) -> None:
        super().__init__(coordinator, f"{port.name.lower()}_{key}")
        self.port_index = port.index
        self._attr_translation_placeholders = {"port": port.name}

    @property
    def port(self) -> PortStatus | None:
        ports = self.coordinator.data.state.ports
        return ports[self.port_index] if self.port_index < len(ports) else None

    @property
    def available(self) -> bool:
        return super().available and self.port is not None
