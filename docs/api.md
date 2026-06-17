# REST API

Базовый URL: `http://<host>:8000`

Аутентификация: cookie `backup_tools_token` или `Authorization: Bearer <jwt>` (кроме публичных эндпоинтов).

Формат ошибок:

```json
{"detail": "Сообщение об ошибке"}
```

## Публичные эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Healthcheck приложения |
| GET | `/ui` | Web UI (HTML) |
| GET | `/api/ui/config` | Конфиг UI (engine, auth methods) |
| POST | `/api/auth/login` | Вход |
| GET | `/api/oxidized/source` | Source для Oxidized (опц. `X-Auth-Token`) |

### GET /health

```json
{
  "status": "ok",
  "inventory_devices": 42,
  "networks": 12,
  "last_scan": "2026-06-17T10:00:00Z"
}
```

### GET /api/ui/config

```json
{
  "oxidized_public_url": "http://host:8888",
  "oxidized_proxy_url": null,
  "oxidized_engine": "python",
  "oxidized_engine_title": "Python Oxidized",
  "scanner_version": "1.0.0",
  "auth_required": true,
  "auth": {"local": true, "ldap": false}
}
```

## Аутентификация

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| POST | `/api/auth/logout` | ✓ | Выход |
| GET | `/api/auth/me` | `inventory:read` | Текущий пользователь + permissions |

## Инвентарь

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| GET | `/inventory` | `inventory:read` | Полный инвентарь |
| PUT | `/inventory` | `inventory:write` | Замена инвентаря |
| POST | `/inventory/devices` | `inventory:devices` | Добавить устройство |
| DELETE | `/inventory/devices/{name}` | `inventory:devices` | Удалить устройство |
| POST | `/inventory/credentials` | `credentials:write` | Создать профиль |
| PUT | `/inventory/credentials/{name}` | `credentials:write` | Обновить профиль (+ model группы) |
| DELETE | `/inventory/credentials/{name}` | `credentials:write` | Удалить профиль |
| POST | `/inventory/import-network` | `inventory:write` | Импорт network_inventory.yml |
| POST | `/inventory/cleanup-discovered` | `inventory:write` | Удалить `discovered-*` устройства |

## Scan

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| POST | `/scan` | `scan:run` | Запуск scan → `202` |
| POST | `/scan?discover=true` | `scan:run` | Scan + discovery |
| GET | `/scan/status` | `inventory:read`* | Статус job |
| GET | `/scan/latest` | `inventory:read`* | Последний ScanSummary |

\* В коде используется `PERMISSION_VIEW_INVENTORY` (эквивалент `inventory:read` + scan results для viewer).

## Oxidized — узлы и конфиги

| Метод | Путь | Permission | Движок | Описание |
|-------|------|------------|--------|----------|
| GET | `/api/oxidized/health` | `oxidized:read` | оба | Health + engine, models |
| GET | `/api/oxidized/logs` | `oxidized:read` | оба | Tail лога |
| GET | `/api/oxidized/models` | `inventory:read` | оба | Список моделей |
| GET | `/api/oxidized/nodes` | `oxidized:read` | оба | Список узлов |
| GET | `/api/oxidized/nodes/{name}` | `oxidized:read` | оба | Текущий конфиг (text) |
| GET | `/api/oxidized/nodes/{name}/versions` | `oxidized:read` | оба | Git versions |
| GET | `/api/oxidized/nodes/{name}/versions/{oid}` | `oxidized:read` | **python** | Версия по OID |
| GET | `/api/oxidized/nodes/{name}/diff` | `oxidized:read` | **python** | Diff (`?oid=&oid2=&format=html\|text\|json`) |
| POST | `/api/oxidized/nodes/{name}/fetch` | `oxidized:write` | оба | Принудительный fetch |
| POST | `/api/oxidized/backup/all` | `oxidized:write` | **python** | Очередь всех узлов |
| POST | `/oxidized/sync` | `oxidized:write` | оба | Sync credentials/source |
| * | `/oxidized-proxy/{path}` | `oxidized:read` | **external** | Прокси Ruby UI |

