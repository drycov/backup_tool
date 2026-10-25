# Platform role: backup_tool

Backup Tool is the **config backup & network compliance product**.

Profile map: https://github.com/drycov#-ops-platform-ecosystem

## Shared libraries

| Library | Usage |
| --- | --- |
| [`network-core`](https://github.com/drycov/network-core) | `scanner/services/network_core_bridge.py` — MikroTik API, vendor labels, geo |

SSH identity probing for backup targets remains product-local (`device_probe.py`) because it uses AutoAddPolicy and Oxidized-oriented model names. Prefer `network-core` for **RouterOS API** reads and shared vendor normalization.

## Does not own

- CCTV operator UI → cms
- Field Telegram/map → equipment-bot
- Camera ONVIF stack → camera-probe
