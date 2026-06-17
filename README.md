# Backup Tools

Сканирование сети, инвентарь устройств и бэкап конфигураций через [Oxidized](https://github.com/ytti/oxidized).

| Сервис | Порт | Описание |
|--------|------|----------|
| Scanner UI | 8000 | Web-интерфейс, API, scan/discovery |
| Oxidized | 8888 | Сбор и хранение конфигов |
| PostgreSQL | — | База инвентаря и пользователей (внутренняя) |

## Быстрый старт (Docker Compose)

```bash
cp .env.example .env
# отредактируйте .env
chmod +x deploy/init-stack.sh oxidized/entrypoint.sh
./deploy/init-stack.sh .
docker compose up -d --build
```

UI: http://localhost:8000/ui

LDAP / Active Directory: **Настройки** → раздел «LDAP / Active Directory» (роль admin). При первом запуске подтягиваются значения из `.env`.

## Развёртывание через Portainer

Пошаговая инструкция: **[deploy/PORTAINER.md](deploy/PORTAINER.md)**

Кратко:

1. Клонировать репозиторий на сервер
2. `./deploy/init-stack.sh` и настроить `.env`
3. Portainer → Stacks → Git repository → `docker-compose.yml` + env

## Структура

```
├── docker-compose.yml      # стек сервисов
├── .env.example            # шаблон переменных
├── deploy/                 # скрипты и документация Portainer
├── scanner/                # Django-приложение (UI + API)
├── inventory/              # network_inventory.yml (bind-mount)
├── oxidized/               # config Oxidized (bind-mount)
└── oxidized-ssh/           # SSH-ключи для push в Git
```

## Полезные команды

```bash
docker compose logs -f scanner
docker compose logs -f oxidized
docker compose restart scanner oxidized
```
