"""Centralized logging configuration."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the application-wide logger.

    Args:
        level: Logging level (default INFO).

    Returns:
        Configured root logger for the application.
    """
    logger = logging.getLogger("job_app_bot")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)

    return logger
