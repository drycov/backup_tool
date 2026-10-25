# Platform role: backup_tool

Backup Tool is the **config backup & network compliance product** in the ops ecosystem.

Profile map: [github.com/drycov — Ops platform ecosystem](https://github.com/drycov#-ops-platform-ecosystem)

## Position

```text
inventory / network probes ──► backup_tool (discovery, oxidized, compliance UI)
camera-probe ──► only if camera probing is required (depend, do not copy)
```

## Owns

- Device discovery for backup targets
- Oxidized / MikroTik backup pipelines
- Backup compliance dashboard, notifications, RBAC for backup ops

## Does not own

- CCTV operator UI ([cms](https://github.com/drycov/cms))
- Field Telegram/map UX ([equipment-bot](https://github.com/drycov/equipment-bot))
- Long-term home for ONVIF camera protocol code ([camera-probe](https://github.com/drycov/camera-probe))

## Anti-duplication

1. SNMP/SSH/RouterOS helpers that also appear in equipment-bot should eventually move to a small shared **network-core** package — until then, avoid copy-paste expansion in both directions.
2. Camera probing → depend on `camera-probe`.
3. Equipment registry for CCTV field ops stays in cms/equipment-bot; this tool keeps backup inventory focused on config targets.
