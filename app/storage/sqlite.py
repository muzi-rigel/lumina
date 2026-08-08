"""旧存储入口的兼容导出。"""

from app.storage.database import SQLiteDatabase, StorageError

SQLiteStorage = SQLiteDatabase

__all__ = ["SQLiteDatabase", "SQLiteStorage", "StorageError"]
