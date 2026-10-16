"""SQLite schema 與存取層。

SQLite 專屬語法（如 INSERT OR REPLACE）只允許出現在這個套件內。
所有寫入必須 idempotent。
"""

from stockwatch.store.db import connect, init_schema

__all__ = ["connect", "init_schema"]
