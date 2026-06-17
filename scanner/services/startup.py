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
    update_oxidized_credentials(load_inventory())
    _initialized = True
