# Kuni (Aroma Republic) for Home Assistant

Custom integration for **Kuni** diffusers using the Aroma Republic mobile API (Cognito login, device shadow).

## Installation

### HACS

1. Open **HACS** → **⋮** (top right) → **Custom repositories**.
2. Add this repository URL, category **Integration**, then **Add**.
3. Open **HACS** → **Integrations** → **Explore & download repositories**, find **Kuni**, and **Download**.
4. Restart Home Assistant.
5. **Settings** → **Devices & services** → **Add integration** → **Kuni**.

### Manual

Copy the `custom_components/kuni` folder into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

Setup uses the config flow (email and password — same account as the Kuni app). **API base URL and organization ID** are set in `custom_components/kuni/const.py` (`KUNI_API_BASE_URL`, `KUNI_ORGANIZATION_ID`); change those if you use another tenant or endpoint.

All devices returned for that account are added automatically.

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

Use [GitHub Issues](https://github.com/taltaub/kuni-integration/issues) for bugs and feature requests.

## Disclaimer

This is a community integration and is not affiliated with Aroma Republic or Kuni.
