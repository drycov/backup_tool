# Backup Tools

Сканирование сети, инвентарь устройств и автоматический бэкап конфигураций через встроенный или внешний [Oxidized](https://github.com/ytti/oxidized).

## Возможности

- **Discovery** — ping sweep подсетей, автоматическое добавление устройств
- **Scan** — проверка доступности (ICMP, TCP, SSH probe)
- **Инвентарь** — PostgreSQL, Web UI, REST API, импорт из YAML
- **Бэкапы** — встроенный Python-движок Oxidized или Ruby Oxidized (external)
- **Git push** — сохранение конфигов в Gitea/GitLab через HTTP или SSH
- **RBAC** — роли viewer / operator / admin
- **LDAP / AD** — корпоративная аутентификация с маппингом групп

## Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| Scanner UI | 8000 | Web-интерфейс, API, scan/discovery, Python Oxidized |
| Oxidized (external) | 8888 | Ruby Oxidized — только при `OXIDIZED_ENGINE=external` |
| PostgreSQL | — | База инвентаря и пользователей (внутренняя) |

## Быстрый старт

```bash
cp .env.example .env
# отредактируйте .env (JWT_SECRET, ADMIN_PASSWORD, OVN_PASS, US_PASS)
chmod +x deploy/init-stack.sh oxidized/entrypoint.sh
./deploy/init-stack.sh .
docker compose up -d --build
```

**UI:** http://localhost:8000/ui

Первый вход: `ADMIN_USERNAME` / `ADMIN_PASSWORD` (по умолчанию `admin`).

## Документация

Полная документация: **[docs/README.md](docs/README.md)**

| Раздел | Описание |
|--------|----------|
| [Архитектура](docs/architecture.md) | Компоненты, потоки данных, режимы Oxidized |
| [Установка](docs/installation.md) | Docker Compose, Portainer, dev-окружение |
| [Конфигурация](docs/configuration.md) | Все переменные `.env` |
| [Инвентарь](docs/inventory.md) | YAML, импорт подсетей, профили credentials |
| [Сканирование](docs/scanning.md) | Scan, discovery, tuning |
| [Oxidized](docs/oxidized.md) | Бэкапы, Git push, SSH-ключи |
| [Аутентификация](docs/authentication.md) | JWT, RBAC, LDAP / AD |
| [API](docs/api.md) | REST-эндпоинты |
| [Эксплуатация](docs/operations.md) | Мониторинг, backup, troubleshooting |

## Развёртывание

- **Portainer:** [deploy/PORTAINER.md](deploy/PORTAINER.md)
- **SSH для Git:** [oxidized-ssh/README.md](oxidized-ssh/README.md)

## Структура репозитория

```
├── docker-compose.yml      # стек сервисов
├── .env.example            # шаблон переменных окружения
├── docs/                   # документация
├── deploy/                 # init-stack.sh, Portainer guide
├── scanner/                # Django-приложение (UI + API + Python Oxidized)
├── inventory/              # network_inventory.yml (bind-mount)
├── oxidized/               # config Oxidized (bind-mount)
└── oxidized-ssh/           # SSH-ключи для push в Git
```

## Полезные команды

```bash
docker compose logs -f scanner
docker compose logs -f oxidized          # external mode
docker compose restart scanner oxidized
curl -s http://localhost:8000/health
```

## External Oxidized

По умолчанию используется встроенный Python-движок (`OXIDIZED_ENGINE=python`). Для Ruby Oxidized:

```env
OXIDIZED_ENGINE=external
```

```bash
docker compose --profile external up -d --build
```

LDAP / Active Directory: **Настройки → LDAP / Active Directory** (роль admin). При первом запуске значения импортируются из `.env`.
