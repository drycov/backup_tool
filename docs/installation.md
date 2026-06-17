# Установка

## Требования

- Docker Engine 24+ и Docker Compose v2
- Доступ к сети устройств (ICMP ping, TCP на SSH-порт, по умолчанию `44333` для RouterOS)
- Для Git push: Gitea/GitLab/GitHub с deploy key или token
- Для LDAP: доступ контейнера scanner к LDAP/AD (порт 389/636)

Рекомендуемые ресурсы сервера:

| Компонент | CPU | RAM | Диск |
|-----------|-----|-----|------|
| Минимум | 2 vCPU | 2 GB | 20 GB |
| Production (500+ устройств) | 4 vCPU | 4 GB | 50 GB+ |

## Установка через Docker Compose

### 1. Клонирование и подготовка

```bash
git clone <url-репозитория> /opt/backup-tools
cd /opt/backup-tools
chmod +x deploy/init-stack.sh oxidized/entrypoint.sh
./deploy/init-stack.sh .
```

Скрипт `deploy/init-stack.sh`:

- создаёт каталоги `inventory/`, `oxidized/`, `oxidized-ssh/`;
- копирует `.env.example` → `.env` (если нет);
- копирует `oxidized/config.example` → `oxidized/config` (если нет);
- нормализует CRLF в `oxidized/entrypoint.sh`.

### 2. Настройка `.env`

Минимально измените:

```env
JWT_SECRET=<случайная строка ≥ 32 символов>
ADMIN_PASSWORD=<пароль администратора UI>
POSTGRES_PASSWORD=<пароль PostgreSQL>
OVN_PASS=<пароль SSH для группы hex>
US_PASS=<пароль SSH для группы us>
```

Полный список переменных: [configuration.md](configuration.md).

### 3. Инвентарь подсетей

Поместите файл `inventory/network_inventory.yml` с описанием подсетей (см. [inventory.md](inventory.md)).

### 4. Запуск

```bash
# Python-движок Oxidized (по умолчанию, один контейнер oxidized не нужен)
docker compose up -d --build

# С внешним Ruby Oxidized
docker compose --profile external up -d --build
```

### 5. Проверка

| URL | Ожидание |
|-----|----------|
| http://localhost:8000/ui | Страница входа |
| http://localhost:8000/health | `{"status":"ok",...}` |
| http://localhost:8888 | Oxidized Web UI (только external) |

```bash
docker compose ps
docker compose logs -f scanner
```

## Установка через Portainer

Пошаговая инструкция: [deploy/PORTAINER.md](../deploy/PORTAINER.md).

Краткий алгоритм:

1. Подготовить сервер: `./deploy/init-stack.sh /opt/backup-tools`
2. Настроить `.env`, `oxidized/config`, SSH-ключи
3. Portainer → Stacks → Git repository → `docker-compose.yml`
4. Вставить переменные из `.env`, при необходимости `STACK_PATH=/opt/backup-tools`
5. Deploy the stack

## SSH-ключи для Git push

См. [oxidized-ssh/README.md](../oxidized-ssh/README.md) и раздел [Oxidized → Git push](oxidized.md#git-push).

## Первый вход

1. Откройте http://&lt;host&gt;:8000/ui
2. Войдите с `ADMIN_USERNAME` / `ADMIN_PASSWORD` (по умолчанию `admin`)
3. **Настройки** → импортируйте `network_inventory` или добавьте устройства вручную
4. Запустите scan с discovery для обнаружения устройств
5. Проверьте раздел **Oxidized** — статус узлов и бэкапы

## Обновление

```bash
cd /opt/backup-tools
git pull
docker compose up -d --build
```

В Portainer: Redeploy stack (Pull and redeploy / webhook).

## Локальная разработка (без Docker)

```bash
cd scanner
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export DATABASE_URL=postgresql+psycopg2://backup:backup@localhost:5432/inventory
export JWT_SECRET=dev-secret-change-me-in-production-min-32-chars
export ADMIN_PASSWORD=admin

python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

PostgreSQL и пути к inventory/oxidized нужно настроить отдельно. Для production используйте Docker.
