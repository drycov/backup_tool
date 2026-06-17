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
    logger.info("scanner | startup")
    init_db()
    from services.ldap_settings import ensure_initialized

    ensure_initialized()
    from services.backup_settings import ensure_initialized as ensure_backup_initialized

    ensure_backup_initialized()

    from django.conf import settings

    inventory = load_inventory()
    update_oxidized_credentials(inventory)

    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python":
        from services.oxidized_engine import start_engine

        start_engine()
        logger.info("oxidized | python engine started")
        logger.info(
            "oxidized | python mode — stop external oxidized container "
            "(docker compose --profile external stop oxidized) to avoid conflicts"
        )
    else:
        logger.info("oxidized | ruby engine mode — config synced, worker in oxidized container")

    from services.degradation_monitor import start_degradation_monitor

    start_degradation_monitor()

    _initialized = True
