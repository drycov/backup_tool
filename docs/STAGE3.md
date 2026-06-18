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
| Oxidized external unified diff | ✅ `oxidized_diff.py` (python + external) |

---

## Фаза 3.2 — Безопасность и доступ (недели 5–8) — частично ✅

| Задача | Статус |
|--------|--------|
| 2FA TOTP (local users) | ✅ migration `0013`, `totp_auth.py`, login challenge |
| TOTP UI (login step + Users page) | ✅ |
| LDAP scope mappings UI | ✅ Settings → LDAP |
| LDAP test → scope preview | ✅ `allowed_groups` / `allowed_sites` в ответе |
| External Oxidized unified diff | ✅ (перенесено из 3.1b) |
| Custom roles + `scope_locked` | ⏳ |

### LDAP → object scope (автоматика)

**Реализовано:** `scope_mappings` — JSON-массив `{ldap_group, allowed_groups[], allowed_sites[]}`; UI-редактор; preview при LDAP test login.

**Дальше:**
- Синхронизация scope при каждом login (не перезаписывать ручные правки если `scope_locked` на user).

### API keys

**Реализовано (3.0):** CRUD admin, scope + permissions на ключ.

**Дальше:**
- Ротация ключей, audit `api_key.use`.
- Ansible module examples в `docs/integrations.md`.

### 2FA TOTP (local admin)

**Реализовано:** `User.totp_secret`, `totp_enabled`, recovery codes; login flow password → `POST /api/auth/totp` → JWT; `pyotp`.

### Fine-grained permissions

**Реализовано (3.0):** новые permission IDs + матрица RBAC.

**Дальше:**
- Custom roles (таблица `Role` + M2M permissions), UI конструктор ролей.
- Роль `compliance_auditor`: только `compliance:read` + `audit:read`.

---

## Фаза 3.3 — Интеграции (недели 7–10) — частично ✅

| Задача | Статус |
|--------|--------|
| Slack / Teams webhooks | ✅ `notification_channels.py`, toggles per event type |
| ServiceNow / Jira tickets | ✅ `IntegrationConfig`, dedupe `AlertState` |
| Audit SIEM webhook + HMAC | ✅ `audit_webhook.py`, task `audit.webhook` |
| UI Settings → Интеграции | ✅ |
| OpenAPI autogen drift CI | ⏳ |

### Slack / Microsoft Teams

**Реализовано:** Block Kit / MessageCard; `slack_webhook_url`, `teams_webhook_url` в BackupConfig; галочки error/report/degrade/compliance.

### ServiceNow / Jira

**Реализовано:** `IntegrationConfig` singleton; `create_ticket()` при `backup_failed` и `device_offline`; cooldown через `ticket_cooldown_hours`.

### Webhook на audit (SIEM)

**Реализовано:** `audit_webhook_*` в IntegrationConfig; HMAC `X-Backup-Tools-Signature`; async `BackgroundTask.TASK_AUDIT_WEBHOOK`; фильтр `audit_webhook_action_prefix`.

### OpenAPI

**Реализовано (3.0):** базовая спецификация + Swagger UI.

**Дальше:** автогенерация из Pydantic schemas, CI проверка drift.

---

## Фаза 3.4 — Инвентарь и сеть (недели 9–12) — частично ✅

| Задача | Статус |
|--------|--------|
| Импорт NetBox | ✅ `POST /api/inventory/import/netbox` |
| Импорт LibreNMS | ✅ `POST /api/inventory/import/librenms` |
| Scheduled inventory sync | ✅ `TASK_INVENTORY_SYNC` |
| Site иерархия | ✅ модель `Site`, expand children при фильтре |
| Фильтры tags (compliance + inventory UI) | ✅ |
| NetBox cables / topology graph | ⏳ 3.4b |

### Импорт NetBox / LibreNMS

**Реализовано:** upsert устройств по имени; маппинг site/role/tags/model; настройки в IntegrationConfig; UI Import + scheduled sync.

### Теги и иерархия

**Реализовано (3.0):** `Device.tags: string[]`.

**Реализовано (3.4):** фильтр `tags` в compliance API/UI; `Site` parent/child; object scope учитывает дочерние sites.

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
