"""Tests for the centralized logging configuration."""

import logging

from src.utils.logging import setup_logging


# ===================================================================
# setup_logging — basic behavior
# ===================================================================

class TestSetupLogging:

    def test_returns_logger(self):
        logger = setup_logging()
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        logger = setup_logging()
        assert logger.name == "job_app_bot"

    def test_default_level_is_info(self):
        logger = setup_logging()
        assert logger.level == logging.INFO

    def test_custom_level_debug(self):
        logger = setup_logging(level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_custom_level_warning(self):
        logger = setup_logging(level=logging.WARNING)
        assert logger.level == logging.WARNING

    def test_custom_level_error(self):
        logger = setup_logging(level=logging.ERROR)
        assert logger.level == logging.ERROR

    def test_has_at_least_one_handler(self):
        logger = setup_logging()
        assert len(logger.handlers) >= 1

    def test_handler_is_stream_handler(self):
        logger = setup_logging()
        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) >= 1

    def test_handler_has_formatter(self):
        logger = setup_logging()
        handler = logger.handlers[0]
        assert handler.formatter is not None

    def test_formatter_includes_levelname(self):
        logger = setup_logging()
        fmt = logger.handlers[0].formatter._fmt
        assert "%(levelname)s" in fmt

    def test_formatter_includes_name(self):
        logger = setup_logging()
        fmt = logger.handlers[0].formatter._fmt
        assert "%(name)s" in fmt

    def test_formatter_includes_asctime(self):
        logger = setup_logging()
        fmt = logger.handlers[0].formatter._fmt
        assert "%(asctime)s" in fmt

    def test_formatter_includes_message(self):
        logger = setup_logging()
        fmt = logger.handlers[0].formatter._fmt
        assert "%(message)s" in fmt

    def test_does_not_duplicate_handlers(self):
        logger = setup_logging()
        count_before = len(logger.handlers)
        setup_logging()
        count_after = len(logger.handlers)
        assert count_after == count_before

    def test_returns_same_logger_instance(self):
        logger1 = setup_logging()
        logger2 = setup_logging()
        assert logger1 is logger2

    def test_logger_can_log_info(self, caplog):
        logger = setup_logging()
        with caplog.at_level(logging.INFO, logger="job_app_bot"):
            logger.info("test message")
        assert "test message" in caplog.text

    def test_logger_can_log_error(self, caplog):
        logger = setup_logging()
        with caplog.at_level(logging.ERROR, logger="job_app_bot"):
            logger.error("error occurred")
        assert "error occurred" in caplog.text
