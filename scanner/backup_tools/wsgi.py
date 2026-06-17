import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backup_tools.settings")

application = get_wsgi_application()

from services.startup import initialize  # noqa: E402

initialize()
