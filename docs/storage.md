# Хранение бэкапов

Backup Tools хранит конфигурации устройств **локально** в Docker-томе `oxidized-data` и **опционально** пушит их во внешний Git (Gitea/GitLab). Отдельно есть файловые бэкапы MikroTik (binary/export) и данные инвентаря/БД.

## Схема хранилищ

| Что храним | Где в контейнере | Где на хосте (bind-mount) | Тип |
|------------|------------------|---------------------------|-----|
| Git-репозиторий конфигов | `/var/lib/oxidized` | volume `oxidized-data` | **git** (single repo) |
| MikroTik binary `.backup` | `/var/lib/oxidized/bin/` | volume `oxidized-data` | **файлы** |
| MikroTik export `.rsc` | `/var/lib/oxidized/rsc/` | volume `oxidized-data` | **файлы** |
| Инвентарь + SQLite БД (`scanner.db`) | `/data/inventory/` | `STACK_PATH/inventory/` | **bind-mount** |
| Конфигурация Oxidized / router.db | `/data/oxidized/` | `STACK_PATH/oxidized/` | **bind-mount** |
| SSH-ключи для git push | `/home/oxidized/.ssh/` (ro) | `STACK_PATH/oxidized-ssh/` | **bind-mount** |
| PostgreSQL (опционально) | `/var/lib/postgresql/data` | volume `pg-data` | **sql** |
| Экспорт БД + инвентаря (`backup_data`) | `/data/backups/<timestamp>/` | volume `BACKUP_DATA_DIR` | **дамп** |

> Том `oxidized-data` объявляется в `docker-compose.yml` (`volumes: oxidized-data:`) и монтируется в `/var/lib/oxidized` у `scanner`, `scanner-worker` и `oxidized`.

## 1. Git-репозиторий конфигов (основной бэкап)

Каждое устройство опрашивается по SSH, конфиг сохраняется в git-репозиторий по пути `OXIDIZED_GIT_REPO` = `/var/lib/oxidized`.

- **Вид:** один git-репозиторий (`single_repo: true`), одна ветка `main` (`single_branch: true`, `single_branch_name: main`).
- **Путь к файлу:** `<group>/<name>` — при `single_repo=true` конфиги раскладываются по группам (`hex`, `us`), например `hex/r1_ukg`.
- **Коммит** создаётся только при изменении содержимого (diff по сравнению с предыдущей версией).
- **Автор коммита:** `GIT_COMMIT_USER` / `GIT_COMMIT_EMAIL` (по умолчанию `Oxidized <oxidized@example.com>`).
- **Каталог:** `/var/lib/oxidized/`.

```
/var/lib/oxidized/          # git repo (volume oxidized-data)
├── hex/                    # группа hex
│   ├── r1_ukg              # конфиг устройства (копия после изменения)
│   └── ...
├── us/                     # группа us
│   └── ...
└── .git/                   # история версий (git log)
```

API просмотра версий/диффа: `GET /api/oxidized/nodes/{name}/versions`.

### Push во внешний Git

После сохранения (`post_store`) кидается hook `githubrepo` → push в `GIT_REMOTE_URL`:

```env
GIT_REMOTE_URL=http://10.216.40.65:3000/Oxidized/sat_backup.git
GITEA_TOKEN=...
GITEA_HTTP_USER=oauth2
# или SSH:
GIT_REMOTE_URL=git@10.216.40.65:Oxidized/sat_backup.git
```

- Содержимое репозитория: те же `<group>/<name>`, плюс каталоги `bin/` и `rsc/` (при `MK_BACKUP_GIT_PUSH=true`).
- Credentials/ключи — UI → Настройки → Git, или из `.env` при первом старте.

## 2. MikroTik файловые бэкапы

Создаются для узлов с моделью `routeros` только при `OXIDIZED_ENGINE=python`. Скачиваются по SFTP в volume.

