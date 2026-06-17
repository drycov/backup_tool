import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("JWT_SECRET", "change-me-in-production")
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "*").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "core",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "backup_tools.urls"
WSGI_APPLICATION = "backup_tools.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "inventory"),
        "USER": os.environ.get("POSTGRES_USER", "backup"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "backup"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

if os.environ.get("DATABASE_URL"):
    import re

    match = re.match(
        r"postgresql(\+psycopg2)?://(?P<user>[^:]+):(?P<password>[^@]+)@"
        r"(?P<host>[^:/]+)(:(?P<port>\d+))?/(?P<name>.+)",
        os.environ["DATABASE_URL"],
    )
    if match:
        g = match.groupdict()
        DATABASES["default"].update(
            {
                "NAME": g["name"],
                "USER": g["user"],
                "PASSWORD": g["password"],
                "HOST": g["host"],
                "PORT": g["port"] or "5432",
            }
        )

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
}

# App settings (from .env)
JWT_SECRET = SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
AUTH_COOKIE_NAME = os.environ.get("AUTH_COOKIE_NAME", "backup_tools_token")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

OXIDIZED_URL = os.environ.get("OXIDIZED_URL", "http://oxidized:8888").rstrip("/")
OXIDIZED_ENGINE = os.environ.get("OXIDIZED_ENGINE", "python").lower()
OXIDIZED_INTERVAL = int(os.environ.get("OXIDIZED_INTERVAL", "3600"))
OXIDIZED_THREADS = int(os.environ.get("OXIDIZED_THREADS", "10"))
OXIDIZED_TIMEOUT = int(os.environ.get("OXIDIZED_TIMEOUT", "20"))
OXIDIZED_RETRIES = int(os.environ.get("OXIDIZED_RETRIES", "3"))
OXIDIZED_GIT_REPO = os.environ.get("OXIDIZED_GIT_REPO", "/var/lib/oxidized")
OXIDIZED_PUBLIC_URL = os.environ.get(
    "OXIDIZED_PUBLIC_URL", "http://localhost:8888"
).rstrip("/")
OXIDIZED_SOURCE_URL = os.environ.get(
    "OXIDIZED_SOURCE_URL",
    "http://scanner:8000/api/oxidized/source",
)
OXIDIZED_SOURCE_TOKEN = os.environ.get("OXIDIZED_SOURCE_TOKEN", "")

INVENTORY_PATH = os.environ.get("INVENTORY_PATH", "/data/inventory/inventory.yaml")
NETWORK_INVENTORY_PATH = os.environ.get(
    "NETWORK_INVENTORY_PATH", "/data/inventory/network_inventory.yml"
)
ROUTER_DB_PATH = os.environ.get("ROUTER_DB_PATH", "/data/oxidized/router.db")
OXIDIZED_CONFIG_PATH = os.environ.get("OXIDIZED_CONFIG_PATH", "/data/oxidized/config")
OXIDIZED_HOME = os.environ.get("OXIDIZED_HOME", "/data/oxidized")
OXIDIZED_LOG_PATH = os.environ.get(
    "OXIDIZED_LOG_PATH", "/var/lib/oxidized/oxidized.log"
)
OXIDIZED_PYTHON_LOG_PATH = os.environ.get(
    "OXIDIZED_PYTHON_LOG_PATH", "/var/lib/oxidized/oxidized-python.log"
)
ROUTEROS_SSH_PORT = int(os.environ.get("ROUTEROS_SSH_PORT", "44333"))
SCAN_CONCURRENCY = max(1, int(os.environ.get("SCAN_CONCURRENCY", "50")))

GIT_REMOTE_URL = os.environ.get("GIT_REMOTE_URL", "")
GITEA_TOKEN = os.environ.get("GITEA_TOKEN", "")
GITEA_HTTP_USER = os.environ.get("GITEA_HTTP_USER", "oauth2")

OVN_USER = os.environ.get("OVN_USER", "satcoadm")
OVN_PASS = os.environ.get("OVN_PASS", "")
US_USER = os.environ.get("US_USER", "satcoadm")
US_PASS = os.environ.get("US_PASS", "")
