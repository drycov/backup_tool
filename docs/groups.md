# Группы и учётные данные (Oxidized `groups`)

Раздел **Настройки → Группы** управляет SSH-логинами и моделями Oxidized для каждой **группы устройств**.

Данные хранятся в PostgreSQL (`credential_profiles`) и синхронизируются в `oxidized/config`:

```yaml
groups:
  hex:
    username: satcoadm
    password: "**"
    model: routeros
  us:
    username: satcoadm
    password: "**"
    model: routeros
```

## Профиль vs группа

| Поле | Назначение | Пример |
|------|------------|--------|
| **Имя профиля** | Уникальное имя записи в БД (для UI/API) | `ovn`, `us`, `hex-prod` |
| **Группа** | Значение поля `group` у устройств и ключ в `groups` Oxidized | `hex`, `us`, `default` |

Обычно для стандартного деплоя:

| Профиль | Группа | Откуда берётся |
|---------|--------|----------------|
| `ovn` | `hex` | `network_inventory.yml` → `environments.hex`, пароли `OVN_*` |
| `us` | `us` | `environments.us`, пароли `US_*` |

Имя профиля и группа **могут совпадать** (`hex` / `hex`), но это не обязательно.

## Связь с устройствами

Каждое устройство в инвентаре имеет поле **group**:

```yaml
devices:
  - name: hex_r1_ukg
    ip: 10.216.92.1
    group: hex      # ← использует credentials группы hex
    model: routeros
```

При бэкапе Oxidized:

1. Берёт `group` устройства
2. Ищет username/password/model в `groups.<group>`
3. Подключается по SSH с этими credentials

## Как появляются группы

### Автоматически — import network_inventory

**Настройки → Сервис → Import network inventory** или `POST /inventory/import-network`:

- Создаёт профили `ovn` (group `hex`) и `us` (group `us`)
- Пароли из `.env`: `OVN_USER`, `OVN_PASS`, `US_USER`, `US_PASS`
- Добавляет подсети и gateway-устройства

### Вручную — форма «Добавить группу»

Требуется право **`credentials:write`** (роль admin).

Пример для группы `hex`:

| Поле | Значение |
|------|----------|
| Имя профиля | `ovn` или `hex` |
| Группа | `hex` |
| Username | `satcoadm` (из `OVN_USER`) |
| Model | `routeros` |
| Password | пароль SSH (из `OVN_PASS`) |

После добавления выполните **Oxidized → Sync** (или изменения подхватятся при save).

## Таблица групп

| Колонка | Описание |
|---------|----------|
| Профиль | Имя записи |
| Группа | Ключ для устройств / Oxidized |
| Model | Модель Oxidized для группы (`routeros`, `ios`, …) |
| Username | SSH-логин |
| Password | SSH-пароль (виден admin; operator — скрыт) |

Кнопки **Сохранить** / **Удалить** — `PUT/DELETE /inventory/credentials/{name}`.

Изменение model обновляет `oxidized/config` → `groups.<group>.model`.

## Права доступа

| Действие | Permission | Роли |
|----------|------------|------|
| Просмотр таблицы | `credentials:read` | admin |
| Просмотр без паролей | — | operator (username виден, password `********`) |
| Добавление/редактирование | `credentials:write` | admin |

Operator **не** видит вкладку редактирования паролей, но видит группы для привязки устройств.

## API

```http
POST /inventory/credentials
{
  "name": "ovn",
  "group_name": "hex",
  "username": "satcoadm",
  "password": "secret",
  "model": "routeros"
}

PUT /inventory/credentials/ovn
{
  "username": "satcoadm",
  "password": "newpass",
  "group_name": "hex",
  "model": "routeros"
}

DELETE /inventory/credentials/ovn
```

## Типовые сценарии

### Пустая таблица после установки

1. Проверьте `.env`: `OVN_PASS`, `US_PASS` заполнены
2. **Import network inventory** (файл `inventory/network_inventory.yml` на хосте)
3. Или добавьте группы вручную на вкладке **Группы**

### Смена пароля SSH

1. **Настройки → Группы** → изменить Password → Сохранить
2. **Oxidized → Sync**

### Новая зона (группа `lab`)

1. Добавить профиль: group `lab`, credentials
2. Добавить устройства с `group: lab` в инвентаре
3. Sync Oxidized

### Несколько групп — один пароль

Создайте отдельные профили с разными `group_name`, но одинаковыми username/password.

## Связанные документы

- [Инвентарь](inventory.md) — устройства и import YAML
- [Oxidized](oxidized.md) — sync credentials
- [Конфигурация](configuration.md) — `OVN_*`, `US_*` в `.env`
