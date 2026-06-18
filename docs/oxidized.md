# Oxidized и бэкапы конфигураций

Backup Tools собирает конфигурации через Oxidized. Подробное сравнение движков — **[engines.md](engines.md)**.

## Типы движков (кратко)

| | **Python Oxidized** | **Ruby Oxidized (external)** |
|---|-------------------|------------------------------|
| `OXIDIZED_ENGINE` | `python` (default) | `external` |
| Контейнер | Только `scanner` | `scanner` + `oxidized` |
| Запуск | `docker compose up -d` | `docker compose --profile external up -d` |
| Модели | Gem oxidized в scanner + fallback `routeros` | Полный upstream Oxidized |
| Git push | Python HookRunner | Hook в `oxidized/config` |
| Лог | `oxidized-python.log` | `oxidized.log` |

### Python Oxidized (по умолчанию)

```env
OXIDIZED_ENGINE=python
```

- Worker-поток **внутри scanner**, Gunicorn = 1 worker
- Узлы из PostgreSQL напрямую (без HTTP source)
- Сбор: `oxidized_bridge.rb` + gem oxidized (если доступен), иначе нативная модель `routeros`
- Push через subprocess git (`GITEA_TOKEN` или SSH-ключ)

### Ruby Oxidized (external)

```env
OXIDIZED_ENGINE=external
```

```bash
docker compose --profile external up -d
```

- Контейнер `oxidized/oxidized:latest`, Web UI `:8888`
- Source: `GET scanner:8000/api/oxidized/source`
- Scanner API проксирует nodes/fetch/versions на Ruby
- Push через hook `githubrepo` в config

→ Полное описание: **[docs/engines.md](engines.md)**

## Жизненный цикл бэкапа

1. **Load nodes** — список из PostgreSQL (enabled devices)
2. **Schedule** — каждые `OXIDIZED_INTERVAL` секунд worker обрабатывает очередь
3. **Collect** — SSH-сессия, выполнение команд модели
4. **Store** — diff с предыдущей версией, commit в локальный Git (`oxidized-data` volume)
5. **Push** — отправка в `GIT_REMOTE_URL`
6. **MikroTik files** (python, routeros) — binary `.backup` + export `.rsc` → [mikrotik-backups.md](mikrotik-backups.md)
7. **Notify** (опц.) — Telegram/Email → [notifications.md](notifications.md)

## Поддерживаемые модели

| Движок | Режим | Модели |
|--------|-------|--------|
| **python** | `oxidized-gem` (по умолчанию в Docker) | Все модели gem oxidized через `ruby_bridge.rb` |
| **python** | `python-fallback` | Только `routeros` (нативный Python) |
| **external** | Ruby Oxidized | Полный upstream набор |

Проверка активного режима: `GET /api/oxidized/health` → поле `models` (только python).

Список моделей: `GET /api/oxidized/models`.

Маппинг имён: `oxidized/config` → `model_map`.

## Web UI — раздел «Oxidized»

- Статус движка (python / external)
- Таблица узлов: имя, IP, группа, модель, last status, mtime
- **Fetch** — принудительный сбор одного узла
- **Sync** — синхронизация source/credentials
- **Backup all** — постановка всех узлов в очередь (python only)
- Просмотр конфигурации, версий, diff
- **MikroTik backups** — список и скачивание `.backup` / `.rsc` (routeros)
- Логи (`/api/oxidized/logs`)

## Настройки worker (UI / API)

**Настройки → Бэкап → Oxidized worker** или `GET/PUT /api/settings/oxidized`:

| Поле | Описание |
|------|----------|
| `interval` | Интервал опроса (≥ 60 сек) |
| `threads` | Параллельные потоки (1–64) |
| `timeout` / `retries` | SSH timeout и повторы |
| `default_model` | Модель по умолчанию |
| `ssh_port` | SSH порт в config |
| `group_models` | Модель per group (`hex` → `routeros`) |
| `resolve_dns` | DNS resolve |

Сохранение записывает `oxidized/config` и вызывает reload engine. `OXIDIZED_ENGINE` и `GIT_REMOTE_URL` — только из `.env`.

Раздел **Oxidized Web** — iframe/proxy к Ruby UI (external) или справка (python).

## Git push

Локальный репозиторий: volume `oxidized-data` → `/var/lib/oxidized`.

Настройки remote URL, token, ветки и commit author — **UI → Настройки → Git** (`PUT /api/settings/git`). При первом запуске импортируются из `.env`. SSH-ключи остаются в `oxidized-ssh/`.

### HTTP (Gitea token)

```env
GIT_REMOTE_URL=http://10.216.40.65:3000/Oxidized/sat_backup.git
GITEA_TOKEN=<personal-or-deploy-token>
GITEA_HTTP_USER=oauth2
```

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

> **Push по движку:** `python` — Python HookRunner из `.env`; `external` — hook в config + entrypoint. См. [engines.md](engines.md).

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
| POST | `/api/oxidized/backup/all` | Очередь всех узлов (python) |
| GET | `/api/oxidized/nodes/{name}/backups` | MikroTik binary/export файлы |
| GET | `/api/oxidized/nodes/{name}/backups/download` | Скачать backup file |
| POST | `/oxidized/sync` | Sync credentials/source |
| GET/PUT | `/api/settings/oxidized` | Настройки worker |
| GET/PUT | `/api/settings/backup` | MikroTik + уведомления |
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
