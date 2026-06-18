# Провижионинг устройств

Шаблоны конфигурации (Jinja2) и применение на сетевые устройства через SSH.

## Возможности

- **Шаблоны** — Jinja2 с переменными из инвентаря (`device.name`, `device.ip`, `site`, `group`, `role`, `tags`)
- **Preview** — рендер без применения (dry-run)
- **Apply** — push конфигурации на устройство с записью в `provision_runs` и audit
- **Модели**:
  - `routeros` — SFTP + `/import` (как MikroTik restore)
  - `ios` / `iosxe` / `nxos` / `asa` — `configure terminal` + `write memory`
  - `junos` — `configure` + `commit and-quit`
  - прочие — построчное выполнение команд по SSH

## Переменные шаблона

```jinja2
/system identity set name={{ device.name }}
# site={{ site }} group={{ group }}
```

Доступны: `device` (dict), `name`, `ip`, `group`, `site`, `role`, плюс `extra_vars` из API.

## API

| Метод | URL | Права |
|-------|-----|-------|
| GET/POST | `/api/provisioning/templates` | `provision:read` / POST: `provision:run` |
| GET/PUT/DELETE | `/api/provisioning/templates/{id}` | read / run |
| POST | `/api/provisioning/preview` | `provision:read` |
| POST | `/api/provisioning/run` | `provision:run` |
| GET | `/api/provisioning/runs` | `provision:read` |

### Preview

```bash
curl -s -b cookies.txt -X POST http://scanner:8000/api/provisioning/preview \
  -H "Content-Type: application/json" \
  -d '{"template_slug":"routeros-identity","device_name":"ROUTER-01"}'
```

### Apply (dry-run)

```bash
curl -s -b cookies.txt -X POST http://scanner:8000/api/provisioning/run \
  -H "Content-Type: application/json" \
  -d '{"template_slug":"routeros-identity","device_name":"ROUTER-01","dry_run":true}'
```

### Apply (production)

Уберите `"dry_run": true` или передайте `"dry_run": false`. Требуется роль operator/admin.

## Web UI

**Провижионинг** в боковом меню: шаблоны, preview, история запусков.

## RBAC

| Permission | Роли |
|------------|------|
| `provision:read` | viewer, operator, admin |
| `provision:run` | operator, admin |

Object scope применяется: operator видит только устройства в своём scope.

## Аудит

- `provision.preview` — preview конфигурации
- `provision.apply` — успешное применение
- `provision.template_create` / `update` / `delete`

## Ограничения

- RouterOS apply требует `OXIDIZED_ENGINE=python` и узел в Oxidized engine
- Cisco/Juniper apply — упрощённый режим (построчные команды); для сложных конфигов используйте короткие шаблоны
- Нет отката (rollback) — используйте бэкапы Oxidized перед apply

## Связанные документы

- [mikrotik-backups.md](mikrotik-backups.md) — restore из UI
- [inventory.md](inventory.md) — теги site/role для шаблонов
- [integrations.md](integrations.md) — автоматизация через API keys
