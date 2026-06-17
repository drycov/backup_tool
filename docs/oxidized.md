# Oxidized и бэкапы конфигураций

Backup Tools поддерживает два способа сбора конфигураций сетевых устройств.

## Режимы движка

### Python-движок (по умолчанию)

```env
OXIDIZED_ENGINE=python
```

- Работает **внутри контейнера scanner** (фоновый worker-поток)
- Не требует отдельного контейнера `oxidized`
- Gunicorn запускается с **1 worker** (избежание дублирования worker-циклов)
- Модели: встроенные Python (`routeros`) + опционально Ruby через `oxidized_bridge.rb`
- Git output и push — нативно в Python

### External (Ruby Oxidized)

```env
OXIDIZED_ENGINE=external
```

```bash
docker compose --profile external up -d
```

- Отдельный контейнер `oxidized/oxidized:latest`
- Source: HTTP API scanner (`/api/oxidized/source`)
- Полный набор моделей upstream Oxidized
- Web UI на порту `8888`
- Прокси в scanner UI: `/oxidized-proxy/*`

## Жизненный цикл бэкапа

1. **Load nodes** — список из PostgreSQL (enabled devices)
2. **Schedule** — каждые `OXIDIZED_INTERVAL` секунд worker обрабатывает очередь
3. **Collect** — SSH-сессия, выполнение команд модели
4. **Store** — diff с предыдущей версией, commit в локальный Git (`oxidized-data` volume)
5. **Push** — отправка в `GIT_REMOTE_URL` (hook post_store)

## Поддерживаемые модели (Python)

| Model | Статус | Описание |
|-------|--------|----------|
| `routeros` | Встроенная | MikroTik RouterOS — `/export`, resource info |
| Другие | Ruby bridge | Через `oxidized_bridge.rb` и gem oxidized в scanner |

Маппинг имён моделей настраивается в `oxidized/config` (`model_map`).

## Web UI — раздел «Oxidized»

- Статус движка (python / external)
- Таблица узлов: имя, IP, группа, модель, last status, mtime
- **Fetch** — принудительный сбор одного узла
- **Sync** — синхронизация source/credentials
- Просмотр конфигурации, версий, diff
- Логи (`/api/oxidized/logs`)

Раздел **Oxidized Web** — iframe/proxy к Ruby UI (external) или справка (python).

## Git push

Локальный репозиторий: volume `oxidized-data` → `/var/lib/oxidized`.

### HTTP (Gitea token)

```env
GIT_REMOTE_URL=http://10.216.40.65:3000/Oxidized/sat_backup.git
GITEA_TOKEN=<personal-or-deploy-token>
GITEA_HTTP_USER=oauth2
```

Для external-режима entrypoint подставляет token в `oxidized/config` hooks.

### SSH

```env
GIT_REMOTE_URL=git@10.216.40.65:Oxidized/sat_backup.git
```

Ключи в `oxidized-ssh/`:

```bash
ssh-keygen -t rsa -b 4096 -m PEM -f oxidized-ssh/id_rsa -N ""
ssh-keyscan <gitea-host> >> oxidized-ssh/known_hosts
```

Deploy Key с правом **write** в репозитории Gitea.

Подробнее: [oxidized-ssh/README.md](../oxidized-ssh/README.md).

> **Важно:** ключ должен быть в формате **PEM** (`-m PEM`). OpenSSH-формат не поддерживается libssh2.

## Конфигурация `oxidized/config`

Ключевые параметры:

```yaml
interval: 3600
threads: 30
timeout: 20
retries: 3
model: routeros
resolve_dns: true
log: /var/lib/oxidized/oxidized-python.log   # python engine
# log: /var/lib/oxidized/oxidized.log        # ruby engine (external)

input:
  default: ssh
  ssh:
    secure: false
    port: 44333

source:
  http:
    url: http://scanner:8000/api/oxidized/source
    map:
      name: hostname
      model: os
      group: group
      ip: ip

groups:
  hex:
    username: satcoadm
    password: "***"
    model: routeros
  us:
    username: satcoadm
    password: "***"
    model: routeros

output:
  git:
    repo: /var/lib/oxidized
    single_repo: true
    single_branch: true
    single_branch_name: main

hooks:
  push_to_git:
    type: githubrepo
    events: [post_store]
    remote_repo: http://gitea/Oxidized/backups.git
    username: oauth2
    password: ''

rest: 0.0.0.0:8888
```

## HTTP Source API

```http
GET /api/oxidized/source
Accept: application/json
X-Auth-Token: <OXIDIZED_SOURCE_TOKEN>   # если задан
```

Публичный эндпоинт (без JWT), защищается опциональным токеном.

## API управления

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/oxidized/health` | Статус движка |
| GET | `/api/oxidized/nodes` | Список узлов |
| GET | `/api/oxidized/nodes/{name}` | Текущий конфиг |
| GET | `/api/oxidized/nodes/{name}/versions` | История версий |
| GET | `/api/oxidized/nodes/{name}/versions/{oid}` | Конкретная версия |
| GET | `/api/oxidized/nodes/{name}/diff` | Diff версий |
| POST | `/api/oxidized/nodes/{name}/fetch` | Принудительный fetch |
| POST | `/oxidized/sync` | Sync credentials/source |
| GET | `/api/oxidized/logs` | Tail лога |

## Логи

| Движок | `OXIDIZED_ENGINE` | Файл |
|--------|-------------------|------|
| Python Oxidized | `python` | `OXIDIZED_PYTHON_LOG_PATH` → `/var/lib/oxidized/oxidized-python.log` |
| Ruby Oxidized | `external` | `log:` в `oxidized/config` → обычно `/var/lib/oxidized/oxidized.log` |

UI читает `/api/oxidized/logs` — путь зависит от активного движка.

```bash
# Python engine
docker compose exec scanner tail -f /var/lib/oxidized/oxidized-python.log

# Ruby Oxidized
docker compose exec oxidized tail -f /var/lib/oxidized/oxidized.log
docker compose logs -f oxidized
```

## Troubleshooting

| Симптом | Причина | Решение |
|---------|---------|---------|
| `never` status | Узел ещё не опрашивался | Дождаться interval или Fetch |
| `no connection` | SSH недоступен | Ping/port с контейнера, firewall, credentials |
| Git push fail | Неверный token/ключ | Проверить `GIT_REMOTE_URL`, PEM-ключ, known_hosts |
| Пустой source | Нет enabled devices | Проверить инвентарь, Sync |
| Duplicate workers | Несколько gunicorn workers + python | Норма: entrypoint ставит workers=1 |
| Permission denied (git) | Deploy key read-only | Write access в Gitea |

Проверка SSH к устройству:

```bash
docker compose exec scanner python -c "
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('10.216.92.1', port=44333, username='user', password='pass', timeout=10)
print(c.exec_command('/system identity print')[1].read().decode())
"
```

## Переключение режима

```env
# .env
OXIDIZED_ENGINE=external   # или python
```

```bash
# external
docker compose --profile external up -d

# python only
docker compose up -d scanner db
docker compose stop oxidized
```

После переключения выполните **Sync** и проверьте `/api/oxidized/health`.
