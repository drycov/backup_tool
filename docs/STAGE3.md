# Этап 3 — Расширение функционала (квартал)

Дорожная карта на ~3 месяца. Зависимости и порядок фаз учитывают Stage 1–2 (тесты, health, task queue, observability, audit).

## Фаза 3.0 — Фундамент (недели 1–2) ✅ частично

| Задача | Статус | Артефакты |
|--------|--------|-----------|
| API keys для CI/Ansible | реализовано | `ApiKey`, `X-API-Key` / `Bearer bk_…` |
| Fine-grained RBAC | реализовано | `compliance:read`, `settings:notify`, `audit:read`, `api_keys:manage` |
| LDAP → object scope (AD groups) | реализовано | `LdapConfig.scope_mappings` JSON |
| Теги устройств | реализовано | `Device.tags` |
| OpenAPI | реализовано | `GET /api/openapi.json`, `/api/docs` |
| Compliance по site (дашборд) | реализовано | `GET /api/compliance/by-site` |

## Фаза 3.1 — Бэкапы и устройства (недели 3–6) — частично ✅

| Задача | Статус |
|--------|--------|
| Native models ios/junos/eos | ✅ `model/{ios,junos,eos}.py` + registry |
| Group policies notify/SLA/maintenance | ✅ migration `0012`, `group_policies.py` |
| MikroTik restore + compare API | ✅ `mikrotik_restore.py`, UI Restore |
| Oxidized external unified diff | ⏳ фаза 3.1b |

---

## Фаза 3.2 — Безопасность и доступ (недели 5–8)

### LDAP → object scope (автоматика)

**Реализовано (3.0):** `scope_mappings` — JSON-массив `{ldap_group, allowed_groups[], allowed_sites[]}`.

**Дальше:**
- UI редактор mappings в Settings → LDAP.
- Preview scope при LDAP test login.
- Синхронизация scope при каждом login (не перезаписывать ручные правки если `scope_locked` на user).

### API keys

**Реализовано (3.0):** CRUD admin, scope + permissions на ключ.

**Дальше:**
- Ротация ключей, audit `api_key.use`.
- Ansible module examples в `docs/integrations.md`.

### 2FA TOTP (local admin)

**План:**
- `User.totp_secret`, `totp_enabled`
- Login flow: password → `POST /api/auth/totp` → JWT
- Recovery codes (10 одноразовых)
- Библиотека: `pyotp`

### Fine-grained permissions

**Реализовано (3.0):** новые permission IDs + матрица RBAC.

**Дальше:**
- Custom roles (таблица `Role` + M2M permissions), UI конструктор ролей.
- Роль `compliance_auditor`: только `compliance:read` + `audit:read`.

---

## Фаза 3.3 — Интеграции (недели 7–10)

### Slack / Microsoft Teams

Абстракция `NotificationChannel` поверх `backup_notifications.py`:
- `slack_webhook_url`, `teams_webhook_url` в `BackupConfig`
- Форматтеры: Block Kit / MessageCard
- Переключатель per event type (error, report, degrade, compliance)

### ServiceNow / Jira

- `IntegrationConfig` singleton: SNOW instance, Jira URL, credentials
- `create_ticket(event, devices)` при `backup_failed` / `device_offline`
- Dedupe по `alert_key` (как `AlertState`)

### Webhook на audit (SIEM)

- `AUDIT_WEBHOOK_URL` + HMAC подпись
- POST JSON на каждый `AuditEvent.create` (async via task queue)
- Фильтр action prefix

### OpenAPI

**Реализовано (3.0):** базовая спецификация + Swagger UI.

**Дальше:** автогенерация из Pydantic schemas, CI проверка drift.

---

## Фаза 3.4 — Инвентарь и сеть (недели 9–12)

### Импорт NetBox / LibreNMS

| Источник | API | Маппинг |
|----------|-----|---------|
| NetBox | `/api/dcim/devices/` | name, ip, site, role, tags, device_type → model |
| LibreNMS | `/api/v0/devices` | hostname, ip, location → site |

`POST /inventory/import/netbox`, `import/librenms` + scheduled sync task.

### Теги и иерархия

**Реализовано (3.0):** `Device.tags: string[]`.

**Дальше:**
- Фильтры по тегам в compliance/inventory UI
- Иерархия: `Site` model (parent site), device.site FK

### Топология / карта сети

**Минимум (3.4a):** группировка compliance по site на дашборде ✅.

**Расширение (3.4b):**
- Граф связей из NetBox cables (readonly)
- Dashboard widgets: site cards, critical count, compliance %

---

## Матрица приоритетов

```
P0 (блокеры production):  API keys, LDAP scope, OpenAPI
P1 (операционная ценность): IOS/JunOS models, MikroTik restore, Slack/Teams
P2 (enterprise):           SNOW/Jira, 2FA, custom roles, NetBox sync
P3 (nice-to-have):         Network topology graph, bin binary diff
```

## Критерии готовности этапа

- [ ] ≥3 vendor models в backup (routeros + 2 других)
- [ ] Restore MikroTik из UI с audit
- [ ] LDAP login автоматически задаёт scope в 80%+ кейсов
- [ ] API keys используются в CI pipeline (документированный пример)
- [ ] OpenAPI покрывает ≥80% `/api/*` endpoints
- [ ] NetBox import E2E тест с mock API
- [ ] 2FA включена для local admin

## Связанные документы

- [OBSERVABILITY.md](../deploy/OBSERVABILITY.md) — метрики/алерты
- [authentication.md](authentication.md) — LDAP, RBAC
- [engines.md](engines.md) — Python vs Ruby Oxidized
- [api.md](api.md) — REST каталог (дополняется OpenAPI)
