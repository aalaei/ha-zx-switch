"""Sensors for the ZX510S-4T2XS switch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfDataRate,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import PortStatus, SfpStatus
from .coordinator import PortRates, ZxSwitchConfigEntry, ZxSwitchCoordinator, ZxSwitchData
from .entity import ZxPortEntity, ZxSwitchEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ZxSensorDescription(SensorEntityDescription):
    """Switch-wide sensor."""

    value_fn: Callable[[ZxSwitchData], float | int | datetime | None]


@dataclass(frozen=True, kw_only=True)
class ZxPortSensorDescription(SensorEntityDescription):
    """Per-port sensor."""

    value_fn: Callable[[PortStatus, PortRates], float | int | None]


@dataclass(frozen=True, kw_only=True)
class ZxSfpSensorDescription(SensorEntityDescription):
    """SFP digital diagnostics (DDM) reading."""

    value_fn: Callable[[SfpStatus], float | None]


SYSTEM_SENSORS: tuple[ZxSensorDescription, ...] = (
    ZxSensorDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.state.cpu_usage,
    ),
    ZxSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.state.memory_usage,
    ),
    ZxSensorDescription(
        key="boot_time",
        translation_key="boot_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.boot_time,
    ),
    ZxSensorDescription(
        key="ports_up",
        translation_key="ports_up",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: sum(1 for p in d.state.ports if p.link),
    ),
)

PORT_SENSORS: tuple[ZxPortSensorDescription, ...] = (
    ZxPortSensorDescription(
        key="link_speed",
        translation_key="link_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        value_fn=lambda p, r: p.speed,
    ),
    ZxPortSensorDescription(
        key="rx_rate",
        translation_key="rx_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        value_fn=lambda p, r: r.rx,
    ),
    ZxPortSensorDescription(
        key="tx_rate",
        translation_key="tx_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        value_fn=lambda p, r: r.tx,
    ),
    ZxPortSensorDescription(
        key="rx_bytes",
        translation_key="rx_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        value_fn=lambda p, r: p.rx_bytes,
    ),
    ZxPortSensorDescription(
        key="tx_bytes",
        translation_key="tx_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        value_fn=lambda p, r: p.tx_bytes,
    ),
    ZxPortSensorDescription(
        key="rx_packets",
        translation_key="rx_packets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda p, r: p.rx_packets,
    ),
    ZxPortSensorDescription(
        key="tx_packets",
        translation_key="tx_packets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda p, r: p.tx_packets,
    ),
    ZxPortSensorDescription(
        key="rx_errors",
        translation_key="rx_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p, r: p.rx_errors,
    ),
    ZxPortSensorDescription(
        key="rx_discards",
        translation_key="rx_discards",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda p, r: p.counters.get("ifInDiscards"),
    ),
    ZxPortSensorDescription(
        key="tx_discards",
        translation_key="tx_discards",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda p, r: p.counters.get("ifOutDiscards"),
    ),
)

SFP_SENSORS: tuple[ZxSfpSensorDescription, ...] = (
    ZxSfpSensorDescription(
        key="sfp_temperature",
        translation_key="sfp_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.temperature,
    ),
    ZxSfpSensorDescription(
        key="sfp_voltage",
        translation_key="sfp_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.voltage,
    ),
    ZxSfpSensorDescription(
        key="sfp_bias_current",
        translation_key="sfp_bias_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.bias_current,
    ),
    ZxSfpSensorDescription(
        key="sfp_tx_power",
        translation_key="sfp_tx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.tx_power,
    ),
    ZxSfpSensorDescription(
        key="sfp_rx_power",
        translation_key="sfp_rx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.rx_power,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZxSwitchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    state = coordinator.data.state
    entities: list[SensorEntity] = [ZxSensor(coordinator, d) for d in SYSTEM_SENSORS]
    entities += [ZxTemperatureSensor(coordinator, name) for name in state.temperatures]
    entities += [ZxFanSensor(coordinator, name) for name in state.fans]
    for port in state.ports:
        entities += [ZxPortSensor(coordinator, port, d) for d in PORT_SENSORS]
        if port.sfp is not None:
            entities.append(ZxSfpModuleSensor(coordinator, port))
            entities += [ZxSfpSensor(coordinator, port, d) for d in SFP_SENSORS]
    async_add_entities(entities)


class ZxSensor(ZxSwitchEntity, SensorEntity):
    """Switch-wide sensor."""

    entity_description: ZxSensorDescription

    def __init__(self, coordinator: ZxSwitchCoordinator, description: ZxSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | datetime | None:
        return self.entity_description.value_fn(self.coordinator.data)


class ZxTemperatureSensor(ZxSwitchEntity, SensorEntity):
    """One of the switch's temperature probes (CPU, chassis, PHY)."""

    _attr_translation_key = "temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: ZxSwitchCoordinator, probe: str) -> None:
        super().__init__(coordinator, f"temperature_{probe.lower()}")
        self._probe = probe
        self._attr_translation_placeholders = {"probe": probe}

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.state.temperatures.get(self._probe)


class ZxFanSensor(ZxSwitchEntity, SensorEntity):
    """Fan speed."""

    _attr_translation_key = "fan_speed"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = REVOLUTIONS_PER_MINUTE

    def __init__(self, coordinator: ZxSwitchCoordinator, fan: str) -> None:
        super().__init__(coordinator, f"fan_{fan.lower()}")
        self._fan = fan
        self._attr_translation_placeholders = {"fan": fan}

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.state.fans.get(self._fan)


class ZxPortSensor(ZxPortEntity, SensorEntity):
    """Per-port sensor."""

    entity_description: ZxPortSensorDescription

    def __init__(
        self,
        coordinator: ZxSwitchCoordinator,
        port: PortStatus,
        description: ZxPortSensorDescription,
    ) -> None:
        super().__init__(coordinator, port, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        port = self.port
        if port is None:
            return None
        rates = self.coordinator.data.rates.get(self.port_index, PortRates())
        return self.entity_description.value_fn(port, rates)


class ZxSfpSensor(ZxPortEntity, SensorEntity):
    """SFP DDM reading. Many DACs and cheap modules don't report DDM."""

    entity_description: ZxSfpSensorDescription

    def __init__(
        self,
        coordinator: ZxSwitchCoordinator,
        port: PortStatus,
        description: ZxSfpSensorDescription,
    ) -> None:
        super().__init__(coordinator, port, description.key)
        self.entity_description = description
        # Don't clutter the UI with readings the inserted module can't give.
        if port.sfp is None or description.value_fn(port.sfp) is None:
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | None:
        port = self.port
        if port is None or port.sfp is None:
            return None
        return self.entity_description.value_fn(port.sfp)


class ZxSfpModuleSensor(ZxPortEntity, SensorEntity):
    """Part number of the inserted transceiver, with EEPROM details as attributes."""

    _attr_translation_key = "sfp_module"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZxSwitchCoordinator, port: PortStatus) -> None:
        super().__init__(coordinator, port, "sfp_module")

    @property
    def native_value(self) -> str | None:
        sfp = self.port.sfp if self.port else None
        if sfp is None or not sfp.present:
            return "none"
        return sfp.module.get("part_number") or "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        sfp = self.port.sfp if self.port else None
        if sfp is None or not sfp.present:
            return None
        return {k: v for k, v in sfp.module.items() if v is not None}
