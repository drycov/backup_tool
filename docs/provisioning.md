# Провижионинг устройств

Шаблоны конфигурации (Jinja2) и применение на сетевые устройства через SSH.

## Возможности

- **Шаблоны** — Jinja2 с переменными из инвентаря (`device.name`, `device.ip`, `site`, `group`, `role`, `tags`)
- **Автогенерация** — шаблоны из конфигов Oxidized по кластерам `group` + `site` + `model`; baseline — наиболее типичный конфиг; outlier-устройства помечаются как «сложные»
- **Bulk provision** — применение шаблона на все устройства `group`/`site` через персистентную task queue (`provision.bulk`)
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
| GET | `/api/provisioning/analysis` | `provision:read` — анализ кластеров без сохранения |
| POST | `/api/provisioning/templates/generate` | `provision:run` — создать/обновить шаблоны из бэкапов |
| GET | `/api/provisioning/bulk?action=preview` | `provision:read` — список устройств для bulk |
| POST | `/api/provisioning/bulk/run` | `provision:run` — запуск bulk (async по умолчанию) |
| GET | `/api/provisioning/bulk` | `provision:read` — история bulk-задач |
| GET | `/api/provisioning/bulk/{id}` | `provision:read` — статус bulk-задачи |
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

### Анализ конфигов (без сохранения)

```bash
curl -s -b cookies.txt "http://scanner:8000/api/provisioning/analysis?group=hex&threshold=0.85&min_devices=2"
```

Ответ: `clusters` (по group/site/model), `complex_devices` — устройства с отклонением от baseline.

### Генерация шаблонов

```bash
curl -s -b cookies.txt -X POST http://scanner:8000/api/provisioning/templates/generate \
  -H "Content-Type: application/json" \
  -d '{"group":"hex","site":"dc1","complexity_threshold":0.85,"min_devices":2,"upsert":true}'
```

Создаёт шаблоны с префиксом slug `gen-...`, поля `source=generated`, `meta` с baseline и списком сложных устройств.

### Bulk provision

```bash
# Preview целевых устройств
curl -s -b cookies.txt "http://scanner:8000/api/provisioning/bulk?action=preview&template_id=1&group=hex&site=dc1&exclude_complex=true"

# Запуск в очередь (dry-run)
curl -s -b cookies.txt -X POST http://scanner:8000/api/provisioning/bulk/run \
  -H "Content-Type: application/json" \
  -d '{"template_id":1,"group":"hex","site":"dc1","dry_run":true,"exclude_complex":true,"async":true}'

# Статус задачи
curl -s -b cookies.txt http://scanner:8000/api/provisioning/bulk/5
```

Задача выполняется worker'ом (`TASK_WORKER_ENABLED`). Каждое устройство получает запись в `provision_runs` с привязкой к `provision_bulk_runs`.

## Web UI

**Провижионинг** в боковом меню: шаблоны, **Генерация из бэкапов**, **Bulk provision**, preview, история запусков и bulk-задач.

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
- `provision.template_generate` — автогенерация из конфигов
- `provision.bulk` — массовое применение шаблона

## Ограничения

- RouterOS apply требует `OXIDIZED_ENGINE=python` и узел в Oxidized engine
- Cisco/Juniper apply — упрощённый режим (построчные команды); для сложных конфигов используйте короткие шаблоны
- Нет отката (rollback) — используйте бэкапы Oxidized перед apply

## Связанные документы

- [mikrotik-backups.md](mikrotik-backups.md) — restore из UI
- [inventory.md](inventory.md) — теги site/role для шаблонов
- [integrations.md](integrations.md) — автоматизация через API keys
