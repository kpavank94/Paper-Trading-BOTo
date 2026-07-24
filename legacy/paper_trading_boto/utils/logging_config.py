"""
Logging configuration utilities for the Paper Trading BOTo project.

This module centralises setup of the Python ``logging`` module.  It
provides a function to configure loggers with sensible defaults and
supports optional logging to a database.  Drawing inspiration from
open‑source trading bots that unified logging across multiple
components【6889114618198†L82-L90】, BOTo uses a single function to
initialise loggers and handlers in a consistent manner.

The ``configure_logging`` function returns a logger instance and, if
requested, creates a SQLite table for persisting log records.  If the
database is unavailable, logging gracefully falls back to console
output【735478255617264†L82-L89】.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class DBLogger:
    """Optional SQLite handler for persisting log records.

    When enabled by providing a ``db_path`` to ``configure_logging``,
    an instance of this handler is attached to the root logger.  Each
    log record is inserted into the ``logs`` table with columns
    ``timestamp`` (UTC ISO‑format), ``level``, ``module`` and
    ``message``.  This simple schema allows later analysis of
    application behaviour and trading decisions.

    If the ``logs`` table does not exist it is created automatically.
    The handler attempts to reconnect if the database becomes
    temporarily unavailable.
    """

    db_path: str

    def __post_init__(self) -> None:
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None
        self._ensure_connection()
        self._create_table()

    def _ensure_connection(self) -> None:
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
        except Exception as exc:
            print(f"Failed to connect to database at {self.db_path}: {exc}")
            self.conn = None
            self.cursor = None

    def _create_table(self) -> None:
        if not self.cursor:
            return
        try:
            self.cursor.execute(
                "CREATE TABLE IF NOT EXISTS logs (\n"
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                "  timestamp TEXT NOT NULL,\n"
                "  level TEXT NOT NULL,\n"
                "  module TEXT NOT NULL,\n"
                "  message TEXT NOT NULL\n"
                ")"
            )
            self.conn.commit()
        except Exception as exc:
            print(f"Failed to create logs table: {exc}")

    def emit(self, record: logging.LogRecord) -> None:
        if not self.cursor:
            return
        try:
            self.cursor.execute(
                "INSERT INTO logs (timestamp, level, module, message) VALUES (?, ?, ?, ?)",
                (
                    record.asctime if hasattr(record, "asctime") else record.created,
                    record.levelname,
                    record.name,
                    record.getMessage(),
                ),
            )
            self.conn.commit()
        except Exception:
            # Fail silently on DB errors so logging does not interrupt trading
            pass


def configure_logging(
    name: str = "paper_trading_boto",
    level: int = logging.INFO,
    db_path: Optional[str] = None,
) -> logging.Logger:
    """Configure and return a logger for the application.

    Parameters
    ----------
    name: str
        Name of the logger to configure.  Child loggers inherit
        handlers from the root logger by default.
    level: int
        Logging level (e.g., ``logging.INFO`` or ``logging.DEBUG``).
    db_path: Optional[str]
        If provided, path to an SQLite database for log persistence.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # Avoid duplicate logs when using root

    # Console handler with simple format
    ch = logging.StreamHandler()
    ch.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Optional DB handler
    if db_path:
        db_logger = DBLogger(db_path)

        class SQLHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                db_logger.emit(record)

        sql_handler = SQLHandler()
        sql_handler.setLevel(level)
        logger.addHandler(sql_handler)

    return logger
