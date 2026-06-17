# Инвентарь

Инвентарь хранится в **PostgreSQL** и управляется через Web UI или REST API. YAML-файлы используются для первичного seed и импорта подсетей.

## Структура данных

### Устройство (Device)

| Поле | Тип | Описание |
|------|-----|----------|
| `name` | string | Уникальное имя (hostname, slug) |
| `ip` | string | IPv4-адрес |
| `model` | string | Модель Oxidized: `routeros`, `ios`, `junos`, … |
| `group` | string | Группа учётных данных (`hex`, `us`, `default`, …) |
| `enabled` | bool | Участвует в scan и бэкапах |
| `ports` | int[] | TCP-порты для проверки (по умолчанию `[44333]`) |

### Подсеть (Network)

| Поле | Тип | Описание |
|------|-----|----------|
| `network` | string | CIDR, напр. `10.216.92.0/23` |
| `group_name` | string | Группа credentials для discovery |
| `environment_name` | string | Имя окружения (из YAML) |
| `gateway` | string | IP шлюза (опционально, добавляется как устройство) |

### Профиль учётных данных (CredentialProfile)

См. подробнее **[groups.md](groups.md)**.

| Поле | Тип | Описание |
|------|-----|----------|
| `name` | string | Имя профиля в БД (`ovn`, `us`, …) |
| `group_name` | string | Группа устройств и ключ `groups` в Oxidized (`hex`, `us`) |
| `username` | string | SSH-логин |
| `password` | string | SSH-пароль |
| `model` | string | (в UI/API) модель Oxidized для группы — пишется в `oxidized/config` |

## network_inventory.yml

Файл описывает **подсети по окружениям**. Расположение: `inventory/network_inventory.yml` (bind-mount в контейнер).

```yaml
environments:
  hex:                    # → group_name = "hex", credentials = OVN_*
    - name: hex_r1_ukg    # environment_name, gateway → устройство
      networks:
        - subnet: 10.216.92.0/23
          gateway: 10.216.92.1
        - subnet: 10.216.101.0/24
          gateway: 10.216.101.1

  us:                     # → group_name = "us", credentials = US_*
    - name: us_r1_ukg
      networks:
        - subnet: 10.216.80.0/24
          gateway: 10.216.80.1
```

### Логика импорта

При `POST /inventory/import-network`:

1. Создаются профили `ovn` (group `hex`) и `us` (group `us`) из `OVN_*` / `US_*`.
2. Для каждой подсети создаётся запись `Network`.
3. Если указан `gateway`, создаётся устройство с именем `environment_name`.
4. Если gateway не указан и prefix ≥ /30 — первый хост подсети.

Импорт **заменяет** существующие networks и credential profiles, устройства дополняются.

## inventory.yaml (seed)

Файл для первого запуска при пустой БД:

```yaml
credentials:
  username: admin
  password: changeme

networks:
  - 192.168.1.0/24

devices:
  - name: router-01
    ip: 192.168.1.1
    model: ios
    group: routers
    enabled: true
    ports: [22, 44333]
```

После миграции данные живут в PostgreSQL; редактирование — через UI/API.

## Web UI — раздел «Инвентарь»

- Таблица устройств с фильтрацией и глобальным поиском
- Добавление/редактирование/удаление устройств (роль operator+)
- Импорт `network_inventory.yml`
- Просмотр подсетей

## Cleanup discovered

Discovery создаёт устройства вида `discovered-10-0-0-1`, если SSH probe не определил hostname. После ручного переименования можно удалить placeholder'ы:

- UI: **Настройки → Сервис → Cleanup discovered**
- API: `POST /inventory/cleanup-discovered` (`inventory:write`)

Удаляются только имена с префиксом `discovered-`. После cleanup — sync Oxidized credentials.

## Маскирование паролей

Пользователи с ролью **viewer** и **operator** не видят пароли в API (`credentials:read` только у admin). В UI поля паролей скрыты.

## Синхронизация с Oxidized

При любом изменении инвентаря:

- Обновляются `groups` в `oxidized/config` (external)
- Python-движок перезагружает список узлов

Ручная синхронизация: UI **Oxidized → Sync** или `POST /oxidized/sync`.

## Формат source для Oxidized

Эндпоинт `GET /api/oxidized/source` возвращает JSON-массив:

```json
[
  {
    "name": "hex_r1_ukg",
    "ip": "10.216.92.1",
    "model": "routeros",
    "group": "hex",
    "ssh_port": 44333
  }
]
```

Включены только устройства с `enabled: true`.

## Рекомендации

- Имена устройств: lowercase, `[a-z0-9-.]`, без пробелов
- Одна группа credentials на логическую зону (hex/us/production/…)
- Gateway-роутеры добавляйте явно — они часто не обнаруживаются discovery
- После массового импорта запустите scan без discovery для проверки доступности
