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
- **Compliance бэкапов** — процент OK, счётчики по состояниям, таблица проблемных устройств (`GET /api/compliance/summary`)
- Быстрые ссылки на Scan и Oxidized
- Health из `/api/oxidized/health`

См. [compliance.md](compliance.md).

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

Вкладки: **Бэкап**, **Git**, **Уведомления**, **Группы**, **LDAP**, **Сервис**.

### Вкладка «Бэкап» (`oxidized:read/write`)

**Oxidized worker** — interval, threads, timeout, retries, SSH port, default model, group models, resolve DNS.

Сохранение → `PUT /api/settings/oxidized` → запись `oxidized/config` + reload engine.

**MikroTik binary/export** — binary, export, hide sensitive, encrypt password, purge, каталоги.

Сохранение → `PUT /api/settings/backup` (только MikroTik-поля).

> `OXIDIZED_ENGINE` только из `.env` (read-only в UI).

### Вкладка «Git» (`oxidized:read/write`)

Remote URL, ветка, Gitea token/user, commit author, source token, Oxidized public URL.

Сохранение → `PUT /api/settings/git`. SSH-ключи — `oxidized-ssh/`, не редактируются в UI.

### Вкладка «Уведомления» (`oxidized:read/write`)

Telegram + SMTP; три блока: **ошибки**, **отчёты**, **деградация** (stale/offline/overdue).

Параметры деградации: stale (дней), cooldown (ч), интервал проверки (сек).

| Кнопка | Действие |
|--------|----------|
| Сохранить уведомления | `PUT /api/settings/backup` |
| Тест отчёта / ошибки / деградации | `POST test-notify` с `kind` и полями формы |
| Проверить деградацию | `POST /api/settings/backup/degrade-check` |

Тест использует галочки и chat ID из формы; token/password — из поля или БД.

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
- **Scan / discovery** — concurrency, max hosts, ping workers → `PUT /api/settings/scan`
- **Seed credentials** — OVN/US user/password для import (не путать с группами Oxidized)

## Oxidized Web

- **external**: iframe `/oxidized-proxy/nodes`
- **python**: информационная страница + ссылка на раздел Oxidized

## Первый запуск — чеклист

1. Войти как admin
2. **Настройки → Группы** — проверить credentials hex/us
3. **Инвентарь → Import** — загрузить подсети
4. **Scan + Discovery**
5. **Oxidized → Sync**
6. **Настройки → Git** — remote URL, token (если нужен push)
7. **Настройки → Бэкап** — interval, MikroTik options
8. (опц.) **Уведомления** — Telegram/SMTP + тест + degrade

## Связанные документы

- [Аутентификация](authentication.md) — роли и права
- [API](api.md) — REST для автоматизации
- [Типы движков](engines.md) — Python vs Ruby
