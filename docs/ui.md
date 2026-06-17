# Web-интерфейс

URL: **http://&lt;host&gt;:8000/ui**

SPA на AdminLTE 3. Аутентификация через JWT (cookie). Разделы и кнопки скрываются по RBAC (`data-permission`).

## Разделы навигации

| Раздел | ID | Мин. роль | Описание |
|--------|-----|-----------|----------|
| Dashboard | `dashboard` | viewer | Сводка: устройства, scan, Oxidized health |
| Инвентарь | `inventory` | viewer | Устройства, подсети, import network |
| Scan | `scan` | operator | Scan / Discovery, прогресс, результаты |
| Oxidized | `oxidized` | viewer | Узлы, fetch, sync, diff, MikroTik files |
| Oxidized Web | `oxidized-ui` | viewer | Proxy Ruby UI (external) или справка |
| Настройки | `settings` | mixed | Бэкап, уведомления, группы, LDAP, сервис |
| Пользователи | `users` | admin | CRUD пользователей, RBAC matrix |

**Глобальный поиск** в шапке фильтрует таблицы по имени, IP, группе, модели (Esc — очистить).

## Dashboard

- Карточки: устройства, online/offline scan, Oxidized nodes, engine title
- Быстрые ссылки на Scan и Oxidized
- Health из `/api/oxidized/health`

## Инвентарь

- Таблица устройств: имя, IP, группа, модель, enabled, порты
- **Добавить устройство** (operator+)
- **Import network inventory** (admin, `inventory:write`)
- **Cleanup discovered** — удалить устройства `discovered-*` (admin)
- Редактирование inline / modal

## Scan

- **Scan** — проверка известных устройств
- **Scan + Discovery** — ping sweep + добавление новых
- Live progress bar, лог job
- Таблица результатов с фильтром по статусу

## Oxidized

- Engine badge: Python Oxidized / Ruby Oxidized
- Таблица узлов: status, last, mtime
- **Fetch** — принудительный сбор (operator+)
- **Sync** — sync credentials/source
- **Backup all** — очередь всех узлов (python only)
- Клик по узлу: конфиг, Git versions, diff
- **MikroTik files** — binary/export список и скачивание (routeros)

## Настройки

### Вкладка «Бэкап» (`oxidized:read/write`)

**Oxidized worker** — interval, threads, timeout, retries, SSH port, default model, group models, resolve DNS.

Сохранение → `PUT /api/settings/oxidized` → запись `oxidized/config` + reload engine.

**MikroTik binary/export** — binary, export, hide sensitive, encrypt password, purge, каталоги.

Сохранение → `PUT /api/settings/backup`.

> `OXIDIZED_ENGINE` и `GIT_REMOTE_URL` только из `.env` (отображаются read-only).

### Вкладка «Уведомления»

Telegram + SMTP, error/report toggles, тестовые кнопки.

См. [notifications.md](notifications.md).

### Вкладка «Группы»

SSH credentials и model per group. UI: **Настройки → Группы**.

Подробнее: [groups.md](groups.md).

- Профиль `ovn` → группа `hex` (после import network_inventory)
- Редактирование паролей — только admin (`credentials:write`)

### Вкладка «LDAP» (`users:manage`)

Настройки LDAP/AD, тест bind.

### Вкладка «Сервис» (`inventory:write`)

- Import network inventory
- Cleanup discovered devices
- Scan concurrency (read-only из env)

## Oxidized Web

- **external**: iframe `/oxidized-proxy/nodes`
- **python**: информационная страница + ссылка на раздел Oxidized

## Первый запуск — чеклист

1. Войти как admin
2. **Настройки → Группы** — проверить credentials hex/us
3. **Инвентарь → Import** — загрузить подсети
4. **Scan + Discovery**
5. **Oxidized → Sync**
6. **Настройки → Бэкап** — interval, MikroTik options
7. (опц.) **Уведомления** — Telegram/SMTP + тест

## Связанные документы

- [Аутентификация](authentication.md) — роли и права
- [API](api.md) — REST для автоматизации
- [Типы движков](engines.md) — Python vs Ruby
