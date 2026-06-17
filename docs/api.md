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
| GET | `/health` | Healthcheck |
| GET | `/ui` | Web UI (HTML) |
| GET | `/api/ui/config` | Конфиг UI (engine, auth methods) |
| POST | `/api/auth/login` | Вход |
| GET | `/api/oxidized/source` | Source для Oxidized (опц. `X-Auth-Token`) |

### GET /health

```json
{
  "status": "ok",
  "oxidized_engine": "python",
  "database": "ok"
}
```

## Аутентификация

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/api/auth/logout` | ✓ | Выход (очистка cookie) |
| GET | `/api/auth/me` | ✓ | Текущий пользователь |

## Инвентарь

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| GET | `/inventory` | `inventory:read` | Полный инвентарь |
| PUT | `/inventory` | `inventory:write` | Замена инвентаря |
| GET | `/inventory/devices` | `inventory:read` | Список устройств |
| POST | `/inventory/devices` | `inventory:devices` | Добавить устройство |
| DELETE | `/inventory/devices/{name}` | `inventory:devices` | Удалить устройство |
| POST | `/inventory/credentials` | `credentials:write` | Создать профиль |
| PUT | `/inventory/credentials/{name}` | `credentials:write` | Обновить профиль |
| DELETE | `/inventory/credentials/{name}` | `credentials:write` | Удалить профиль |
| POST | `/inventory/import-network` | `inventory:write` | Импорт network_inventory.yml |

### Device (POST /inventory/devices)

```json
{
  "name": "router-01",
  "ip": "10.0.0.1",
  "model": "routeros",
  "group": "hex",
  "enabled": true,
  "ports": [44333]
}
```

### Inventory (PUT /inventory)

```json
{
  "credential_profiles": [
    {"name": "ovn", "group_name": "hex", "username": "admin", "password": "secret"}
  ],
  "networks": [
    {"network": "10.0.0.0/24", "group_name": "hex", "environment_name": "lab", "gateway": "10.0.0.1"}
  ],
  "devices": [
    {"name": "router-01", "ip": "10.0.0.1", "model": "routeros", "group": "hex", "enabled": true, "ports": [44333]}
  ]
}
```

## Scan

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| POST | `/scan` | `scan:run` | Запуск scan |
| POST | `/scan?discover=true` | `scan:run` | Scan + discovery |
| GET | `/scan/status` | `scan:read` | Статус текущего job |
| GET | `/scan/latest` | `scan:read` | Последний ScanSummary |

## Oxidized

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| GET | `/api/oxidized/health` | `oxidized:read` | Health движка |
| GET | `/api/oxidized/logs` | `oxidized:read` | Хвост лога |
| GET | `/api/oxidized/models` | `oxidized:read` | Доступные модели |
| GET | `/api/oxidized/nodes` | `oxidized:read` | Список узлов |
| GET | `/api/oxidized/nodes/{name}` | `oxidized:read` | Текущий конфиг (text) |
| GET | `/api/oxidized/nodes/{name}/versions` | `oxidized:read` | Git versions |
| GET | `/api/oxidized/nodes/{name}/versions/{oid}` | `oxidized:read` | Версия по OID |
| GET | `/api/oxidized/nodes/{name}/diff?oid=...` | `oxidized:read` | Diff |
| POST | `/api/oxidized/nodes/{name}/fetch` | `oxidized:write` | Принудительный fetch |
| POST | `/oxidized/sync` | `oxidized:write` | Sync source/credentials |
| * | `/oxidized-proxy/{path}` | `oxidized:read` | Прокси к Ruby Oxidized |

## Пользователи

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| GET | `/api/auth/users` | `users:manage` | Список |
| POST | `/api/auth/users` | `users:manage` | Создать |
| GET | `/api/auth/users/{id}` | `users:manage` | Детали |
| PUT | `/api/auth/users/{id}` | `users:manage` | Обновить |
| DELETE | `/api/auth/users/{id}` | `users:manage` | Удалить |

## LDAP

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| GET | `/api/settings/ldap` | `users:manage` | Текущие настройки |
| PUT | `/api/settings/ldap` | `users:manage` | Сохранить |
| POST | `/api/settings/ldap/test` | `users:manage` | Тест bind |

## Примеры curl

### Login

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secret"}'
```

### Scan

```bash
curl -b cookies.txt -X POST "http://localhost:8000/scan?discover=true"
curl -b cookies.txt http://localhost:8000/scan/status
```

### Fetch node

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/oxidized/nodes/my-router/fetch
```

### Bearer token

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secret"}' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/inventory
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
| 500 | Внутренняя ошибка |

## Oxidized Source (для external)

```bash
curl -H "Accept: application/json" \
  -H "X-Auth-Token: your-token" \
  http://localhost:8000/api/oxidized/source
```

Формат ответа — массив объектов `{name, ip, model, group, ssh_port}`.
