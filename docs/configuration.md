# Конфигурация

Все сервисы (`db`, `scanner`, `oxidized`) читают один файл `.env` через `env_file` в `docker-compose.yml`. Шаблон: [.env.example](../.env.example).

## Пути на хосте

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `STACK_PATH` | `.` | Корень репозитория для bind-mount (`inventory`, `oxidized`, `oxidized-ssh`). На Portainer укажите абсолютный путь, если репо не в каталоге compose. |

## PostgreSQL

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `POSTGRES_USER` | `backup` | Пользователь БД |
| `POSTGRES_PASSWORD` | — | **Обязательно изменить** |
| `POSTGRES_DB` | `inventory` | Имя базы |
| `POSTGRES_HOST` | `db` | Хост (в Docker — имя сервиса) |
| `POSTGRES_PORT` | `5432` | Порт |
| `DATABASE_URL` | — | Альтернативный DSN: `postgresql+psycopg2://user:pass@host:5432/db` |

## Scanner

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `SCANNER_PORT` | `8000` | Публикуемый порт UI/API |
| `SCANNER_IMAGE_TAG` | `latest` | Тег образа scanner |
| `LOG_LEVEL` | `INFO` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `DEBUG` | `false` | Django DEBUG (только для разработки) |
| `ALLOWED_HOSTS` | `*` | Список хостов через запятую |
| `GUNICORN_WORKERS` | `2` (1 при python engine) | Число worker-процессов Gunicorn |

### Пути внутри контейнера

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `INVENTORY_PATH` | `/data/inventory/inventory.yaml` | Seed-файл (при пустой БД) |
| `NETWORK_INVENTORY_PATH` | `/data/inventory/network_inventory.yml` | Подсети для импорта |
| `ROUTER_DB_PATH` | `/data/oxidized/router.db` | Legacy SQLite (не используется при PostgreSQL) |
| `OXIDIZED_HOME` | `/data/oxidized` | Каталог конфигурации Oxidized |
| `OXIDIZED_CONFIG_PATH` | `/data/oxidized/config` | YAML-конфиг Oxidized |
| `OXIDIZED_LOG_PATH` | `/var/lib/oxidized/oxidized.log` | Лог Oxidized (python и external) |

### Scan / Discovery

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `SCAN_CONCURRENCY` | `50` | Параллельных ping/port-проверок (снижайте при `Errno 24`) |
| `DISCOVER_MAX_HOSTS` | `4096` | Максимум хостов в одной подсети при discovery |
| `DISCOVER_PING_WORKERS` | `100` | Параллельных ping при sweep подсети |

## Аутентификация

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `JWT_SECRET` | — | **Обязательно** — секрет подписи JWT (≥ 32 символов) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Время жизни сессии (минуты) |
| `ADMIN_USERNAME` | `admin` | Логин начального администратора |
| `ADMIN_PASSWORD` | — | **Обязательно** — пароль начального администратора |
| `AUTH_COOKIE_NAME` | `backup_tools_token` | Имя HttpOnly cookie с JWT |

## LDAP / Active Directory

Начальные значения подтягиваются из `.env` при первом запуске; далее редактируются в UI (**Настройки → LDAP**). См. [authentication.md](authentication.md).

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `LDAP_ENABLED` | `false` | Включить LDAP-аутентификацию |
| `LDAP_AD` | `false` | `true` — Active Directory (фильтр `sAMAccountName`) |
| `LDAP_SERVER` | — | URI, напр. `ldap://dc.example.com:389` |
| `LDAP_USE_SSL` | `false` | LDAPS (порт 636) |
| `LDAP_START_TLS` | `true` | STARTTLS на порту 389 |
| `LDAP_BIND_DN` | — | DN сервисной учётной записи |
| `LDAP_BIND_PASSWORD` | — | Пароль bind |
| `LDAP_USER_BASE` | — | Base DN для поиска пользователей |
| `LDAP_USER_FILTER` | `(uid={username})` | Фильтр; для AD: `(sAMAccountName={username})` |
| `LDAP_USER_DN_TEMPLATE` | — | Альтернатива фильтру: `uid={username},ou=users,dc=...` |
| `LDAP_USER_UPN_SUFFIX` | — | UPN-суффикс: `user@domain.com` |
| `LDAP_ADMIN_GROUPS` | — | DN групп → роль `admin` (по одной на строку) |
| `LDAP_OPERATOR_GROUPS` | — | DN групп → роль `operator` |
| `LDAP_DEFAULT_ROLE` | `viewer` | Роль, если пользователь не в admin/operator группах |
| `LDAP_FALLBACK_LOCAL` | `true` | Разрешить локальный вход, если LDAP недоступен |
| `LDAP_CONNECT_TIMEOUT` | `10` | Таймаут подключения (сек) |