Эндпоинты с пометкой **python** возвращают `501` при `OXIDIZED_ENGINE=external` (versions/diff через proxy).

### GET /api/oxidized/health (python)

```json
{
  "reachable": true,
  "nodes_count": 42,
  "engine": "python",
  "engine_title": "Python Oxidized",
  "models": "oxidized-gem",
  "log_path": "/var/lib/oxidized/oxidized-python.log"
}
```

## MikroTik файловые бэкапы

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| GET | `/api/oxidized/nodes/{name}/backups` | `oxidized:read` | Список `.backup` / `.rsc` |
| GET | `/api/oxidized/nodes/{name}/backups/download` | `oxidized:read` | Скачать файл (`?type=bin\|rsc&file=...`) |

См. [mikrotik-backups.md](mikrotik-backups.md).

## Настройки

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| GET | `/api/settings/oxidized` | `oxidized:read` | Worker settings + health |
| PUT | `/api/settings/oxidized` | `oxidized:write` | Сохранить interval, threads, models… |
| GET | `/api/settings/backup` | `oxidized:read` | MikroTik backup + notifications |
| PUT | `/api/settings/backup` | `oxidized:write` | Сохранить backup/notify settings |
| POST | `/api/settings/backup/test-notify` | `oxidized:write` | Тест Telegram/Email |
| GET | `/api/settings/ldap` | `users:manage` | LDAP config |
| PUT | `/api/settings/ldap` | `users:manage` | Сохранить LDAP |
| POST | `/api/settings/ldap/test` | `users:manage` | Тест LDAP bind |

### PUT /api/settings/oxidized

```json
{
  "interval": 3600,
  "threads": 10,
  "timeout": 20,
  "retries": 3,
  "default_model": "routeros",
  "ssh_port": 44333,
  "resolve_dns": true,
  "group_models": {"hex": "routeros", "us": "routeros"}
}
```

### PUT /api/settings/backup

```json
{
  "binary_enabled": true,
  "export_enabled": true,
  "hide_sensitive": false,
  "purge_enabled": true,
  "purge_keep": 10,
  "error_notify_telegram": true,
  "telegram_token": "…",
  "telegram_chat_notify": "-100…"
}
```

## Пользователи

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| GET | `/api/auth/users` | `users:manage` | Список |
| POST | `/api/auth/users` | `users:manage` | Создать |
| GET | `/api/auth/users/{id}` | `users:manage` | Детали |
| PUT | `/api/auth/users/{id}` | `users:manage` | Обновить |
| DELETE | `/api/auth/users/{id}` | `users:manage` | Удалить |

## Примеры curl

### Login + inventory

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secret"}'

curl -b cookies.txt http://localhost:8000/inventory
```

### Discovery scan

```bash
curl -b cookies.txt -X POST "http://localhost:8000/scan?discover=true"
curl -b cookies.txt http://localhost:8000/scan/status
```

### Backup all + MikroTik files

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/oxidized/backup/all
curl -b cookies.txt http://localhost:8000/api/oxidized/nodes/my-router/backups
curl -b cookies.txt -OJ \
  "http://localhost:8000/api/oxidized/nodes/my-router/backups/download?type=bin&file=1_my-router_last.backup"
```

### Test notification

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/settings/backup/test-notify \
  -H "Content-Type: application/json" \
  -d '{"kind":"report"}'
```

## Коды ответов

| Код | Значение |
|-----|----------|
| 200 | OK |
| 202 | Scan job принят |
| 400 | Ошибка валидации |
| 401 | Не авторизован |
| 403 | Недостаточно прав |
| 404 | Не найдено |
| 405 | Method not allowed |
| 409 | Конфликт (scan уже running) |
| 501 | Не поддерживается для текущего engine |
| 503 | Oxidized/external недоступен |

## Oxidized Source (external)

```bash
curl -H "Accept: application/json" \
  -H "X-Auth-Token: your-token" \
  http://localhost:8000/api/oxidized/source
```

Формат: массив `{hostname, ip, os, group, ssh_port}`.
