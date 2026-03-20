"""
GhostScripter-K1-K2 — Database Package
"""
from ghostscripter.core.database.manager import (
    DatabaseManager, get_db, close_db, DB_PATH, APP_DATA_DIR
)

__all__ = ["DatabaseManager", "get_db", "close_db", "DB_PATH", "APP_DATA_DIR"]
