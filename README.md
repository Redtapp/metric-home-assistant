# Metric for Home Assistant

Home Assistant integration for [Metric](https://metric-app.com) gas tank sensors.
Sign in with your Metric account and every tank in it shows up as a device.

> **Status:** in development. Sign-in is not available yet.

## Installation

Requires Home Assistant 2026.3 or newer.

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/Redtapp/metric-home-assistant` with type **Integration**.
3. Install **Metric** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Metric** and sign in.

Sign-in redirects through `my.home-assistant.io`, which forwards you back to
your own Home Assistant.

## Entities

Each tank is one device with:

| Entity | Unit | Notes |
| --- | --- | --- |
| Gas level | % | |
| Remaining gas | L | Gas level × tank size |
| Average daily consumption | L/d | Unknown until there is enough history |
| Estimated run-out | timestamp | Unknown until there is enough history |
| Low gas | on/off | Uses the low-gas alert set in the Metric app; unknown if none is set |
| Tank size | L | Diagnostic |
| Last reading | timestamp | Diagnostic |
| Battery voltage | V | Diagnostic |
| Temperature | °C | Diagnostic |
| Signal strength | dBm | Diagnostic, disabled by default |

Data is polled from the cloud every 5 minutes. Tanks added to or removed from
the account are picked up automatically; removed tanks become unavailable and
can then be deleted from the device page.

## How it works

- Sign-in uses OAuth 2.0 authorization code with PKCE against
  `https://metric-app.com/auth/redtapp`, as the public client `home-assistant`
  (no client secret). Each sign-in gets its own PKCE verifier.
- The config entry is keyed by the Metric user ID, so the same account can't be added twice, and reauthentication must use the
  same account.
- Data comes from the public API at `https://metric-app.com/openapi/v1`:
  `GET /devices`, then `GET /devices/{id}/telemetry/latest` for each tank.
- Home Assistant refreshes the access token automatically. A rejected refresh
  token or a `401` starts the reauthentication flow.
- Removing the integration revokes its refresh token.
- `custom_components/metric/client.py` has no Home Assistant imports, so it can
  become a standalone PyPI package if the integration moves to Home Assistant core.

## Development

```sh
uv sync --group dev
uv run pytest --cov=custom_components.metric
uv run ruff format . && uv run ruff check .
```

To validate the manifest and translations the same way CI does:

```sh
docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest
```

To try it in a real Home Assistant, copy or symlink `custom_components/metric`
into the `custom_components` folder of your Home Assistant config directory.

## Releasing

1. Bump `version` in `custom_components/metric/manifest.json`.
2. Create a GitHub release (not just a tag) named after the version. HACS offers
   releases as updates.
