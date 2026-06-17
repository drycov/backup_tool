# Эксплуатация

## Ежедневные операции

### Мониторинг health

```bash
curl -s http://localhost:8000/health | jq .
docker compose ps
```

В Portainer все сервисы должны быть **healthy**.

### Просмотр логов

```bash
docker compose logs -f scanner
docker compose logs -f oxidized    # external mode
docker compose logs -f db
```

Лог Oxidized внутри scanner:

```bash
docker compose exec scanner tail -100 /var/lib/oxidized/oxidized.log
```

### Перезапуск сервисов

```bash
docker compose restart scanner
docker compose restart scanner oxidized
docker compose down && docker compose up -d --build
```

## Типовые сценарии

### Добавление новой подсети

1. Обновить `inventory/network_inventory.yml` на хосте
2. UI → **Инвентарь → Import network inventory** (или `POST /inventory/import-network`)
3. **Scan + Discovery** для обнаружения устройств
4. **Oxidized → Sync**

### Смена пароля SSH группы

1. UI → **Настройки** → профиль credentials (admin)
2. Или обновить `OVN_PASS` / `US_PASS` в `.env` и перезапустить scanner
3. **Oxidized → Sync**

### Принудительный бэкап одного устройства

UI → **Oxidized** → кнопка Fetch у узла

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/oxidized/nodes/ROUTER-NAME/fetch
```

### Добавление пользователя

UI → **Пользователи** → Add (admin)

## Резервное копирование данных

| Что | Где | Как бэкапить |
|-----|-----|--------------|
| PostgreSQL | volume `pg-data` | `pg_dump` или snapshot volume |
| Git конфиги | volume `oxidized-data` | Remote Git (Gitea) + локально |
| MikroTik bin/rsc | volume `oxidized-data` `/bin`, `/rsc` | Отдельный файловый бэкап volume |
| Конфигурация | `./.env`, `./oxidized/`, `./inventory/` | Git или файловый бэкап |
| SSH-ключи | `./oxidized-ssh/` | Зашифрованный бэкап |

### pg_dump

```bash
docker compose exec db pg_dump -U backup inventory > backup-$(date +%F).sql
```

### Restore

```bash
cat backup.sql | docker compose exec -T db psql -U backup inventory
```

## Обновление версии

```bash
cd /opt/backup-tools
git pull
docker compose up -d --build
docker compose exec scanner python manage.py migrate
```

Миграции выполняются автоматически при старте scanner (`init_db`).

## Troubleshooting

### Scanner не стартует

```bash
docker compose logs scanner
```

Частые причины:

- PostgreSQL недоступен → проверить `db` healthy
- Неверный `DATABASE_URL` / `POSTGRES_PASSWORD`
- Порт 8000 занят → изменить `SCANNER_PORT`

### База данных

```bash
docker compose exec db psql -U backup -d inventory -c '\dt'
docker compose exec scanner python manage.py migrate
```

### Scan не находит устройства

1. Ping из контейнера: `docker compose exec scanner ping <ip>`
2. Проверить firewall между Docker host и подсетями
3. На Linux может потребоваться `cap_add: NET_RAW` (ping) — проверьте docker-compose
4. Уменьшить concurrency при ошибках сокетов

### Oxidized: узлы в статусе fail

1. Проверить credentials группы устройства
2. SSH вручную (см. [oxidized.md](oxidized.md))
3. Проверить `ROUTEROS_SSH_PORT` и `ports` устройства
4. Лог зависит от движка: `oxidized-python.log` (python) или `oxidized.log` (external)

### Неверный / недоступный движок

```bash
curl -s http://localhost:8000/api/oxidized/health | jq '{engine, engine_title, models, reachable, error}'
```

| `engine` | `reachable: false` | Действие |
|----------|-------------------|----------|
| `python` | worker error | `docker compose logs scanner`, проверить `oxidized-python.log` |
| `external` | oxidized down | `docker compose --profile external up -d oxidized` |

Сравнение движков: [engines.md](engines.md).

### Git push не работает

1. **HTTP**: `GITEA_TOKEN`, права token, `GITEA_HTTP_USER=oauth2`
2. **SSH**: PEM-ключ, `known_hosts`, deploy key write
3. Логи hook в oxidized.log
4. Перезапуск: `docker compose restart scanner` (python) или `oxidized` (external)

### Bind mount пустой / неверные данные

Проверьте `STACK_PATH` — должен указывать на корень репозитория на **хосте**, не внутри контейнера.

### LDAP не работает

1. UI → **Настройки → LDAP → Тест**
2. Проверить `LDAP_SERVER` доступен из контейнера
3. Для AD: `LDAP_AD=true`, правильный filter/UPN
4. `LDAP_FALLBACK_LOCAL=true` — временный локальный вход

### MikroTik backups не создаются

1. `OXIDIZED_ENGINE=python` (не external)
2. Модель устройства `routeros`
3. `MK_BACKUP_BINARY` / `MK_BACKUP_EXPORT` включены
4. Проверить каталоги: `docker compose exec scanner ls /var/lib/oxidized/bin/`

См. [mikrotik-backups.md](mikrotik-backups.md).

### Уведомления не приходят

1. UI → **Настройки → Уведомления** — включить канал + **Тест**
2. Исходящий доступ к `api.telegram.org` / SMTP
3. Report шлётся только при изменении Git или ошибке binary

См. [notifications.md](notifications.md).

### CRLF на Windows

`init-stack.sh` и compose entrypoint нормализуют `\r\n` → `\n` для shell-скриптов и `known_hosts`.

## Полезные команды

```bash
# Статус контейнеров
docker compose ps

# Использование ресурсов
docker stats backup-tools-scanner-1

# Shell в scanner
docker compose exec scanner bash

# Django shell
docker compose exec scanner python manage.py shell

# Список узлов Oxidized (API)
curl -b cookies.txt http://localhost:8000/api/oxidized/nodes | jq .

# Пересборка только scanner
docker compose build scanner && docker compose up -d scanner
```

## Web UI — разделы

Полное описание: [ui.md](ui.md).

| Раздел | Роли | Функции |
|--------|------|---------|
| Dashboard | viewer+ | Сводка, health |
| Инвентарь | viewer+ | Устройства, import, cleanup discovered |
| Scan | operator+ | Scan / discovery |
| Oxidized | viewer+ | Узлы, fetch, sync, backup all, MikroTik files |
| Oxidized Web | viewer+ | Ruby UI proxy (external) |
| Настройки | mixed | Oxidized worker, MikroTik, notify, groups, LDAP, сервис |
| Пользователи | admin | CRUD, RBAC |

Глобальный поиск в шапке фильтрует таблицы по имени, IP, группе, модели.

## Контакты и поддержка

При проблемах соберите:

```bash
docker compose ps
docker compose logs --tail=200 scanner
curl -s http://localhost:8000/health
docker compose exec scanner tail -50 /var/lib/oxidized/oxidized.log
```

Версия UI: поле `scanner_version` в `GET /api/ui/config`.
