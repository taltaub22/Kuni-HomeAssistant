"""Constants for the Kuni integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "kuni"


def entity_suggested_object_id(device_id: str, *segments: str) -> str:
    rest = "_".join(
        s.replace("-", "_").replace(" ", "_").lower() for s in segments if s
    )
    return f"kuni_{rest}" if rest else f"kuni_{dev}"


# Aroma / Kuni API (stored in config entry)
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_ID_TOKEN: Final = "id_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"

# Config flow (password never persisted)
CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"

# Fixed deployment target (change in const.py for another API host or tenant).
KUNI_API_BASE_URL: Final = "https://api.aroma-republic.co.il"
KUNI_ORGANIZATION_ID: Final = "tenant-98c65ce5-f45e-4c55-919f-b4f70dea36a1"

API_PREFIX: Final = "/mobile-app/api/v1"

# AWS Cognito (from mobile app / Kuni — us-east-1)
COGNITO_REGION: Final = "us-east-1"
COGNITO_USER_POOL_ID: Final = "us-east-1_U27buhZ3D"
COGNITO_CLIENT_ID: Final = "4keodfbcaqvq36nli132rirq23"

# Shadow property names
SHADOW_POWER: Final = "power"
SHADOW_INTENSITY: Final = "intensity"
SHADOW_LIST: Final = "list"
SHADOW_POSITION: Final = "position"  # active cartridge index 0..NUM_SCENT_SLOTS-1

NUM_SCENT_SLOTS: Final = 3
TIMER_MAX_SECONDS: Final = 86400  # max seconds for power-based timer (shadow power value)

SERVICE_SET_TIMER: Final = "set_timer"
SCENT_CATALOG_TTL_SEC: Final = 3600

# Shadow intensity is 0..6; UI uses 1..7 (HA value 1 → device 0).
INTENSITY_DEVICE_MIN: Final = 0
INTENSITY_DEVICE_MAX: Final = 6

PLATFORMS: Final = [
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SELECT,
]
