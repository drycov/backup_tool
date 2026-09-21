# Провижионинг устройств

Шаблоны конфигурации (Jinja2) и применение на сетевые устройства через SSH.

## Возможности

- **Шаблоны** — Jinja2 с переменными из инвентаря (`device.name`, `device.ip`, `site`, `group`, `role`, `tags`)
- **Автогенерация** — шаблоны из конфигов Oxidized по кластерам `group` + `site` + `model`; baseline — наиболее типичный конфиг; outlier-устройства помечаются как «сложные»
- **Выделение шаблона** — из baseline берётся устойчивая часть конфигурации (по кластеру), автоматически параметризуются только значения из inventory (`name`, `ip`, `site`, `group`, `role`), а divergent-строки сохраняются в отчёте для ручной проверки
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
| GET | `/api/provisioning/filters` | `provision:read` — group/site/model/устройства из БД |
| GET | `/api/provisioning/analysis` | `provision:read` — анализ кластеров без сохранения (синхронно) |
| POST | `/api/provisioning/analysis/run` | `provision:read` — запуск анализа в фоне |
| GET | `/api/provisioning/analysis/runs/{run_id}` | `provision:read` — статус и лог анализа |
| POST | `/api/provisioning/templates/generate` | `provision:run` — создать/обновить шаблоны (синхронно) |
| POST | `/api/provisioning/templates/generate/run` | `provision:run` — генерация в фоне |
| GET | `/api/provisioning/templates/generate/runs/{run_id}` | `provision:run` — статус и лог генерации |
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
# Синхронный анализ
curl -s -b cookies.txt "http://scanner:8000/api/provisioning/analysis?group=hex&threshold=0.85&min_devices=2"

# Асинхронный анализ с логом (рекомендуется для UI)
curl -s -b cookies.txt -X POST http://scanner:8000/api/provisioning/analysis/run \
  -H "Content-Type: application/json" \
  -d '{"group":"hex","threshold":0.85,"min_devices":2}'

curl -s -b cookies.txt http://scanner:8000/api/provisioning/analysis/runs/RUN_ID
```

Ответ: `clusters` (по group/site/model), `complex_devices` — устройства с отклонением от baseline. В async-режиме поле `log` — пошаговый лог.

### Генерация шаблонов

```bash
# Синхронно
curl -s -b cookies.txt -X POST http://scanner:8000/api/provisioning/templates/generate \
  -H "Content-Type: application/json" \
  -d '{"group":"hex","site":"dc1","complexity_threshold":0.85,"min_devices":2,"upsert":true}'

# Асинхронно (UI)
curl -s -b cookies.txt -X POST http://scanner:8000/api/provisioning/templates/generate/run \
  -H "Content-Type: application/json" \
  -d '{"group":"hex","threshold":0.85,"min_devices":2,"upsert":true}'

curl -s -b cookies.txt http://scanner:8000/api/provisioning/templates/generate/runs/RUN_ID
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

# Статус задачи (поле log — пошаговый лог bulk)
curl -s -b cookies.txt http://scanner:8000/api/provisioning/bulk/5
```

Задача выполняется worker'ом (`TASK_WORKER_ENABLED`). Каждое устройство получает запись в `provision_runs` с привязкой к `provision_bulk_runs`.

## Web UI

**Провижионинг** в боковом меню: шаблоны (создание и **редактирование** через edit → Сохранить), **Генерация из бэкапов** (лог анализа/генерации), **Bulk provision** (live-лог прогресса), preview, история запусков и bulk-задач.

Фильтры group / site / model и список устройств подгружаются из БД (`GET /api/provisioning/filters`) с учётом object scope. Значение «все» в фильтрах — весь доступный инвентарь. Шаблон с `model=*` применяется к любой модели; apply для неизвестных моделей — построчно по SSH.

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


## Выделение шаблона из конфигов

Для каждого кластера рассчитывается extraction report:

- `coverage` — доля строк baseline, вошедших в устойчивую часть;
- `common_lines` — количество устойчивых строк;
- `divergent_lines` — строки baseline, которых нет минимум у 80% конфигов кластера;
- `variables` — автоматически выделенные переменные с известным источником;
- `review_lines` — divergent-строки для ручной проверки.

Автоматически параметризуются только значения, источник которых известен из inventory. Произвольные отличия между устройствами в Jinja-переменные не превращаются.

В UI таблица кластеров показывает `coverage / divergent`, а результат анализа содержит полный `extraction` объект.

Пример:

```json
{
  "coverage": 0.94,
  "common_lines": 47,
  "divergent_lines": 3,
  "variables": [
    {"name": "name", "source": "inventory", "expression": "{{ device.name }}"},
    {"name": "ip", "source": "inventory", "expression": "{{ device.ip }}"}
  ],
  "review_lines": ["/ip route add gateway=10.20.30.1"]
}
```
