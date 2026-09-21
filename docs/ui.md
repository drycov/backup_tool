# Web-интерфейс

URL: **http://&lt;host&gt;:8000/ui** (в production — HTTPS через reverse proxy, см. [deploy/HTTPS.md](../deploy/HTTPS.md))

SPA на **AdminLTE 4** / Bootstrap 5. Аутентификация через JWT (cookie). Разделы и кнопки скрываются по RBAC (`data-permission`).

Deep-link настройки: `#settings/backup`, `#settings/groups`, `#settings/service` и т.д.

## Разделы навигации

| Раздел | ID | Мин. роль | Описание |
|--------|-----|-----------|----------|
| Dashboard | `dashboard` | viewer | Сводка: устройства, scan, Oxidized health, compliance |
| Инвентарь | `inventory` | viewer | Устройства, подсети, bulk-операции |
| Scan | `scan` | operator | Scan / Discovery, прогресс, результаты |
| Oxidized | `oxidized` | viewer | Узлы, fetch, sync, diff, MikroTik files |
| Oxidized Web | `oxidized-ui` | viewer | Встроенный UI (python) или proxy (external) |
| Настройки | `settings` | mixed | Боковое меню: бэкап, Git, уведомления, группы, LDAP, сервис |
| Журнал | `audit` | admin | Audit log |
| Пользователи | `users` | admin | CRUD, RBAC matrix, object scope |

**Глобальный поиск** в шапке фильтрует таблицы (Esc — очистить).

**Object scope** — banner в шапке для operator/viewer с ограничением по `allowed_groups` / `allowed_sites`.

## Dashboard

- Stat-плитки: устройства, подсети, scan, Oxidized
- **Compliance бэкапов** — фильтры site/role/group/state/critical
- Экспорт: **CSV**, **PDF** (`GET /api/compliance/export?format=pdf`)
- Рассылка с учётом scope и фильтров: **POST /api/compliance/report/send`

## Инвентарь

- Таблица устройств с чекбоксами (operator+)
- **Bulk**: enable/disable, maintenance on/off, смена группы → `POST /inventory/devices/bulk`
- Подсети для discovery, modal редактирования устройства

## Настройки

Макет: **вертикальное меню слева** + контент справа. Секции оформлены карточками `.settings-section`.

| Вкладка | Права | API |
|---------|-------|-----|
| Бэкап | `oxidized:read/write` | `PUT /api/settings/oxidized`, `PUT /api/settings/backup` |
| Git | `oxidized:read/write` | `PUT /api/settings/git` |
| Уведомления | `oxidized:read/write` | `PUT /api/settings/backup` (notify-поля) |
| Группы | credentials + policies | credentials CRUD, `PUT /api/policies/groups` |
| LDAP | `users:manage` | `PUT /api/settings/ldap`, `POST /api/settings/ldap/test` |
| Сервис | `inventory:write` | scan settings, maintenance window, import |

При несохранённых изменениях показывается предупреждение; смена вкладки — с подтверждением.

Вкладка **ENV** показывает фактическое runtime-окружение контейнера scanner по группам с поиском и фильтрацией. Секретные переменные отображаются маской. Кнопка **Экспорт snapshot** выгружает безопасный `.env` snapshot без секретов.

### Окно обслуживания (вкладка «Сервис»)

UTC-часы и дни недели; устройства с флагом `maintenance` пропускают scheduled backup в окне.

## Безопасность

- При первом входе admin с паролем по умолчанию (`changeme`) — **обязательная смена пароля**
- `JWT_SECRET` ≥ 32 символов в production
- За HTTPS: `BEHIND_HTTPS_PROXY=true` в `.env`

## Health

| Endpoint | Назначение |
|----------|------------|
| `GET /health` | Liveness |
| `GET /health/ready` | Readiness: БД + Oxidized worker (503 если не готов) |

## Первый запуск — чеклист

1. Войти как admin (сменить пароль при запросе)
2. **Настройки → Группы** — credentials hex/us
3. **Инвентарь** — подсети, scan/discovery
4. **Oxidized → Sync**
5. **Настройки → Git** и **Бэкап**
6. (опц.) **Уведомления** + compliance-отчёт

## Связанные документы

- [Аутентификация](authentication.md)
- [API](api.md)
- [Compliance](compliance.md)
- [HTTPS / reverse proxy](../deploy/HTTPS.md)
