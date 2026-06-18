import logging

logger = logging.getLogger(__name__)
_initialized = False


def initialize() -> None:
    global _initialized
    if _initialized:
        return
    from services.log_config import setup_logging
    from services.inventory import init_db, load_inventory, update_oxidized_credentials

    setup_logging()
    from django.conf import settings as dj_settings

    logger.info("scanner | startup | database=%s", dj_settings.DATABASE_URL_DISPLAY)
    init_db()
    from services.ldap_settings import ensure_initialized

    ensure_initialized()
    from services.backup_settings import ensure_initialized as ensure_backup_initialized

    from services.git_settings import ensure_initialized as ensure_git_initialized
    from services.scan_settings import ensure_initialized as ensure_scan_initialized

    ensure_git_initialized()
    ensure_scan_initialized()
    ensure_backup_initialized()
    from services.integration_settings import ensure_initialized as ensure_integration_initialized

    ensure_integration_initialized()

    from django.conf import settings

    inventory = load_inventory()
    update_oxidized_credentials(inventory)

    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python":
        from services.oxidized_logging import configure_oxidized_file_logging
        from services.oxidized_engine import start_engine

        configure_oxidized_file_logging()
        start_engine()
        logger.info("oxidized | python engine started")
        logger.info(
            "oxidized | python mode — stop external oxidized container "
            "(docker compose --profile external stop oxidized) to avoid conflicts"
        )
    else:
        logger.info("oxidized | ruby engine mode — config synced, worker in oxidized container")

    from services.task_worker import start_inline_task_worker

    start_inline_task_worker()

    _initialized = True
