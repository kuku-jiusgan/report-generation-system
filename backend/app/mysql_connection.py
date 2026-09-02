from contextlib import contextmanager
from typing import Any, Iterator

import pymysql


class HybridRow(dict):
    def __init__(self, values: dict[str, Any], columns: list[str]):
        super().__init__(values)
        self._columns = columns

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return super().__getitem__(self._columns[key])
        return super().__getitem__(key)


class MySQLCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "MySQLCursor":
        self._cursor.execute(sql, params)
        self.lastrowid = getattr(self._cursor, "lastrowid", None)
        self.rowcount = self._cursor.rowcount
        return self

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> "MySQLCursor":
        self._cursor.executemany(sql, params)
        self.lastrowid = getattr(self._cursor, "lastrowid", None)
        self.rowcount = self._cursor.rowcount
        return self

    def fetchone(self) -> HybridRow | None:
        row = self._cursor.fetchone()
        if row is None: return None
        columns = [item[0] for item in self._cursor.description]
        return HybridRow(dict(zip(columns, row)), columns)

    def fetchall(self) -> list[HybridRow]:
        rows = self._cursor.fetchall(); columns = [item[0] for item in self._cursor.description]
        return [HybridRow(dict(zip(columns, row)), columns) for row in rows]

    def __iter__(self):
        return iter(self.fetchall())


class MySQLConnection:
    def __init__(self, connection: Any): self._connection = connection

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> MySQLCursor:
        cursor = MySQLCursor(self._connection.cursor())
        return cursor.execute(sql, params)

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> MySQLCursor:
        cursor = MySQLCursor(self._connection.cursor())
        return cursor.executemany(sql, params)

    def __getattr__(self, name: str) -> Any: return getattr(self._connection, name)


@contextmanager
def mysql_connect(settings: Any) -> Iterator[MySQLConnection]:
    connection = pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
                                 user=settings.mysql_user, password=settings.mysql_password,
                                 database=settings.mysql_database, charset="utf8mb4", autocommit=False)
    try:
        yield MySQLConnection(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