## Учётные данные устройств

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `OVN_USER` | `satcoadm` | SSH-логин для группы `hex` |
| `OVN_PASS` | — | SSH-пароль для группы `hex` |
| `US_USER` | `satcoadm` | SSH-логин для группы `us` |
| `US_PASS` | — | SSH-пароль для группы `us` |
| `ROUTEROS_SSH_PORT` | `44333` | Порт SSH RouterOS по умолчанию |

Группы `hex` и `us` соответствуют ключам в `network_inventory.yml` → `environments`.

## Oxidized

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `OXIDIZED_ENGINE` | `python` | `python` — встроенный движок; `external` — Ruby-контейнер |
| `OXIDIZED_INTERVAL` | `3600` | Интервал опроса узлов (сек) |
| `OXIDIZED_THREADS` | `10` | Параллельных потоков сбора |
| `OXIDIZED_TIMEOUT` | `20` | Таймаут SSH (сек) |
| `OXIDIZED_RETRIES` | `3` | Повторы при ошибке |
| `OXIDIZED_GIT_REPO` | `/var/lib/oxidized` | Локальный Git-репозиторий конфигов |
| `OXIDIZED_RESOLVE_DNS` | `true` | Резолв DNS имён узлов |
| `OXIDIZED_DEFAULT_MODEL` | `routeros` | Модель по умолчанию |
| `OXIDIZED_SOURCE_URL` | `http://scanner:8000/api/oxidized/source` | URL source для external Oxidized |
| `OXIDIZED_SOURCE_TOKEN` | — | Опциональный токен (`X-Auth-Token`) для source |
| `OXIDIZED_PUBLIC_URL` | `http://localhost:8888` | Публичный URL для ссылок в UI |
| `CONFIG_RELOAD_INTERVAL` | `3600` | Интервал перезагрузки конфига (external) |

### Только для `OXIDIZED_ENGINE=external`

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `OXIDIZED_URL` | `http://oxidized:8888` | Внутренний URL Ruby Oxidized |
| `OXIDIZED_PORT` | `8888` | Публикуемый порт Oxidized Web |
| `OXIDIZED_SSH_PASSPHRASE` | — | Passphrase SSH-ключа (если есть) |

## Git push

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `GIT_REMOTE_URL` | — | URL удалённого репозитория (HTTP или SSH) |
| `GITEA_TOKEN` | — | Personal/Deploy token для HTTP push |
| `GITEA_HTTP_USER` | `oauth2` | Username для HTTP auth (Gitea: `oauth2`) |
| `GIT_COMMIT_USER` | `Oxidized` | Имя автора коммитов |
| `GIT_COMMIT_EMAIL` | `oxidized@example.com` | Email автора коммитов |
| `GIT_BRANCH` | `main` | Целевая ветка |
| `GIT_SSH_PRIVATE_KEY` | `/home/oxidized/.ssh/id_rsa` | Путь к приватному ключу |
| `GIT_SSH_PUBLIC_KEY` | `/home/oxidized/.ssh/id_rsa.pub` | Путь к публичному ключу |

## Файл `oxidized/config`

Дополняет `.env` для external-режима и ruby_bridge. Основные секции:

```yaml
interval: 3600
threads: 30
timeout: 20
model: routeros
input:
  default: ssh
  ssh:
    port: 44333
source:
  http:
    url: http://scanner:8000/api/oxidized/source
groups:
  hex:
    username: ...
    password: ...
  us:
    username: ...
    password: ...
output:
  git:
    repo: /var/lib/oxidized
hooks:
  push_to_git:
    remote_repo: http://gitea.example.com/Oxidized/backups.git
```

Шаблон: [oxidized/config.example](../oxidized/config.example).

## Приоритет настроек

1. **Runtime UI** — LDAP, профили credentials (БД)
2. **`.env`** — большинство параметров scanner и oxidized engine
3. **`oxidized/config`** — groups, model_map, SSH port для external/ruby_bridge
4. **Defaults** — значения в коде

После изменения `.env`:

```bash
docker compose up -d
# или для отдельного сервиса:
docker compose restart scanner
```

После изменения credentials в UI достаточно **Oxidized → Sync** или `POST /oxidized/sync`.
