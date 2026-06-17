# Аутентификация и авторизация

## Обзор

- **JWT** (HS256) в HttpOnly cookie и заголовке `Authorization: Bearer`
- **Локальные пользователи** в PostgreSQL (bcrypt)
- **LDAP / Active Directory** — опционально, с маппингом групп на роли
- **RBAC** — три роли с набором permissions

## Вход в систему

```http
POST /api/auth/login
Content-Type: application/json

{"username": "admin", "password": "secret"}
```

Ответ:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "permissions": ["inventory:read", "..."]
  }
}
```

Cookie `backup_tools_token` устанавливается автоматически (HttpOnly, SameSite=Lax).

```http
POST /api/auth/logout
GET /api/auth/me
```

## Роли

| Роль | ID | Описание |
|------|-----|----------|
| Наблюдатель | `viewer` | Чтение инвентаря, scan results, Oxidized |
| Оператор | `operator` | + scan, устройства, fetch/sync Oxidized |
| Администратор | `admin` | Полный доступ, пароли, пользователи, LDAP |

### Матрица прав

| Permission | viewer | operator | admin |
|------------|:------:|:--------:|:-----:|
| `inventory:read` | ✓ | ✓ | ✓ |
| `inventory:devices` | | ✓ | ✓ |
| `inventory:write` | | | ✓ |
| `credentials:read` | | | ✓ |
| `credentials:write` | | | ✓ |
| `scan:read` | ✓ | ✓ | ✓ |
| `scan:run` | | ✓ | ✓ |
| `oxidized:read` | ✓ | ✓ | ✓ |
| `oxidized:write` | | ✓ | ✓ |
| `users:manage` | | | ✓ |

Матрица доступна в UI (**Пользователи**) и через `GET /api/ui/config`.

## Управление пользователями

Только роль **admin** (`users:manage`):

```http
GET    /api/auth/users
POST   /api/auth/users          {"username", "password", "role"}
GET    /api/auth/users/{id}
PUT    /api/auth/users/{id}     {"password", "role", "is_active"}
DELETE /api/auth/users/{id}
```

Начальный admin создаётся из `ADMIN_USERNAME` / `ADMIN_PASSWORD` при первом запуске.

## LDAP / Active Directory

### Первичная настройка

1. Задайте переменные в `.env` (см. [configuration.md](configuration.md))
2. При старте scanner импортирует их в таблицу `ldap_config`
3. Дальнейшее редактирование — **Настройки → LDAP / Active Directory** (только admin)

### API

```http
GET  /api/settings/ldap
PUT  /api/settings/ldap
POST /api/settings/ldap/test     {"username", "password"}
```

### Логика аутентификации

1. Если LDAP включён → попытка bind/search пользователя
2. Роль определяется по членству в `LDAP_ADMIN_GROUPS` / `LDAP_OPERATOR_GROUPS`
3. Если группы не совпали → `LDAP_DEFAULT_ROLE` (по умолчанию `viewer`)
4. Пользователь upsert в таблицу `users` (`auth_source=ldap`)
5. Если LDAP недоступен и `LDAP_FALLBACK_LOCAL=true` → локальная проверка пароля

### Active Directory

```env
LDAP_AD=true
LDAP_USER_FILTER=(sAMAccountName={username})
# или UPN:
LDAP_USER_UPN_SUFFIX=@corp.example.com
```

### OpenLDAP

```env
LDAP_AD=false
LDAP_USER_FILTER=(uid={username})
LDAP_USER_BASE=ou=users,dc=example,dc=com
```

### Группы

DN групп указываются по одному на строку в UI или через запятую в `.env`:

```env
LDAP_ADMIN_GROUPS=cn=backup-admins,ou=groups,dc=example,dc=com
LDAP_OPERATOR_GROUPS=cn=backup-operators,ou=groups,dc=example,dc=com
```

### Тест подключения

UI: **Настройки → LDAP → Тест** с произвольными credentials.

API: `POST /api/settings/ldap/test` — проверяет bind и определение роли без сохранения.

## Безопасность

| Параметр | Рекомендация |
|----------|--------------|
| `JWT_SECRET` | Криптостойкая случайная строка ≥ 32 символов |
| `ADMIN_PASSWORD` | Сменить сразу после установки |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 480 (8 ч) или меньше для строгих политик |
| `LDAP_BIND_PASSWORD` | Минимальные права read-only для AD/LDAP |
| HTTPS | Reverse proxy (nginx/traefik) перед scanner в production |

Пароли credential profiles и LDAP bind password маскируются в API (`********`) при ответах на GET.

## Заголовки авторизации

Клиенты могут использовать:

```
Cookie: backup_tools_token=<jwt>
```

или

```
Authorization: Bearer <jwt>
```

UI использует cookie (автоматически после login). API-скрипты — Bearer token.
