#!/bin/sh
# Первичная подготовка каталогов на сервере перед деплоем в Portainer.
# Использование: ./deploy/init-stack.sh [/opt/backup-tools]

set -e

ROOT="${1:-.}"
cd "$ROOT"

echo "==> Каталог стека: $(pwd)"

mkdir -p inventory oxidized oxidized-ssh

if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Создан .env из .env.example — отредактируйте пароли и URL перед запуском"
else
  echo "==> .env уже существует, пропуск"
fi

if [ ! -f oxidized/config ]; then
  if [ -f oxidized/config.example ]; then
    cp oxidized/config.example oxidized/config
    echo "==> Создан oxidized/config из config.example"
  else
    echo "WARN: oxidized/config.example не найден"
  fi
else
  echo "==> oxidized/config уже существует, пропуск"
fi

if [ ! -f inventory/network_inventory.yml ]; then
  echo "WARN: inventory/network_inventory.yml отсутствует — добавьте подсети или импортируйте позже"
fi

if [ -f oxidized/entrypoint.sh ]; then
  sed -i 's/\r$//' oxidized/entrypoint.sh 2>/dev/null || tr -d '\r' < oxidized/entrypoint.sh > /tmp/ep && mv /tmp/ep oxidized/entrypoint.sh
  chmod +x oxidized/entrypoint.sh
fi

if [ ! -f oxidized-ssh/known_hosts ] && [ -f oxidized-ssh/known_hosts.example ]; then
  cp oxidized-ssh/known_hosts.example oxidized-ssh/known_hosts
  echo "==> Создан oxidized-ssh/known_hosts из example — добавьте ключи Gitea"
fi

echo ""
echo "Готово. Дальше:"
echo "  1. Отредактируйте .env (JWT_SECRET, ADMIN_PASSWORD, OVN_PASS, US_PASS, URL)"
echo "  2. Настройте oxidized/config и SSH-ключи (см. oxidized-ssh/README.md)"
echo "  3. Разверните stack в Portainer (см. deploy/PORTAINER.md)"