| Тип | Каталог | Именование | Описание |
|-----|---------|------------|----------|
| **Binary** | `/var/lib/oxidized/bin/` | `{id}_{name}_{YYYY-MM-DD_HH-MM-SS}.backup` | датированный архив `/system backup save` |
| **Binary (last)** | `/var/lib/oxidized/bin/` | `{id}_{name}_last.backup` | «последняя» копия, ротацией не удаляется |
| **Export** | `/var/lib/oxidized/rsc/` | `{id}_{name}.rsc` | текстовый скрипт `/export` |

- `{id}` — ID устройства из PostgreSQL (защита от совпадений имён после переименования).
- **Шифрование binary:** при заданном `MK_BACKUP_ENCRYPT_PASSWORD` — AES-SHA256.
- **Ротация:** при `PURGE_OLD_BACKUP=true` остаётся последних `PURGE_N_PIECE=10` датированных `.backup`; `_last.backup` не удаляется.
- **Export:** `.rsc` может быть с `hide-sensitive` (`MK_BACKUP_HIDE_SENSITIVE`) в зависимости от версии RouterOS.

Для скачивания и списка: `GET /api/oxidized/nodes/{name}/backups` и `/backups/download`.

## 3. Данные инвентаря и конфигурации

Хранятся на хосте через bind-mount, не в volume — редактируются/подхватываются при перезапуске:

| Файл | Путь в контейнере | Назначение |
|------|-------------------|------------|
| `inventory/*.yaml` | `/data/inventory/` | источник устройств/подсетей |
| `scanner.db` | `/data/inventory/scanner.db` | SQLite-инвентарь (по умолчанию) |
| `oxidized/config` | `/data/oxidized/config` | настройки Oxidized (маппинг, credentials, git) |
| `oxidized/router.db` | `/data/oxidized/router.db` | список устройств для Ruby-движка |

## 4. База данных (инвентарь / настройки / credentials)

- **По умолчанию** — SQLite: `DATABASE_URL=sqlite:////data/inventory/scanner.db`.
- **PostgreSQL (опционально)** — профиль `postgres`, БД в volume `pg-data` (`/var/lib/postgresql/data`).

> `pg-data` — том, создаётся только при `docker compose --profile postgres up -d`.

## 5. Экспорт всего хранилища (backup_data)

`python manage.py backup_data` (UI → Настройки → Сервис → Backup data now) пишет в `BACKUP_DATA_DIR` (по умолчанию `/data/backups/<timestamp>/`):

- SQLite: копия `scanner.db`; PostgreSQL: `pg_dump` → `inventory.sql`
- `inventory.yaml`, `network_inventory.yml` — если существуют

## Итог: роль каждого места

| Место | Что хранит | Зачем |
|-------|------------|-------|
| volume `oxidized-data` (= `/var/lib/oxidized`) | git-репозиторий конфигов + `bin/` + `rsc/` | **главная копия** всех бэкапов и истории |
| Gitea/GitLab (`GIT_REMOTE_URL`) | то же самое + auto-push | внешняя резервная копия, доступ для команды/CI |
| bind-mount `inventory/` | инвентарь + SQLite БД | устройства, credentials, настройки приложений |
| bind-mount `oxidized/` | конфиг Oxidized | логика сбора и git-маппинг |
| bind-mount `oxidized-ssh/` | SSH-ключи | доступ к external Git по SSH |
| volume `pg-data` | PostgreSQL БД | опциональная СУБД вместо SQLite |

## Полезные команды

```bash
# Посмотреть git-репозиторий конфигов
docker compose exec scanner ls -R /var/lib/oxidized

# История изменений конкретного устройства
docker compose exec scanner git -C /var/lib/oxidized log --oneline

# Файлы MikroTik
docker compose exec scanner ls -la /var/lib/oxidized/bin/
docker compose exec scanner ls -la /var/lib/oxidized/rsc/

# Размер томов
docker system df -v
```

## Связанные документы

- [Oxidized и бэкапы](oxidized.md) — жизненный цикл сбора и git push
- [MikroTik бэкапы](mikrotik-backups.md) — binary/export детали
- [Эксплуатация](operations.md) — резервное копирование данных самого инструмента
