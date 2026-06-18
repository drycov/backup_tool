# Документация Backup Tools

Backup Tools — платформа для **сканирования сети**, **ведения инвентаря** сетевых устройств и **автоматического резервного копирования конфигураций** через встроенный или внешний [Oxidized](https://github.com/ytti/oxidized).

## Содержание

| Документ | Описание |
|----------|----------|
| [Архитектура](architecture.md) | Компоненты, потоки данных, режимы Oxidized |
| [Установка](installation.md) | Docker Compose, Portainer, первичная настройка |
| [Конфигурация](configuration.md) | Переменные окружения (`.env`) |
| [Инвентарь](inventory.md) | YAML, импорт подсетей, профили credentials |
| [**Группы Oxidized**](groups.md) | SSH credentials, профиль vs группа, hex/us |
| [Сканирование](scanning.md) | Ping sweep, discovery, проверка портов и SSH |
| [Oxidized и бэкапы](oxidized.md) | Git push, SSH-ключи, API |
| [**Типы движков**](engines.md) | Python vs Ruby Oxidized — сравнение и выбор |
| [MikroTik бэкапы](mikrotik-backups.md) | Binary `.backup` и export `.rsc` |
| [Compliance](compliance.md) | Dashboard и метрики деградации |
| [Уведомления](notifications.md) | Telegram, Email, degrade alerts |
| [Web UI](ui.md) | Разделы интерфейса, чеклист первого запуска |
| [Аутентификация](authentication.md) | JWT, RBAC, LDAP / Active Directory |
| [API](api.md) | REST-эндпоинты Scanner |
| [Эксплуатация](operations.md) | Команды, мониторинг, резервное копирование, troubleshooting |
| [Интеграции](integrations.md) | API keys, Ansible, CI, NetBox |
| [Провижионинг](provisioning.md) | Шаблоны Jinja2, push конфигураций |

## Дополнительные материалы

- [Развёртывание через Portainer](../deploy/PORTAINER.md)
- [SSH-ключи для Git push](../oxidized-ssh/README.md)
- [Шаблон переменных окружения](../.env.example)

## Быстрый старт

```bash
cp .env.example .env
# отредактируйте .env
chmod +x deploy/init-stack.sh oxidized/entrypoint.sh
./deploy/init-stack.sh .
docker compose up -d --build
```

UI: **http://localhost:8000/ui**

Первый вход — логин и пароль из `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

## Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| Scanner UI | 8000 | Web-интерфейс, REST API, scan/discovery, встроенный Oxidized |
| Oxidized (external) | 8888 | Ruby Oxidized — только при `OXIDIZED_ENGINE=external` |
| PostgreSQL | — | Инвентарь, пользователи, LDAP, backup/notify settings |
