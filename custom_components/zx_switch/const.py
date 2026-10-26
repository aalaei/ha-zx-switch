"""Constants for the ZX510S-4T2XS switch integration."""

from datetime import timedelta

DOMAIN = "zx_switch"
MANUFACTURER = "ZX"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

# Boot time recomputed from uptime jitters by a second or two each poll;
# only move the timestamp when it drifts more than this.
BOOT_TIME_TOLERANCE = timedelta(seconds=60)
