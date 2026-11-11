# Kuni (Aroma Republic) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/taltaub22/Kuni-HomeAssistant?display_name=tag&sort=semver)](https://github.com/taltaub22/Kuni-HomeAssistant/releases)

Custom integration for **Kuni** diffusers using the Aroma Republic mobile API (Cognito login, device shadow).

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=taltaub22&repository=Kuni-HomeAssistant&category=integration)

1. Click the button above, or in **HACS** → **⋮** (top right) → **Custom repositories** add `https://github.com/taltaub22/Kuni-HomeAssistant` with category **Integration**.
2. Search for **Kuni** in HACS and **Download** it.
3. Restart Home Assistant.
4. Add the integration:

   [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=kuni)

   or go to **Settings** → **Devices & services** → **Add integration** → **Kuni**.

### Manual

Copy the `custom_components/kuni` folder into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

Setup uses the config flow (email and password — same account as the Kuni app). **API base URL and organization ID** are set in `custom_components/kuni/const.py` (`KUNI_API_BASE_URL`, `KUNI_ORGANIZATION_ID`); change those if you use another tenant or endpoint.

All devices returned for that account are added automatically.

## Provided entities

Each discovered device exposes:

| Entity | Platform | Description |
| --- | --- | --- |
| Power | `switch` | Turn the diffuser on/off. |
| Intensity | `number` | Diffusion intensity (1–7). |
| Current scent | `select` | Active cartridge position. |
| Slot 1–3 | `sensor` | Cartridge fill level (%) per slot, with scent name in attributes. |
| Time Left | `sensor` | Seconds remaining on the run timer (duration). |

### Service `kuni.set_timer`

Sets the **run timer** via shadow **`power`** with **seconds** as the value (**0–86400**; **0** = off / clear), matching the device API.

Choose the **Kuni device** (Targets → **Device** in the UI, or `device_id` in YAML). **Duration** is always required in `data`.

```yaml
service: kuni.set_timer
target:
  device_id: abc123your_ha_device_id
data:
  duration_seconds: 3600
```

## Requirements

- Home Assistant with Brands support (for the integration icon in the UI, **2026.3+** recommended).
- Dependency **`pycognito`** is installed automatically from `manifest.json`.

## Support

Use [GitHub Issues](https://github.com/taltaub22/Kuni-HomeAssistant/issues) for bugs and feature requests.

## Disclaimer

This is a community integration and is not affiliated with Aroma Republic or Kuni.
