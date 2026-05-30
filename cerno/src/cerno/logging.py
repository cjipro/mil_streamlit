"""Structured logger bound to a run_id.

`get_logger(name, run_id)` returns a stdlib Logger with a formatter that
includes the run_id on every record. Idempotent — calling twice on the
same logger name does not double-attach handlers.
"""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] run_id=%(run_id)s %(message)s"
_HANDLER_FLAG = "_cerno_handler"


class _RunIdInjector(logging.Filter):
    """Attaches the run_id attribute to every record passing through."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.run_id = self._run_id
        return True


def get_logger(name: str, run_id: str) -> logging.Logger:
    """Return a Logger bound to `run_id`, formatted structurally.

    Idempotent on handler attachment per logger name. The run_id filter
    is re-attached on every call so callers can update the binding
    mid-process without surprises.
    """
    logger = logging.getLogger(name)
    # Attach the StreamHandler only once.
    if not any(getattr(h, _HANDLER_FLAG, False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT))
        setattr(handler, _HANDLER_FLAG, True)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    # Filters are scoped to the current run_id — clear stale injectors first.
    logger.filters = [f for f in logger.filters if not isinstance(f, _RunIdInjector)]
    logger.addFilter(_RunIdInjector(run_id))
    return logger
