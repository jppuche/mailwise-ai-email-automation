import logging

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structured logging for mailwise.

    PII policy: log emails by email_id only — never subject, sender_email, or body.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structured logger.

    Usage: logger = get_logger(__name__)
    Always bind email_id for email-related operations — never subject/sender/body.
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]
