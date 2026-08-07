"""
Logging setup for StoryShorts AI.

Configures a human-readable console logger (for local runs and CI logs).
No log files are written — the pipeline renders a short and uploads it
directly, leaving no artifacts behind. Downstream pipeline stages call
`get_logger(__name__)` rather than configuring logging themselves.
"""

from __future__ import annotations

import logging

from config.settings import Config

_CONFIGURED = False


def configure_logging(cfg: Config) -> None:
    """
    Configure the root logger once per process.

    Sets up a single console handler at `cfg.logging.level`. No file
    handlers — nothing is persisted after a run.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, cfg.logging.level.upper(), logging.INFO))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(console_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger. Call `configure_logging` first."""
    return logging.getLogger(name)
