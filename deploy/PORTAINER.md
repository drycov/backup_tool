# Развёртывание Backup Tools через Portainer

Стек: **PostgreSQL** + **Scanner (Django UI)** + **Oxidized**.

## Требования

- Portainer CE/BE 2.x с доступом к Docker
- Git-репозиторий с этим проектом **или** копия файлов на сервере
- Открытые порты (по умолчанию): `8000` (Scanner UI), `8888` (Oxidized Web)
- Доступ scanner-кontainer к сети устройств (ICMP/SSH для scan/discovery)

## 1. Подготовка сервера

```bash
git clone <url-репозитория> /opt/backup-tools
cd /opt/backup-tools
chmod +x deploy/init-stack.sh oxidized/entrypoint.sh
./deploy/init-stack.sh /opt/backup-tools
nano .env
nano oxidized/config
```

Минимально измените в `.env`:

| Переменная | Описание |
|------------|----------|
| `JWT_SECRET` | Случайная строка ≥ 32 символов |
| `ADMIN_PASSWORD` | Пароль входа в UI |
| `POSTGRES_PASSWORD` | Пароль БД |
| `OVN_PASS`, `US_PASS` | Креды для групп hex/us |
| `OXIDIZED_PUBLIC_URL` | URL Oxidized снаружи, напр. `http://10.0.0.5:8888` |
| `GIT_REMOTE_URL`, `GITEA_TOKEN` | Push бэкапов в Gitea (если нужен) |

Опционально — данные на отдельном диске:

```env
STACK_PATH=/opt/backup-tools
```

## 2. SSH-ключи для Git push (Oxidized → Gitea)

См. [oxidized-ssh/README.md](../oxidized-ssh/README.md):

```bash
ssh-keygen -t rsa -b 4096 -m PEM -f oxidized-ssh/id_rsa -N ""
ssh-keyscan <gitea-host> >> oxidized-ssh/known_hosts
```

Deploy Key с правом **write** добавить в репозиторий Gitea.

## 3. Создание Stack в Portainer

### Вариант A — из Git (рекомендуется)

1. **Stacks** → **Add stack**
2. Имя: `backup-tools`
3. Build method: **Git repository**
4. Repository URL: URL вашего репо
5. Repository reference: `refs/heads/main` (или нужная ветка)
6. **Compose path**: `docker-compose.yml`
7. **Environment variables** — вставьте содержимое `.env` (или загрузите файл)
8. Добавьте переменную (если репо не в корне данных):

   ```env
   STACK_PATH=/opt/backup-tools
   ```

   Если Portainer клонирует репо в `/data/compose/<id>/`, можно оставить `STACK_PATH=.` (по умолчанию).

9. **Deploy the stack**

Включите **Pull and redeploy** / Webhook для автообновления при push в Git.

### Вариант B — Web editor

1. Скопируйте содержимое `docker-compose.yml` в редактор
2. Вставьте переменные окружения из `.env`
3. Убедитесь, что на хосте существуют bind-mount каталоги:

   ```
   ${STACK_PATH}/inventory
   ${STACK_PATH}/oxidized
   ${STACK_PATH}/oxidized-ssh
   ```

4. Deploy

> Web editor не подтягивает исходники scanner для `build:` — используйте Git или предварительно соберите образ (см. ниже).

### Предсборка образа scanner (без build в Portainer)

```bash
cd /opt/backup-tools/scanner
docker build -t backup-tools-scanner:latest .
```

В `docker-compose.yml` замените секцию `scanner.build` на:

```yaml
scanner:
  image: backup-tools-scanner:latest
```

## 4. Проверка после деплоя

| Сервис | URL | Ожидание |
|--------|-----|----------|
| Scanner UI | `http://<host>:8000/ui` | Страница входа |
| Health | `http://<host>:8000/health` | `{"status":"ok",...}` |
| Oxidized | `http://<host>:8888` | Web UI |

В Portainer → Stack → **backup-tools** все контейнеры должны быть **healthy** (db, scanner).

Первый вход: логин/пароль из `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

## 5. Обновление стека

**Git deploy:** Push в репо → Redeploy stack в Portainer (или webhook).

**Вручную на сервере:**

```bash
cd /opt/backup-tools
git pull
# Portainer: Update the stack
```

## 6. Volumes и данные

| Volume / каталог | Назначение |
|------------------|------------|
| `pg-data` | База PostgreSQL |
| `oxidized-data` | Git-репозиторий бэкапов Oxidized |
| `./inventory` | network_inventory.yml, inventory.yaml |
| `./oxidized` | config Oxidized |
| `./oxidized-ssh` | SSH-ключи для push |

## 7. Troubleshooting

**Scanner не стартует** — проверьте логи контейнера `scanner`, доступность `db:5432`.

**Oxidized не пушит в Git** — логи на странице Oxidized в UI scanner, файл `/var/lib/oxidized/oxidized.log`.

**Bind mount пустой** — неверный `STACK_PATH`; путь должен указывать на корень репозитория на хосте.

**CRLF в entrypoint.sh** — compose уже нормализует через `tr -d '\r'` при старте oxidized.
